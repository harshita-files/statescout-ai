"""Endpoint normalisation and the per-(state_class, action) endpoint counter."""

from __future__ import annotations

import json

import pytest

from apps.agent.orchestrator.stochastic.endpoints import (
    EndpointCounter,
    NetworkCall,
    normalise_endpoint,
)


@pytest.mark.parametrize(
    ("method", "url", "expected"),
    [
        ("get", "/api/users/42?x=1", "GET /api/users/{id}"),
        ("GET", "/api/users/42", "GET /api/users/{id}"),
        ("post", "https://Example.com:8443/api/items/7/", "POST /api/items/{id}"),
        ("GET", "/api/users/42/orders/9001", "GET /api/users/{id}/orders/{id}"),
        (
            "GET",
            "/api/doc/123e4567-e89b-12d3-a456-426614174000",
            "GET /api/doc/{uuid}",
        ),
        (
            "GET",
            "/api/doc/123E4567-E89B-12D3-A456-426614174000/edit",
            "GET /api/doc/{uuid}/edit",
        ),
        ("GET", "/blob/9f86d081884c7d659a2feaa0c55ad015", "GET /blob/{hex}"),
        ("GET", "/events/2026-10-15", "GET /events/{date}"),
        ("GET", "/events/2026/10/15", "GET /events/{id}/{id}/{id}"),
        (
            "GET",
            "/session/eyJhbGciOiJIUzI1NiJ9abc123XYZ789",
            "GET /session/{token}",
        ),
        ("GET", "/a?z=1&b=2&z=3", "GET /a"),
        ("GET", "/a?token=SECRETVALUE", "GET /a"),
        ("GET", "/a#frag", "GET /a"),
        ("GET", "", "GET /"),
        ("GET", "https://example.com", "GET /"),
        ("GET", "//cdn.example.com/x//y", "GET /x/y"),
        ("GET", "/api/authentication-settings", "GET /api/authentication-settings"),
        ("GET", "/API/Users", "GET /API/Users"),
        ("get", "https://user:pw@host.test/p", "GET /p"),
    ],
)
def test_normalise_endpoint(method: str, url: str, expected: str) -> None:
    assert normalise_endpoint(method, url) == expected


def test_normalisation_never_leaks_query_values_or_userinfo() -> None:
    out = normalise_endpoint("GET", "https://u:hunter2@h.test/p?api_key=sk-live-abc&b=2")
    assert "sk-live-abc" not in out
    assert "hunter2" not in out
    assert out == "GET /p"


def test_bare_token_like_query_key_is_redacted() -> None:
    out = normalise_endpoint("GET", "/a?eyJhbGciOiJIUzI1NiJ9abc123XYZ789")
    assert "eyJ" not in out
    assert out == "GET /a"


def test_percent_encoded_segments_are_classified_after_decoding() -> None:
    assert normalise_endpoint("GET", "/u/%34%32") == "GET /u/{id}"


def test_normalisation_is_idempotent_in_shape() -> None:
    once = normalise_endpoint("GET", "/api/users/42?x=1")
    method, _, path = once.partition(" ")
    assert normalise_endpoint(method, path) == once


def test_counter_records_and_counts() -> None:
    c = EndpointCounter()
    c.record("cls", "act", "GET /a")
    c.record("cls", "act", "GET /a")
    c.record("cls", "act", "GET /b", count=3)
    assert c.counts("cls", "act") == {"GET /a": 2, "GET /b": 3}
    assert c.counts("cls", "other") == {}


def test_counter_rejects_non_positive_count() -> None:
    with pytest.raises(ValueError):
        EndpointCounter().record("c", "a", "GET /a", count=0)


def test_record_calls_normalises() -> None:
    c = EndpointCounter()
    c.record_calls(
        "cls",
        "act",
        [
            NetworkCall("get", "/api/users/1?x=1", 200),
            NetworkCall("GET", "/api/users/2?x=9", 404),
        ],
    )
    assert c.counts("cls", "act") == {"GET /api/users/{id}": 2}


def test_top_k_is_ordered_and_deterministic() -> None:
    c = EndpointCounter()
    c.record("s", "a", "GET /z", count=2)
    c.record("s", "a", "GET /b", count=2)
    c.record("s", "a", "GET /top", count=5)
    c.record("s", "a", "GET /low")
    assert c.top_k("s", "a", 3) == [("GET /top", 5), ("GET /b", 2), ("GET /z", 2)]
    assert c.top_k("s", "a", 0) == []
    assert c.top_k("s", "missing", 3) == []
    with pytest.raises(ValueError):
        c.top_k("s", "a", -1)


def test_merge_adds_counts_and_does_not_mutate_inputs() -> None:
    a = EndpointCounter()
    a.record("s", "x", "GET /a", count=2)
    b = EndpointCounter()
    b.record("s", "x", "GET /a")
    b.record("t", "y", "GET /c")
    merged = a.merge(b)
    assert merged.counts("s", "x") == {"GET /a": 3}
    assert merged.counts("t", "y") == {"GET /c": 1}
    assert a.counts("s", "x") == {"GET /a": 2}
    assert b.counts("s", "x") == {"GET /a": 1}


def test_counts_returns_a_copy() -> None:
    c = EndpointCounter()
    c.record("s", "a", "GET /a")
    c.counts("s", "a")["GET /a"] = 99
    assert c.counts("s", "a") == {"GET /a": 1}


def test_dict_round_trip_is_json_safe() -> None:
    c = EndpointCounter()
    c.record("s", "a", "GET /a", count=2)
    c.record("s", "b", "POST /b")
    payload = json.loads(json.dumps(c.to_dict()))
    restored = EndpointCounter.from_dict(payload)
    assert restored == c
    assert restored.to_dict() == c.to_dict()


def test_from_dict_rejects_bad_counts() -> None:
    with pytest.raises(ValueError):
        EndpointCounter.from_dict({"s": {"a": {"GET /a": 0}}})


def test_network_call_is_frozen() -> None:
    call = NetworkCall("GET", "/a", 200)
    with pytest.raises(AttributeError):
        call.status = 500  # type: ignore[misc]
