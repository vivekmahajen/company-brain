"""Phase 8: per-tenant brain scorecard + vertical capability packs."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.packs.catalog import install_pack
from apps.api.services.orgs import create_org
from apps.api.services.scorecard import tenant_scorecard


@pytest.fixture(scope="module")
def client(seeded):
    with TestClient(app) as c:
        yield c


def _bearer(t):
    return {"Authorization": f"Bearer {t}"}


def test_scorecard_reports_brain_health(seeded, db, org_id):
    sc = tenant_scorecard(db, org_id)  # the default org has the seeded demo brain
    assert 0 <= sc["readiness"] <= 100
    assert sc["skills"]["total"] >= 3
    assert sc["knowledge"]["approved"] > 0
    assert sc["capabilities"]["total"] >= 3
    assert set(sc["subscores"]) == {"review", "coverage", "routable", "governance", "freshness"}


def test_scorecard_endpoint_is_tenant_scoped(client):
    org = client.post("/api/orgs", json={"name": "ScoreCo"}).json()
    sc = client.get("/api/scorecard", headers=_bearer(org["tokens"]["agent-token"])).json()
    assert sc["org_id"] == org["id"]


def test_packs_catalog_and_install(seeded, db):
    org = create_org(db, name="PackCo")["id"]
    # upgrade so capability quota doesn't block a multi-capability pack
    from apps.api.billing.metering import set_plan
    set_plan(db, org, "business")

    res = install_pack(db, org, "saas-support")
    assert "plan_change" in res["installed"] and "bug_escalation" in res["installed"]

    # the installed capabilities now show up as the tenant's templates
    from apps.api.compiler.registry import get_templates
    topics = set(get_templates(db, org))
    assert {"plan_change", "bug_escalation"} <= topics
    # re-installing is idempotent (dedup)
    again = install_pack(db, org, "saas-support")
    assert again["installed"] == [] and len(again["skipped"]) == 2


def test_unknown_pack_404(client):
    org = client.post("/api/orgs", json={"name": "NoPack"}).json()
    r = client.post("/api/packs/does-not-exist/install", headers=_bearer(org["tokens"]["agent-token"]))
    assert r.status_code == 404


def test_pack_install_respects_capability_quota(client):
    # free plan caps custom capabilities at 1 → a 2-capability pack partly installs
    org = client.post("/api/orgs", json={"name": "QuotaPack"}).json()
    res = client.post("/api/packs/ecommerce-ops/install", headers=_bearer(org["tokens"]["agent-token"])).json()
    assert len(res["installed"]) == 1 and len(res["skipped"]) == 1
    assert res["skipped"][0]["quota"] is True
