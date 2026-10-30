"""Opt-in telemetry and readiness, without a browser."""

import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apps.agent.contracts import Action
from apps.agent.crawler import actions
from apps.agent.crawler import playwright_crawler as module


@pytest.fixture
def setup(monkeypatch):
    page = Mock()
    page.url = "https://example.test/"
    page.locator.return_value.inner_html.return_value = "<body>ready</body>"
    session = Mock()
    session.__enter__ = Mock(return_value=page)
    session.__exit__ = Mock()
    monkeypatch.setattr(module, "launch_session", Mock(return_value=session))
    state = {"success": True, "url": page.url, "dom": "ready"}
    monkeypatch.setattr(module, "extract_page_state", Mock(return_value=state))
    clock = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    page.wait_for_timeout.side_effect = lambda ms: clock.__setitem__(0, clock[0] + ms / 1000)
    return page, session, clock, state


def request(url, kind="fetch", method="GET"):
    return SimpleNamespace(url=url, resource_type=kind, method=method)


def listeners(page):
    return dict(call.args for call in page.on.call_args_list)


def test_default_unchanged(setup):
    page, _, _, _ = setup
    crawler = module.PlaywrightCrawler()
    crawler.open(page.url)
    page.on.assert_not_called()
    page.locator.assert_not_called()
    page.wait_for_load_state.assert_called_once_with("networkidle", timeout=5000)
    assert crawler.drain() == ()


def test_labels_windows_failures_and_cleanup(setup):
    page, session, _, _ = setup
    crawler = module.PlaywrightCrawler(probabilistic_states=True)
    crawler.open(page.url)
    handlers = listeners(page)
    assert set(handlers) == {"request", "requestfinished", "requestfailed", "framenavigated"}
    req = request(
        "https://user:secret@example.test/api/123/550e8400-e29b-41d4-a716-446655440000?q=secret#private"
    )
    handlers["request"](req)
    handlers["requestfailed"](req)
    handlers["request"](req)
    handlers["requestfinished"](req)
    handlers["request"](request("https://example.test/image/1", "image"))
    assert crawler.drain() == ("GET /api/:id/:uuid",) * 2
    assert crawler.drain() == ()
    handlers["request"](request("https://example.test/users/%31%32?token=x", "xhr", "post"))
    assert crawler.drain() == ("POST /users/:id",)
    crawler.open(page.url)
    assert page.on.call_count == 4
    crawler.close()
    crawler.close()
    assert page.remove_listener.call_count == 4
    for event, handler in handlers.items():
        page.remove_listener.assert_any_call(event, handler)
    session.__exit__.assert_called_once()


@pytest.mark.parametrize("busy", ["pending", "dom"])
def test_readiness_is_bounded(setup, busy):
    page, _, clock, _ = setup
    crawler = module.PlaywrightCrawler(probabilistic_states=True)
    crawler._start_session()
    if busy == "pending":
        listeners(page)["request"](request("https://example.test/poll"))
    else:
        page.locator.return_value.inner_html.side_effect = lambda **kw: str(clock[0])
    crawler.open(page.url)
    assert 1.9 <= clock[0] <= 2.01
    page.wait_for_load_state.assert_not_called()
    assert module.extract_page_state.call_count == 1


def test_readiness_waits_for_failure_and_dom_quiet(setup):
    page, _, clock, _ = setup
    crawler = module.PlaywrightCrawler(probabilistic_states=True)
    crawler._start_session()
    req = request("https://example.test/data")
    handlers = listeners(page)
    handlers["request"](req)

    def tick(ms):
        clock[0] += ms / 1000
        if 0.3 <= clock[0] < 0.35:
            handlers["requestfailed"](req)

    page.wait_for_timeout.side_effect = tick
    crawler.open(page.url)
    assert 0.5 <= clock[0] < 1
    assert crawler.drain() == ("GET /data",)


def test_action_hook_precedes_capture(setup, monkeypatch):
    page, _, _, state = setup
    order = []
    monkeypatch.setattr(actions, "_perform_action", lambda *a, **kw: order.append("action"))
    monkeypatch.setattr(actions, "extract_page_state", lambda *a: order.append("capture") or state)
    result = actions.execute_action(
        page, {"type": "click"}, before_capture=lambda: order.append("ready")
    )
    assert result["success"]
    assert order == ["action", "ready", "capture"]


def test_crawler_action_uses_readiness_hook(setup, monkeypatch):
    page, _, _, state = setup
    crawler = module.PlaywrightCrawler(probabilistic_states=True)
    crawler.open(page.url)
    execute = Mock(return_value={"success": True, "resulting_state": state})
    monkeypatch.setattr(module, "execute_action", execute)
    crawler.act(Action(action_id="a", kind="click", target="#go"))
    assert execute.call_args.kwargs["before_capture"] == crawler._wait_for_capture_ready


def test_default_action_call_is_unchanged(setup, monkeypatch):
    page, _, _, state = setup
    crawler = module.PlaywrightCrawler()
    crawler.open(page.url)
    execute = Mock(return_value={"success": True, "resulting_state": state})
    monkeypatch.setattr(module, "execute_action", execute)
    crawler.act(Action(action_id="a", kind="click", target="#go"))
    assert execute.call_args.kwargs == {}


def test_dom_read_timeout_still_captures_within_budget(setup):
    page, _, clock, _ = setup
    page.locator.return_value.inner_html.side_effect = module.PlaywrightTimeoutError("missing html")
    crawler = module.PlaywrightCrawler(probabilistic_states=True)
    assert crawler.open(page.url).dom == "ready"
    assert clock[0] <= 2.01


