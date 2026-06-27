"""Phase-2 (Slice 1) tests: encrypted vault + self-serve, tenant-isolated source
connections. Credentials are never stored in plaintext or leaked across tenants."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.secrets.vault import get_vault
from apps.api.services.connections import load_source_secret


@pytest.fixture(scope="module")
def client(seeded):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def org_b(client):
    return client.post("/api/orgs", json={"name": "Globex"}).json()


def _bearer(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


# --- vault ----------------------------------------------------------------
def test_vault_roundtrip_and_no_plaintext():
    v = get_vault()
    secrets = {"access_token": "xoxb-super-secret-123", "team": "acme"}
    token = v.encrypt(secrets)
    assert "xoxb-super-secret-123" not in token  # ciphertext hides the secret
    assert v.decrypt(token) == secrets


def test_vault_detects_tampering():
    v = get_vault()
    token = v.encrypt({"k": "v"})
    tampered = token[:-4] + ("AAAA" if token[-4:] != "AAAA" else "BBBB")
    with pytest.raises(Exception):
        v.decrypt(tampered)


# --- connect / sync / isolation ------------------------------------------
def test_connect_stores_credentials_in_vault_not_config(client, org_b, db):
    tok = org_b["tokens"]["agent-token"]
    r = client.post("/api/sources/connect", headers=_bearer(tok), json={
        "kind": "github", "name": "globex/api",
        "config": {"acl_groups": ["eng-team"]},
        "secrets": {"access_token": "ghp_secret_value_xyz"},
    })
    assert r.status_code == 200, r.text
    view = r.json()
    assert view["has_credentials"] is True
    # the secret is nowhere in the API response
    assert "ghp_secret_value_xyz" not in r.text
    # ...but is retrievable from the vault for the owning tenant
    assert load_source_secret(db, org_b["id"], view["id"]) == {"access_token": "ghp_secret_value_xyz"}
    # ...and is NOT in the source's config_jsonb (which GET /sources exposes)
    sources = client.get("/api/sources", headers=_bearer(tok)).json()
    mine = [s for s in sources if s["id"] == view["id"]][0]
    assert "ghp_secret_value_xyz" not in str(mine)


def test_connect_and_sync_a_fixture_backed_source(client, org_b):
    tok = org_b["tokens"]["agent-token"]
    fixture = os.path.join("fixtures", "slack", "support.json")
    r = client.post("/api/sources/connect", headers=_bearer(tok), json={
        "kind": "slack", "name": "globex #support",
        "config": {"fixture_path": fixture, "acl_groups": ["support-team"]},
    })
    sid = r.json()["id"]
    synced = client.post(f"/api/sources/{sid}/sync", headers=_bearer(tok)).json()
    assert synced["inserted"] >= 1  # landed real artifacts


def test_tenant_cannot_sync_or_delete_another_orgs_source(client, org_b):
    # a source owned by the DEFAULT org (no token)
    r = client.post("/api/sources/connect", json={"kind": "manual", "name": "default-only"})
    default_sid = r.json()["id"]
    tok_b = org_b["tokens"]["agent-token"]
    # org B cannot sync or delete it → 404 (not even existence is leaked)
    assert client.post(f"/api/sources/{default_sid}/sync", headers=_bearer(tok_b)).status_code == 404
    assert client.delete(f"/api/sources/{default_sid}", headers=_bearer(tok_b)).status_code == 404


def test_configure_source_sets_nonsecret_config_and_strips_secrets(client, org_b):
    tok = org_b["tokens"]["agent-token"]
    v = client.post("/api/sources/connect", headers=_bearer(tok),
                    json={"kind": "github", "name": "cfg target", "secrets": {"access_token": "ghp_a"}}).json()
    # set repos, and try to sneak a credential in (must be ignored)
    r = client.post(f"/api/sources/{v['id']}/config", headers=_bearer(tok),
                    json={"repos": ["octo/hello"], "access_token": "LEAK"})
    assert r.status_code == 200, r.text
    # cross-tenant config is 404
    assert client.post(f"/api/sources/{v['id']}/config", json={"repos": ["x/y"]}).status_code == 404


def test_connectors_catalog_and_onboarding(client, org_b):
    tok = org_b["tokens"]["agent-token"]
    cat = {c["kind"]: c for c in client.get("/api/connectors").json()}
    assert cat["github"]["auth"] == "token" and cat["slack"]["auth"] == "oauth"

    ob = client.get("/api/onboarding", headers=_bearer(tok)).json()
    assert ob["org_id"] == org_b["id"]
    assert ob["sources"] >= 1  # org B connected sources above
    assert {s["key"] for s in ob["steps"]} == {"connect_source", "first_sync", "first_skill", "review"}
