"""Independent safety checks; masks affect identity, never audit evidence."""
from dataclasses import replace

import pytest

from apps.agent.contracts import ActionError
from apps.agent.orchestrator.config import OrchestratorConfig
from apps.agent.orchestrator.deps import Ports
from apps.agent.orchestrator.dynamic import (
    DynamicStats,
    identity,
    observe_transition,
    pair_key,
    priority,
    probability,
)
from apps.agent.orchestrator.fakes import (
    DEFAULT_POLICY,
    FakeCrawler,
    FakeGraph,
    FakeLink,
    FakePage,
    FakePerception,
)
from apps.agent.orchestrator.graph_runner import explore


def config(**overrides):
    return OrchestratorConfig(_env_file=None, **{
        'probabilistic_states': True,
        'volatility_patterns': (r'data-nonce="[^"]*"',),
        'perception_rate_per_min': 0,
        'max_states': 20,
        'depth_limit': 5,
        **overrides,
    })


def run(crawler, settings=None, perception=None):
    graph = FakeGraph()
    result = explore(
        Ports(crawler, perception or FakePerception(), graph,
              network=crawler if hasattr(crawler, 'drain') else None),
        'http://fake.test/login', DEFAULT_POLICY, settings or config(),
    )
    return result, graph


def test_default_off_does_not_consume_network_or_change_identity(monkeypatch):
    monkeypatch.delenv('STATESCOUT_PROBABILISTIC_STATES', raising=False)

    class NoTelemetry(FakeCrawler):
        def drain(self):
            pytest.fail('default mode consumed experimental telemetry')

    settings = OrchestratorConfig(_env_file=None, perception_rate_per_min=0)
    assert settings.probabilistic_states is False
    result, graph = run(NoTelemetry(), settings)
    assert result.dynamic is None
    assert all(state.startswith('s-') for state in graph.states)
    assert result.states == 4


def test_overbroad_mask_preserves_violation_recall_on_equivalent_revisit():
    class ChangingRisk(FakeCrawler):
        def _render(self, path, page):
            tag = 'admin-link' if len(self.acted) == 1 else 'safe-link'
            return super()._render(path, replace(page, elements=(tag,)))

    crawler = ChangingRisk({'/login': FakePage('Same', transitions=(
        FakeLink('First', '/login'), FakeLink('Second', '/login'),
    ))})
    settings = config(volatility_patterns=(r'data-nonce="[^"]*"', r'(admin|safe)-link'))
    result, graph = run(crawler, settings)
    assert result.states == 1
    assert result.edges == 2
    assert len(result.order) == 3
    stats = result.dynamic
    assert stats is not None
    violation, = [v for v in result.violations if v.expectation_id == 'e-admin-link']
    assert violation.evidence.text == 'admin-link'
    assert stats.audits[violation.state_id] == 3
    assert stats.hits[violation.violation_id] == 1
    assert stats.confidence[violation.violation_id] == pytest.approx(2 / 5)
    assert len([v for v in graph.violations if v.expectation_id == 'e-admin-link']) == 1
    assert len(stats.exact_hashes[violation.state_id]) == 3


@pytest.mark.parametrize('replay_failure', [False, True])
def test_failed_actions_keep_endpoint_counts_without_phantom_transition(replay_failure):
    class FailingNetwork(FakeCrawler):
        calls = ()
        attempts = 0

        def act(self, action):
            self.attempts += 1
            self.calls = ('POST /api/check', 'POST /api/check', 'GET /private?token=secret')
            if not replay_failure or self.attempts == 3:
                raise ActionError('failed after sending request')
            return super().act(action)

        def drain(self):
            calls, self.calls = self.calls, ()
            return calls

    app = {
        '/login': FakePage('Root', transitions=(FakeLink('Enter', '/a', role='button'),)),
        '/a': FakePage('A', transitions=(FakeLink('Leave', '/b'), FakeLink('Other', '/c'))),
        '/b': FakePage('B'), '/c': FakePage('C'),
    }
    crawler = FailingNetwork(app)
    result, _ = run(crawler)
    stats = result.dynamic
    assert stats is not None
    assert set(stats.endpoints) == {'POST /api/check'}
    assert stats.endpoints['POST /api/check'] == {
        'calls': 6 if replay_failure else 2,
        'actions': 3 if replay_failure else 1,
        'clicks': 2 if replay_failure else 1,
        'replay_calls': 2 if replay_failure else 0,
        'replay_clicks': 1 if replay_failure else 0,
    }
    assert result.edges == (2 if replay_failure else 0)
    assert sum(sum(c.values()) for c in stats.transitions.values()) == result.edges
    assert not stats.replay_transitions
    assert len(result.skipped) == 1
    assert crawler.closed


def test_genuinely_different_replay_state_never_executes_pending_action():
    class Diverging(FakeCrawler):
        def open(self, url):
            bundle = super().open(url)
            if len(self.opened) > 1:
                return replace(bundle, dom=bundle.dom + '<button>New permission</button>')
            return bundle

    crawler = Diverging({'/login': FakePage('Root', transitions=(
        FakeLink('First', '/a'), FakeLink('Dangerous', '/b', role='button'),
    )), '/a': FakePage('A'), '/b': FakePage('B')})
    result, graph = run(crawler)
    assert len(crawler.acted) == 1
    assert result.visited_pairs == 1
    assert len(graph.edges) == 1
    assert len(result.skipped) == 1
    assert 'replay diverged' in result.skipped[0].reason