def test_drain_does_not_forget_pending_requests(setup):
    page, _, clock, _ = setup
    crawler = module.PlaywrightCrawler(probabilistic_states=True)
    crawler._start_session()
    listeners(page)["request"](request("https://example.test/pending"))
    assert crawler.drain() == ("GET /pending",)
    crawler.open(page.url)
    assert clock[0] >= 1.9
    assert crawler.drain() == ()


def test_readiness_outcome_resets(setup):
    page, _, _, _ = setup
    crawler = module.PlaywrightCrawler(probabilistic_states=True)
    assert crawler.last_capture_ready is None
    crawler.open(page.url)
    assert crawler.last_capture_ready is True
    req = request(page.url)
    crawler._on_request(req)
    crawler.open(page.url)
    assert crawler.last_capture_ready is False
    crawler._on_request_done(req)
    crawler.open(page.url)
    assert crawler.last_capture_ready is True
    page.goto.side_effect = module.PlaywrightError("closed")
    with pytest.raises(module.NavigationError):
        crawler.open(page.url)
    assert crawler.last_capture_ready is None
    assert module.PlaywrightCrawler().last_capture_ready is None


@pytest.mark.parametrize("failure", ["ready", "capture"])
@pytest.mark.parametrize("enabled,expected", [(True, 1), (False, 3)])
def test_post_action_timeout_does_not_replay_opted_in(
    setup, monkeypatch, failure, enabled, expected
):
    page, _, _, state = setup
    perform = Mock()
    ready = Mock()
    capture = Mock(return_value=state)
    if failure == "ready" and enabled:
        ready.side_effect = module.PlaywrightTimeoutError("readiness failed")
    else:
        capture.side_effect = module.PlaywrightTimeoutError("capture failed")
    monkeypatch.setattr(actions, "_perform_action", perform)
    monkeypatch.setattr(actions, "extract_page_state", capture)
    monkeypatch.setattr(actions.time, "sleep", Mock())
    result = actions.execute_action(
        page, {"type": "click"}, before_capture=ready if enabled else None
    )
    assert not result["success"]
    assert perform.call_count == expected


def test_navigation_cleanup_requires_main_document_commit(setup):
    page, _, _, _ = setup
    crawler = module.PlaywrightCrawler(probabilistic_states=True)
    crawler.open(page.url)
    handlers = listeners(page)
    old = request(page.url)
    crawler._on_request(old)
    handlers["framenavigated"](page.main_frame)  # fragment/history navigation
    assert id(old) in crawler._pending
    nav = SimpleNamespace(
        resource_type="document", frame=page.main_frame, is_navigation_request=lambda: True
    )
    crawler._on_request(nav)
    handlers["requestfailed"](nav)
    handlers["framenavigated"](page.main_frame)
    assert id(old) in crawler._pending
    crawler._on_request(nav)
    new = request(page.url + "new")
    crawler._on_request(new)
    handlers["framenavigated"](object())  # child frame
    assert id(old) in crawler._pending
    handlers["framenavigated"](page.main_frame)
    assert crawler._pending == {id(new)}


@pytest.mark.parametrize("failure", ["ready", "capture", "unsuccessful"])
def test_crawler_act_failure_fires_click_once(setup, monkeypatch, failure):
    page, _, _, _ = setup
    crawler = module.PlaywrightCrawler(probabilistic_states=True)
    crawler.open(page.url)
    monkeypatch.setattr(actions.time, "sleep", Mock())
    capture = Mock(return_value={"success": False, "error": "screenshot failed"})
    monkeypatch.setattr(actions, "extract_page_state", capture)
    if failure == "ready":
        page.locator.return_value.inner_html.side_effect = module.PlaywrightError("closed")
    elif failure == "capture":
        capture.side_effect = module.PlaywrightTimeoutError("screenshot timeout")
    with pytest.raises((module.ActionError, module.NavigationError)):
        crawler.act(Action(action_id="a", kind="click", target="#submit"))
    page.click.assert_called_once()
    if failure == "ready":
        assert crawler.last_capture_ready is None
        capture.assert_not_called()


def test_action_execution_timeout_keeps_existing_retries(setup, monkeypatch):
    page, _, _, state = setup
    perform = Mock(side_effect=[module.PlaywrightTimeoutError("not visible"), None])
    monkeypatch.setattr(actions, "_perform_action", perform)
    monkeypatch.setattr(actions, "extract_page_state", Mock(return_value=state))
    monkeypatch.setattr(actions.time, "sleep", Mock())
    ready = Mock()
    assert actions.execute_action(page, {"type": "click"}, before_capture=ready)["success"]
    assert perform.call_count == 2
    ready.assert_called_once()


@pytest.mark.parametrize("kind", ["click", "navigate"])
@pytest.mark.parametrize("enabled", [False, True])
def test_opted_in_actions_skip_legacy_networkidle(setup, monkeypatch, kind, enabled):
    page, _, _, state = setup
    monkeypatch.setattr(actions, "extract_page_state", Mock(return_value=state))
    ready = Mock() if enabled else None
    result = actions.execute_action(
        page, {"type": kind, "selector": "#go", "url": page.url}, before_capture=ready
    )
    assert result["success"]
    if enabled:
        page.wait_for_load_state.assert_not_called()
        ready.assert_called_once()
    else:
        page.wait_for_load_state.assert_called_once_with("networkidle", timeout=5000)
