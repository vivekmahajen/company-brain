"""Phase-1 multi-tenancy gate: two companies on one deployment, provably isolated.

These run through the real ASGI stack (TenantMiddleware → routers), so they assert
the property a buyer cares about: a token for org B routes to org B, and org B can
never see org A's data (and vice versa). This is a hard gate — if it regresses,
tenant data is leaking.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.config import get_settings
from apps.api.main import app


@pytest.fixture(scope="module")
def client(seeded):  # `seeded` ensures the default org has a provisioned brain
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def org_b(client):
    """Create a second tenant via the real endpoint; return its id + tokens."""
    r = client.post("/api/orgs", json={"name": "Acme Robotics"})
    assert r.status_code == 200, r.text
    return r.json()


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_token_routes_to_the_right_org(client, org_b):
    default_org = get_settings().default_org_id

    # no credential → default org
    assert client.get("/api/orgs/current").json()["org_id"] == default_org

    # org B's agent token → org B
    tok_b = org_b["tokens"]["agent-token"]
    assert client.get("/api/orgs/current", headers=_bearer(tok_b)).json()["org_id"] == org_b["id"]

    # explicit X-Org-Id header → org B
    got = client.get("/api/orgs/current", headers={"X-Org-Id": org_b["id"]}).json()
    assert got["org_id"] == org_b["id"]

    # the two orgs are distinct
    assert org_b["id"] != default_org


def test_policy_created_in_one_tenant_is_invisible_to_the_other(client, org_b):
    tok_b = org_b["tokens"]["agent-token"]

    # create a uniquely-named policy in org B
    body = {"name": "acme-only-guardrail", "tool": "stripe_refund", "when": "amount > 777"}
    r = client.post("/api/policies", json=body, headers=_bearer(tok_b))
    assert r.status_code == 200, r.text

    # org B sees it
    names_b = [p["name"] for p in client.get("/api/policies", headers=_bearer(tok_b)).json()]
    assert "acme-only-guardrail" in names_b

    # the default org does NOT
    names_default = [p["name"] for p in client.get("/api/policies").json()]
    assert "acme-only-guardrail" not in names_default

    # symmetric: a default-org policy is invisible to org B
    client.post("/api/policies", json={"name": "default-only-guardrail", "tool": "stripe_refund",
                                       "when": "amount > 123"})
    names_b2 = [p["name"] for p in client.get("/api/policies", headers=_bearer(tok_b)).json()]
    assert "default-only-guardrail" not in names_b2


def test_strict_mode_fails_closed_without_a_tenant(client, monkeypatch):
    """With multi_tenant_strict on, an unauthenticated request to a tenant route is
    rejected (no silent fallback to the default org), while tenant-management and
    health routes still work."""
    monkeypatch.setenv("MULTI_TENANT_STRICT", "true")
    get_settings.cache_clear()
    try:
        # tenant route, no credential → 401 (fail closed)
        assert client.get("/api/policies").status_code == 401
        # allowlisted management route still reachable
        assert client.get("/api/orgs").status_code == 200
        # a valid org header resolves and is allowed through
        default_org = get_settings().default_org_id
        assert client.get("/api/policies", headers={"X-Org-Id": default_org}).status_code == 200
    finally:
        monkeypatch.delenv("MULTI_TENANT_STRICT", raising=False)
        get_settings.cache_clear()
