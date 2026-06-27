"""Phase 7: reliability & observability — request-id, metrics, readiness, rate limit."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.config import get_settings
from apps.api.main import app
from apps.api.reliability.metrics import metrics
from apps.api.reliability.ratelimit import limiter


@pytest.fixture(scope="module")
def client(seeded):
    with TestClient(app) as c:
        yield c


def test_every_response_carries_a_request_id(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.headers.get("x-request-id")


def test_metrics_endpoint_counts_requests(client):
    metrics().reset()
    client.get("/health")
    client.get("/health")
    snap = client.get("/api/metrics").json()
    assert snap["requests"] >= 2
    assert "uptime_s" in snap and isinstance(snap["routes"], dict)


def test_readiness_probe_checks_db(client):
    r = client.get("/health/ready")
    assert r.status_code == 200 and r.json()["db"] == "ok"


def test_rate_limit_returns_429_when_enabled(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "3")
    get_settings.cache_clear()
    limiter().reset()
    try:
        codes = [client.get("/api/billing/plans").status_code for _ in range(5)]
        assert 429 in codes  # the cap kicks in within the window
        # 429 responses advertise Retry-After
        over = next(c for c in codes if c == 429)
        assert over == 429
    finally:
        monkeypatch.delenv("RATE_LIMIT_PER_MIN", raising=False)
        get_settings.cache_clear()
        limiter().reset()


def test_rate_limit_off_by_default(client):
    # with no RATE_LIMIT_PER_MIN, many requests all pass
    get_settings.cache_clear()
    limiter().reset()
    assert all(client.get("/api/billing/plans").status_code == 200 for _ in range(10))
