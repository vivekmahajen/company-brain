"""Phase 6: usage metering, plan tiers, quota enforcement. Per-tenant, no Stripe key."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.billing.metering import period_extraction_usd, record_usage, usage_summary
from apps.api.main import app
from apps.api.services.orgs import create_org


@pytest.fixture(scope="module")
def client(seeded):
    with TestClient(app) as c:
        yield c


def _org(client, name):
    return client.post("/api/orgs", json={"name": name}).json()


def _bearer(t):
    return {"Authorization": f"Bearer {t}"}


def test_metering_aggregates_extraction_spend_per_tenant(seeded, db):
    org = create_org(db, name="MeterCo")["id"]
    record_usage(db, org, "extraction", cost_usd=0.012)
    record_usage(db, org, "extraction", cost_usd=0.008)
    record_usage(db, org, "sync")  # non-cost event ignored in the $ meter
    db.commit()
    assert period_extraction_usd(db, org) == pytest.approx(0.02)
    s = usage_summary(db, org)
    assert s["plan"] == "free" and s["usage"]["extraction_usd"] == pytest.approx(0.02)


def test_free_plan_caps_sources_and_upgrade_lifts_it(client):
    org = _org(client, "CapCo")
    tok = org["tokens"]["agent-token"]
    # free plan: 2 sources allowed
    for i in range(2):
        r = client.post("/api/sources/connect", headers=_bearer(tok),
                        json={"kind": "manual", "name": f"src{i}"})
        assert r.status_code == 200, r.text
    # 3rd source → 402 Payment Required
    blocked = client.post("/api/sources/connect", headers=_bearer(tok),
                          json={"kind": "manual", "name": "src3"})
    assert blocked.status_code == 402

    # upgrade to team → now allowed
    assert client.post("/api/billing/plan", headers=_bearer(tok), json={"plan": "team"}).status_code == 200
    assert client.post("/api/sources/connect", headers=_bearer(tok),
                       json={"kind": "manual", "name": "src3"}).status_code == 200


def test_free_plan_caps_custom_capabilities(client):
    org = _org(client, "CapsCo")
    tok = org["tokens"]["agent-token"]
    assert client.post("/api/templates", headers=_bearer(tok),
                       json={"topic": "cap_one", "title": "One"}).status_code == 200
    # free allows 1 custom capability → second is 402
    assert client.post("/api/templates", headers=_bearer(tok),
                       json={"topic": "cap_two", "title": "Two"}).status_code == 402


def test_usage_endpoint_reports_plan_limits_and_remaining(client):
    org = _org(client, "UsageCo")
    tok = org["tokens"]["agent-token"]
    u = client.get("/api/usage", headers=_bearer(tok)).json()
    assert u["plan"] == "free"
    assert u["limits"]["max_sources"] == 2
    assert u["remaining"]["sources"] == 2  # nothing connected yet
    plans = client.get("/api/billing/plans").json()
    assert set(plans) >= {"free", "team", "business", "enterprise"}


def test_extraction_blocked_when_over_budget(seeded, db):
    from apps.api.extraction.extractor import extract_pending

    org = create_org(db, name="BudgetCo")["id"]
    # blow past the free $1 monthly extraction budget
    record_usage(db, org, "extraction", cost_usd=1.5)
    db.commit()
    res = extract_pending(db, org)
    assert res["units_created"] == 0 and "over_budget" in res
