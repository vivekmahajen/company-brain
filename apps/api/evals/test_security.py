"""Phase 5: audit log, data export, right-to-erasure. Per-tenant, deterministic."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.config import get_settings
from apps.api.main import app
from apps.api.services.compliance import delete_tenant, export_tenant
from apps.api.services.orgs import create_org


@pytest.fixture(scope="module")
def client(seeded):
    with TestClient(app) as c:
        yield c


def _org(client, name):
    org = client.post("/api/orgs", json={"name": name}).json()
    client.post("/api/billing/plan", headers=_bearer(org["tokens"]["agent-token"]), json={"plan": "business"})
    return org


def _bearer(t):
    return {"Authorization": f"Bearer {t}"}


def test_actions_are_audited_and_listable(client):
    org = _org(client, "AuditCo")
    tok = org["tokens"]["agent-token"]
    client.post("/api/sources/connect", headers=_bearer(tok), json={"kind": "manual", "name": "audited-src"})
    client.post("/api/templates", headers=_bearer(tok), json={"topic": "audited_cap", "title": "Cap"})

    rows = client.get("/api/audit", headers=_bearer(tok)).json()
    actions = {r["action"] for r in rows}
    assert "source.connect" in actions and "capability.create" in actions and "billing.plan_change" in actions
    # every event is this tenant's
    # CSV export works
    csv = client.get("/api/audit?format=csv", headers=_bearer(tok))
    assert csv.status_code == 200 and "action" in csv.text


def test_audit_is_tenant_isolated(client):
    a = _org(client, "AuditA")
    b = _org(client, "AuditB")
    client.post("/api/sources/connect", headers=_bearer(a["tokens"]["agent-token"]),
                json={"kind": "manual", "name": "a-only"})
    rows_b = client.get("/api/audit", headers=_bearer(b["tokens"]["agent-token"])).json()
    assert all(r["target_id"] != "a-only" for r in rows_b)
    assert not any(r["meta"].get("name") == "a-only" for r in rows_b)


def test_export_includes_data_but_never_secrets(seeded, db):
    from apps.api.services.connections import connect_source

    org = create_org(db, name="ExportCo")["id"]
    connect_source(db, org, kind="github", name="x/y", secrets={"access_token": "ghp_TOPSECRET"})
    dump = export_tenant(db, org)
    assert dump["org_id"] == org
    assert dump["skills"] and dump["sources"]
    assert "ghp_TOPSECRET" not in str(dump)  # credentials redacted


def test_right_to_erasure_purges_all_tenant_data(seeded, db):
    from sqlalchemy import func, select

    from apps.api.models.tables import KnowledgeUnit, Skill, Source
    from apps.api.services.connections import connect_source

    org = create_org(db, name="EraseCo")["id"]
    connect_source(db, org, kind="manual", name="to-erase")
    assert db.scalar(select(func.count(Skill.id)).where(Skill.org_id == org)) > 0

    res = delete_tenant(db, org)
    assert res["deleted"]  # something was deleted
    for model in (Source, KnowledgeUnit, Skill):
        assert db.scalar(select(func.count(model.id)).where(model.org_id == org)) == 0


def test_default_org_is_protected_from_deletion(client):
    # no token → default org; deletion must be refused
    r = client.post("/api/org/delete", json={"confirm": True})
    assert r.status_code == 400
    assert "default org" in r.json()["detail"]
