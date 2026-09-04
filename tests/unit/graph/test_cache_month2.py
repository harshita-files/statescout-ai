"""
Unit tests for apps.agent.graph.cache — Month 2 session-scoped keys.

Tests verify:
  - Key pattern is session:{scan_id}:visited:{state_id}:{action_id}
  - clear() only removes keys for the given scan_id, not other sessions
  - set_ttl() sets an expiry on all session keys
  - is_visited / mark_visited still work correctly (regression)

Run:  pytest tests/unit/test_cache_month2.py -v
"""

import fakeredis
import pytest

import apps.agent.graph.cache as cache_module
from apps.agent.graph.cache import VisitedCache


@pytest.fixture
def fake_redis():
    """Patch redis.from_url at module level and yield a FakeStrictRedis instance."""
    original = cache_module.redis.from_url
    fake = fakeredis.FakeStrictRedis(decode_responses=True)
    cache_module.redis.from_url = lambda url, decode_responses=True: fake
    yield fake
    cache_module.redis.from_url = original


@pytest.fixture
def cache_a(fake_redis):
    c = VisitedCache(scan_id="scan-aaa")
    c.clear()
    return c


@pytest.fixture
def cache_b(fake_redis):
    c = VisitedCache(scan_id="scan-bbb")
    c.clear()
    return c


class TestSessionScopedKeys:
    def test_key_pattern_is_session_scoped(self, cache_a, fake_redis):
        """Keys must use session:{scan_id}:visited: prefix."""
        cache_a.mark_visited("fp_abc", "click")
        keys = fake_redis.keys("*")
        assert len(keys) == 1
        assert keys[0] == "session:scan-aaa:visited:fp_abc:click"

    def test_different_scans_are_isolated(self, cache_a, cache_b):
        """Marking visited in scan-aaa must not affect scan-bbb."""
        cache_a.mark_visited("fp_abc", "click")
        assert cache_a.is_visited("fp_abc", "click")
        assert not cache_b.is_visited("fp_abc", "click")

    def test_clear_only_removes_own_scan_keys(self, cache_a, cache_b, fake_redis):
        """clear() on scan-aaa must leave scan-bbb keys intact."""
        cache_a.mark_visited("fp_abc", "click")
        cache_b.mark_visited("fp_xyz", "navigate")

        cache_a.clear()

        assert not cache_a.is_visited("fp_abc", "click")
        assert cache_b.is_visited("fp_xyz", "navigate")

    def test_clear_removes_all_keys_for_own_scan(self, cache_a):
        """clear() must wipe every key for its own scan."""
        cache_a.mark_visited("fp_1", "click")
        cache_a.mark_visited("fp_2", "navigate")
        cache_a.mark_visited("fp_3", "fill")

        cache_a.clear()

        assert not cache_a.is_visited("fp_1", "click")
        assert not cache_a.is_visited("fp_2", "navigate")
        assert not cache_a.is_visited("fp_3", "fill")


class TestVisitedCacheRegression:
    """Month 1 behavioural contract must still hold."""

    def test_unmarked_is_not_visited(self, cache_a):
        assert not cache_a.is_visited("fp_new", "click")

    def test_marked_is_visited(self, cache_a):
        cache_a.mark_visited("fp_abc", "click")
        assert cache_a.is_visited("fp_abc", "click")

    def test_different_action_same_fp_is_not_visited(self, cache_a):
        cache_a.mark_visited("fp_abc", "click")
        assert not cache_a.is_visited("fp_abc", "navigate")

    def test_mark_visited_is_idempotent(self, cache_a):
        cache_a.mark_visited("fp_abc", "click")
        cache_a.mark_visited("fp_abc", "click")
        assert cache_a.is_visited("fp_abc", "click")


class TestSetTTL:
    def test_set_ttl_applies_expiry_to_all_session_keys(self, cache_a, fake_redis):
        """set_ttl must set a positive TTL on all keys for this session."""
        cache_a.mark_visited("fp_1", "click")
        cache_a.mark_visited("fp_2", "navigate")
        cache_a.set_ttl(3600)
        for key in fake_redis.keys("session:scan-aaa:*"):
            ttl = fake_redis.ttl(key)
            assert ttl > 0, f"Expected positive TTL on {key}, got {ttl}"
