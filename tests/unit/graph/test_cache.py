"""
Unit tests for apps.agent.graph.cache

Uses fakeredis — no real Redis or Docker required.

The fixture patches redis.from_url at the module level before constructing
VisitedCache, so the fake client takes over transparently.  This works
because cache.py no longer calls ping() in its constructor.

Run:  pytest tests/unit/test_cache.py -v
"""

import fakeredis
import pytest

import apps.agent.graph.cache as cache_module
from apps.agent.graph.cache import VisitedCache


@pytest.fixture
def fake_redis_cache():
    """
    Inject a fakeredis backend into VisitedCache and yield a clean instance.

    Patches redis.from_url at the module level so that VisitedCache.__init__
    receives a FakeStrictRedis instead of a real connection.  Restores the
    original function after the test.
    """
    original_from_url = cache_module.redis.from_url
    cache_module.redis.from_url = lambda url, decode_responses=True: fakeredis.FakeStrictRedis(
        decode_responses=decode_responses
    )
    cache = VisitedCache(scan_id="test-scan-001")
    cache.clear()  # start each test with a blank slate
    yield cache
    cache_module.redis.from_url = original_from_url


class TestVisitedCache:
    def test_unmarked_state_is_not_visited(self, fake_redis_cache):
        """A freshly cleared cache must report everything as unvisited."""
        assert not fake_redis_cache.is_visited("fp_abc", "click")

    def test_marked_state_is_visited(self, fake_redis_cache):
        """After mark_visited, is_visited must return True for that pair."""
        fake_redis_cache.mark_visited("fp_abc", "click")
        assert fake_redis_cache.is_visited("fp_abc", "click")

    def test_different_action_same_fingerprint_is_not_visited(self, fake_redis_cache):
        """(fp, action) pairs are distinct — different action on same state is unvisited."""
        fake_redis_cache.mark_visited("fp_abc", "click")
        assert not fake_redis_cache.is_visited("fp_abc", "type_text")

    def test_different_fingerprint_same_action_is_not_visited(self, fake_redis_cache):
        """Different state fingerprint with same action is a distinct, unvisited pair."""
        fake_redis_cache.mark_visited("fp_abc", "click")
        assert not fake_redis_cache.is_visited("fp_xyz", "click")

    def test_clear_removes_all_visited_marks(self, fake_redis_cache):
        """clear() must wipe ALL visited marks, not just the ones we set in this test."""
        fake_redis_cache.mark_visited("fp_abc", "click")
        fake_redis_cache.mark_visited("fp_xyz", "type")

        assert fake_redis_cache.is_visited("fp_abc", "click")
        assert fake_redis_cache.is_visited("fp_xyz", "type")

        fake_redis_cache.clear()

        assert not fake_redis_cache.is_visited("fp_abc", "click")
        assert not fake_redis_cache.is_visited("fp_xyz", "type")

    def test_mark_visited_is_idempotent(self, fake_redis_cache):
        """Calling mark_visited twice on the same pair must not raise and must still be visited."""
        fake_redis_cache.mark_visited("fp_abc", "click")
        fake_redis_cache.mark_visited("fp_abc", "click")
        assert fake_redis_cache.is_visited("fp_abc", "click")
