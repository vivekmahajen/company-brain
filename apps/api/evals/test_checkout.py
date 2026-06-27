"""Phase 6 Stripe slice: checkout (stub mode, no key) + webhook plan application."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.billing.checkout import handle_webhook
from apps.api.billing.metering import get_plan
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


def test_stub_checkout_then_confirm_applies_plan(client):
    org = _org(client, "CheckoutCo")
    tok = org["tokens"]["agent-token"]
    res = client.post("/api/billing/checkout", headers=_bearer(tok),
                      json={"plan": "team", "success_url": "https://console.example/billing"}).json()
    assert res["mode"] == "stub" and "/api/billing/checkout/confirm?state=" in res["url"]

    # follow the stub confirm (no Stripe) → 302 back to the CONSOLE (not the API host)
    r = client.get(res["url"], follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("https://console.example/billing")
    assert "upgraded=team" in r.headers["location"]
    assert client.get("/api/usage", headers=_bearer(tok)).json()["plan"] == "team"


def test_free_downgrade_is_direct_and_enterprise_is_contact(client):
    org = _org(client, "TierCo")
    tok = org["tokens"]["agent-token"]
    client.post("/api/billing/plan", headers=_bearer(tok), json={"plan": "team"})  # start on team
    direct = client.post("/api/billing/checkout", headers=_bearer(tok), json={"plan": "free"}).json()
    assert direct["mode"] == "direct"
    assert client.get("/api/usage", headers=_bearer(tok)).json()["plan"] == "free"
    contact = client.post("/api/billing/checkout", headers=_bearer(tok), json={"plan": "enterprise"}).json()
    assert contact["mode"] == "contact"


def test_webhook_applies_plan_from_event_metadata(seeded, db):
    org = create_org(db, name="HookCo")["id"]
    event = {"type": "checkout.session.completed",
             "data": {"object": {"metadata": {"org_id": org, "plan": "business"}}}}
    assert handle_webhook(db, event)["applied"] == "business"
    assert get_plan(db, org) == "business"
    # lapsed subscription → downgrade to free
    cancel = {"type": "customer.subscription.deleted",
              "data": {"object": {"metadata": {"org_id": org}}}}
    handle_webhook(db, cancel)
    assert get_plan(db, org) == "free"


def test_webhook_endpoint_without_secret_applies(client):
    org = _org(client, "HookHttpCo")
    tok = org["tokens"]["agent-token"]
    body = {"type": "checkout.session.completed",
            "data": {"object": {"metadata": {"org_id": org["id"], "plan": "team"}}}}
    assert client.post("/api/billing/webhook", json=body).status_code == 200
    assert client.get("/api/usage", headers=_bearer(tok)).json()["plan"] == "team"