def test_transition_distributions_include_replays_but_keep_separate_subset():
    stats = DynamicStats()
    for target, replay in [('a', False), ('a', True), ('b', True), ('c', False)]:
        observe_transition(stats, 's', 'action', target, replay=replay)
    key = pair_key('s', 'action')
    assert stats.transitions[key] == {'a': 2, 'b': 1, 'c': 1}
    assert stats.replay_transitions[key] == {'a': 1, 'b': 1}
    assert [probability(stats, 's', 'action', t) for t in ('a', 'b', 'c')] == [.5, .25, .25]
    assert probability(stats, 'unknown', 'action', 'a') == 0
    assert priority(stats, 's', 'action') == pytest.approx(.7)
    assert priority(stats, 'unknown', 'action') == 1


def test_unconfigured_numeric_changes_and_role_are_not_masked():
    bundle = FakeCrawler().open('/login')
    settings = config()
    assert identity(replace(bundle, dom=bundle.dom + 'balance 123'), settings) != identity(
        replace(bundle, dom=bundle.dom + 'balance 124'), settings)
    assert identity(bundle, settings) != identity(bundle, config(role='admin'))


@pytest.mark.parametrize('width', [2, 80])
def test_finite_equivalent_self_loops_exhaust_frontier_without_recursion_error(width):
    crawler = FakeCrawler({'/login': FakePage('Loop', transitions=tuple(
        FakeLink(f'Loop {i}', '/login') for i in range(width)
    ))})
    result, graph = run(crawler, config(max_states=2))
    assert result.termination_reason == 'frontier_exhausted'
    assert result.states == 1
    assert result.visited_pairs == width
    assert len(graph.back_edges()) == width
    assert len(crawler.acted) == width
    assert crawler.closed


@pytest.mark.parametrize('limits, expected_states', [
    ({'max_states': 2}, 2), ({'depth_limit': 0}, 1),
])
def test_dynamic_mode_respects_state_and_depth_caps(limits, expected_states):
    crawler = FakeCrawler()
    result, _ = run(crawler, config(**limits))
    assert result.states == expected_states
    assert crawler.closed
    if limits.get('depth_limit') == 0:
        assert not crawler.acted
    else:
        assert result.termination_reason == 'max_states'


@pytest.mark.parametrize('case', ['allowed', 'visited', 'unlearned', 'unknown', 'changed_action'])
def test_retarget_records_only_actual_source_and_requires_prior_evidence(case):
    """Seed checkpoint-shaped history to isolate replay from frontier discovery."""
    from apps.agent.orchestrator.graph_runner import build_graph
    from apps.agent.orchestrator.state import PendingAction, initial_state

    app = {
        '/login': FakePage('Root', transitions=(FakeLink('Branch', '/b'),)),
        '/a': FakePage('A', transitions=(FakeLink('Continue', '/end'),)),
        '/b': FakePage('B', transitions=(FakeLink('Continue', '/end'),)),
        '/elsewhere': FakePage('Elsewhere'),
        '/end': FakePage('End'),
    }
    crawler, graph = FakeCrawler(app), FakeGraph()
    settings = config()
    bundles = {path: crawler.open(path) for path in app}
    ids = {path: identity(bundle, settings) for path, bundle in bundles.items()}
    branch, = crawler.enumerate_actions(bundles['/login'])
    action, = crawler.enumerate_actions(bundles['/a'])
    if case == 'changed_action':
        action = replace(action, target='#different-control')
    stats = DynamicStats()
    observe_transition(stats, ids['/login'], branch.action_id, ids['/a'], replay=False)
    if case != 'unlearned':
        observe_transition(stats, ids['/login'], branch.action_id, ids['/b'], replay=False)
    state = initial_state('retarget-safety', 'http://fake.test/login', role='guest')
    state.update(
        current_bundle=bundles['/elsewhere'],
        current_state_id=ids['/elsewhere'],
        seen=[sid for path, sid in ids.items() if path != '/end'
              and not (case == 'unknown' and path == '/b')],
        frontier=[PendingAction(ids['/a'], action, 2, (branch,))],
        dynamic=stats,
    )
    if case == 'visited':
        graph.mark_visited(ids['/b'], action.action_id)
    runner = build_graph(Ports(crawler, FakePerception(), graph), DEFAULT_POLICY, settings)
    final = runner.invoke(state, {'configurable': {'thread_id': 'retarget-safety'}})
    if case == 'allowed':
        edge, = graph.edges
        assert (edge.from_state_id, edge.to_state_id) == (ids['/b'], ids['/end'])
        assert graph.visited == {(ids['/b'], action.action_id)}
        assert final['dynamic'].transitions[pair_key(ids['/b'], action.action_id)] == {
            ids['/end']: 1,
        }
        assert len(crawler.acted) == 2
    else:
        assert not graph.edges
        assert len(crawler.acted) == 1  # only the replay step, never the pending action
        assert len(final['skipped']) == 1
    assert (ids['/a'], action.action_id) not in graph.visited
    assert pair_key(ids['/a'], action.action_id) not in final['dynamic'].transitions
