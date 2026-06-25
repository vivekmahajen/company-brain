"""Phase-2 Slice 2: OAuth scaffolding. Offline — the one network call (token
exchange) is monkeypatched; everything else (state sealing, tenant binding,
configured/unconfigured paths) is real."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.config import get_settings
from apps.api.connectors import oauth
from apps.api.main import app


@pytest.fixture(scope="module")
def client(seeded):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def org_b(client):
    return client.post("/api/orgs", json={"name": "Hooli"}).json()


@pytest.fixture()
def configured(monkeypatch):
    monkeypatch.setenv("OAUTH_SLACK_CLIENT_ID", "cid-123")
    monkeypatch.setenv("OAUTH_SLACK_CLIENT_SECRET", "csec-456")
    monkeypatch.setenv("OAUTH_REDIRECT_BASE", "https://api.test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _bearer(t):
    return {"Authorization": f"Bearer {t}"}


def test_authorize_reports_not_configured_until_app_is_set(client):
    r = client.get("/api/connect/slack/authorize").json()
    assert r["configured"] is False
    assert "OAUTH_SLACK_CLIENT_ID" in r["needed_env"]


def test_authorize_builds_consent_url_when_configured(client, configured, org_b):
    r = client.get("/api/connect/slack/authorize", headers=_bearer(org_b["tokens"]["agent-token"])).json()
    assert r["configured"] is True
    url = r["authorize_url"]
    assert url.startswith("https://slack.com/oauth/v2/authorize?")
    assert "client_id=cid-123" in url
    assert "redirect_uri=https%3A%2F%2Fapi.test%2Fapi%2Fconnect%2Fslack%2Fcallback" in url
    assert "state=" in url and "scope=" in url


def test_state_binds_tenant_and_rejects_tamper_and_expiry(configured, monkeypatch):
    state = oauth.seal_state("org-xyz", "slack")
    assert oauth.unseal_state(state, "slack") == "org-xyz"
    # wrong provider
    with pytest.raises(ValueError):
        oauth.unseal_state(state, "github")
    # tampered ciphertext
    with pytest.raises(Exception):
        oauth.unseal_state(state[:-3] + "zzz", "slack")
    # expired: jump the clock past the TTL
    monkeypatch.setattr(oauth.time, "time", lambda: 9_999_999_999)
    with pytest.raises(ValueError):
        oauth.unseal_state(state, "slack")


def test_callback_exchanges_code_and_provisions_to_sealed_tenant(client, configured, org_b, monkeypatch):
    # mock the network token exchange
    monkeypatch.setattr(oauth, "exchange_code", lambda kind, code: {"access_token": "xoxb-from-oauth"})
    state = oauth.seal_state(org_b["id"], "slack")
    r = client.get(f"/api/connect/slack/callback?code=abc123&state={state}").json()
    assert r["connected"] is True
    assert r["org_id"] == org_b["id"]
    assert r["source"]["kind"] == "slack" and r["source"]["has_credentials"] is True
    # the token landed in the vault for org B, not in the response
    assert "xoxb-from-oauth" not in str(r)
    from apps.api.services.connections import load_source_secret
    from apps.api.models.db import SessionLocal
    db = SessionLocal()
    try:
        assert load_source_secret(db, org_b["id"], r["source"]["id"]) == {"access_token": "xoxb-from-oauth"}
    finally:
        db.close()


def test_callback_rejects_bad_state(client, configured):
    r = client.get("/api/connect/slack/callback?code=abc&state=not-a-valid-state").json()
    assert r["connected"] is False and "state" in r["error"]


def test_catalog_exposes_oauth_configured_flag(client, configured):
    cat = {c["kind"]: c for c in client.get("/api/connectors").json()}
    assert cat["slack"]["auth"] == "oauth"
    assert cat["slack"]["oauth_configured"] is True
    assert cat["slack"]["authorize_path"] == "/api/connect/slack/authorize"
