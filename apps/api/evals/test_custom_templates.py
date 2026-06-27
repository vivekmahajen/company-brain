"""Phase 3: customer-authored capability templates. A tenant defines a new skill
shape; the compiler fills it from that tenant's knowledge, isolated per org."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.compiler.registry import get_templates, topic_keywords
from apps.api.compiler.skill_compiler import compile_skill
from apps.api.extraction.extractor import _detect_topic
from apps.api.main import app
from apps.api.models.tables import KnowledgeUnit
from apps.api.services.orgs import create_org
from apps.api.services.templates import create_template


@pytest.fixture(scope="module")
def client(seeded):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def org_b(client):
    return client.post("/api/orgs", json={"name": "TemplateCo"}).json()


def _bearer(t):
    return {"Authorization": f"Bearer {t}"}


def test_create_list_and_tenant_isolation(client, org_b):
    tok = org_b["tokens"]["agent-token"]
    r = client.post("/api/templates", headers=_bearer(tok), json={
        "topic": "vendor_invoice", "title": "Approve a vendor invoice",
        "keywords": ["invoice", "vendor", "accounts payable"],
        "intents": ["approve an invoice", "pay a vendor"],
    })
    assert r.status_code == 200, r.text

    # appears for org B, flagged custom, alongside the built-ins
    mine = {t["topic"]: t for t in client.get("/api/templates", headers=_bearer(tok)).json()}
    assert mine["vendor_invoice"]["custom"] is True
    assert "refund" in mine and mine["refund"]["custom"] is False

    # invisible to the default org (no token)
    default = {t["topic"] for t in client.get("/api/templates").json()}
    assert "vendor_invoice" not in default


def test_validation_rejects_builtin_topic_and_duplicates(client, org_b):
    tok = org_b["tokens"]["agent-token"]
    assert client.post("/api/templates", headers=_bearer(tok),
                       json={"topic": "refund", "title": "x"}).status_code == 400  # built-in
    # duplicate of the one created above
    assert client.post("/api/templates", headers=_bearer(tok),
                       json={"topic": "vendor_invoice", "title": "y"}).status_code == 400


def test_draft_then_create_from_description(client, org_b):
    tok = org_b["tokens"]["agent-token"]
    d = client.post("/api/templates/draft", headers=_bearer(tok),
                    json={"description": "Approve a vendor refund credit and notify billing"}).json()
    assert d["topic"] and d["title"]
    assert d["keywords"] and d["intents"]
    # the draft is editable, then created like any template (rename topic to avoid clashes)
    d["topic"] = "refund_credit"
    r = client.post("/api/templates", headers=_bearer(tok), json=d)
    assert r.status_code == 200, r.text
    topics = {t["topic"] for t in client.get("/api/templates", headers=_bearer(tok)).json()}
    assert "refund_credit" in topics


def test_custom_topic_drives_extraction_topic_detection(seeded, db):
    org = create_org(db, name="DetectCo")["id"]
    create_template(db, org, topic="vendor_invoice", title="Approve a vendor invoice",
                    keywords=["invoice", "vendor", "accounts payable"])
    tkw = topic_keywords(db, org)
    assert "vendor_invoice" in tkw
    assert _detect_topic("Please approve this vendor invoice for $12,000", tkw) == "vendor_invoice"
    # an unrelated artifact still routes to a built-in topic
    assert _detect_topic("customer wants a refund", tkw) == "refund"


def test_custom_template_compiles_into_a_skill(seeded, db):
    org = create_org(db, name="CompileCo")["id"]
    create_template(db, org, topic="vendor_invoice", title="Approve a vendor invoice",
                    keywords=["invoice", "vendor"], intents=["approve an invoice"])
    # the topic is in the tenant's compile set
    assert "vendor_invoice" in get_templates(db, org)

    # seed approved knowledge for the custom topic, then compile
    db.add(KnowledgeUnit(org_id=org, type="policy_rule", topic="vendor_invoice", status="approved",
                         statement="Vendor invoices above $10,000 require finance approval.",
                         payload_jsonb={"action": "finance_approval", "amount_threshold": 10000}))
    db.add(KnowledgeUnit(org_id=org, type="procedure_step", topic="vendor_invoice", status="approved",
                         statement="Look up the vendor by vendor_id.", payload_jsonb={"step_number": 1}))
    db.commit()

    skill = compile_skill(db, org, "vendor_invoice")
    assert skill is not None
    assert skill.slug == "vendor-invoice"
    assert "Vendor invoices above $10,000" in skill.body_md
