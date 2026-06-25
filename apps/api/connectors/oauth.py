"""OAuth scaffolding for connectors — Phase 2, Slice 2.

The "Connect your Slack" flow:
  1. GET /api/connect/{kind}/authorize  → we build the provider's consent URL with a
     signed `state` that binds the flow to the initiating tenant, and redirect the user.
  2. provider redirects back to /api/connect/{kind}/callback?code=…&state=…
  3. we verify `state`, exchange `code` for an access token, store it in the vault, and
     create the tenant's source.

Real token exchange needs a registered OAuth app (client id/secret) per provider — read
from env (`OAUTH_<KIND>_CLIENT_ID` / `_CLIENT_SECRET`) and a public `OAUTH_REDIRECT_BASE`.
Until those are set, `authorize` honestly reports `configured: false` instead of faking it.

`state` is sealed with the credential vault (authenticated + opaque) and carries an
expiry, so the callback — which arrives with no Authorization header — can still resolve
the right tenant and reject tampered/expired flows.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from apps.api.config import get_settings
from apps.api.secrets.vault import get_vault

_STATE_TTL_SECONDS = 600  # an OAuth round-trip is short


@dataclass(frozen=True)
class OAuthProvider:
    authorize_url: str
    token_url: str
    scopes: list[str]
    auth_style: str = "body"        # "body" (client creds in form) | "basic" (Basic auth)
    token_field: str = "access_token"
    extra_authorize: dict = field(default_factory=dict)


# Keyed by *connector kind*. gmail uses Google's endpoints.
PROVIDERS: dict[str, OAuthProvider] = {
    "slack": OAuthProvider(
        "https://slack.com/oauth/v2/authorize",
        "https://slack.com/api/oauth.v2.access",
        ["channels:history", "channels:read", "groups:history"],
    ),
    "github": OAuthProvider(
        "https://github.com/login/oauth/authorize",
        "https://github.com/login/oauth/access_token",
        ["repo", "read:org"],
    ),
    "gmail": OAuthProvider(
        "https://accounts.google.com/o/oauth2/v2/auth",
        "https://oauth2.googleapis.com/token",
        ["https://www.googleapis.com/auth/gmail.readonly"],
        extra_authorize={"access_type": "offline", "prompt": "consent"},
    ),
    "notion": OAuthProvider(
        "https://api.notion.com/v1/oauth/authorize",
        "https://api.notion.com/v1/oauth/token",
        [],
        auth_style="basic",
        extra_authorize={"owner": "user"},
    ),
    "linear": OAuthProvider(
        "https://linear.app/oauth/authorize",
        "https://api.linear.app/oauth/token",
        ["read"],
    ),
}


def supports_oauth(kind: str) -> bool:
    return kind in PROVIDERS


def _client_creds(kind: str) -> tuple[str | None, str | None]:
    up = kind.upper()
    return os.environ.get(f"OAUTH_{up}_CLIENT_ID"), os.environ.get(f"OAUTH_{up}_CLIENT_SECRET")


def needed_env(kind: str) -> list[str]:
    up = kind.upper()
    return [f"OAUTH_{up}_CLIENT_ID", f"OAUTH_{up}_CLIENT_SECRET", "OAUTH_REDIRECT_BASE"]


def is_configured(kind: str) -> bool:
    cid, csec = _client_creds(kind)
    return bool(supports_oauth(kind) and cid and csec and get_settings().oauth_redirect_base)


def redirect_uri(kind: str) -> str:
    base = (get_settings().oauth_redirect_base or "").rstrip("/")
    return f"{base}/api/connect/{kind}/callback"


# --- signed state (tenant binding + CSRF + expiry) ------------------------
def seal_state(org_id: str, kind: str) -> str:
    return get_vault().encrypt({"org": org_id, "kind": kind, "exp": int(time.time()) + _STATE_TTL_SECONDS})


def unseal_state(state: str, kind: str) -> str:
    """Return the org_id encoded in `state`, or raise ValueError on tamper/expiry/mismatch."""
    data = get_vault().decrypt(state)  # raises on tamper
    if data.get("kind") != kind:
        raise ValueError("state/provider mismatch")
    if int(data.get("exp", 0)) < int(time.time()):
        raise ValueError("state expired")
    return data["org"]


# --- authorize URL --------------------------------------------------------
def authorize_url(kind: str, state: str) -> str:
    from urllib.parse import urlencode

    p = PROVIDERS[kind]
    cid, _ = _client_creds(kind)
    params = {
        "client_id": cid,
        "redirect_uri": redirect_uri(kind),
        "response_type": "code",
        "state": state,
        **p.extra_authorize,
    }
    if p.scopes:
        params["scope"] = " ".join(p.scopes)
    return f"{p.authorize_url}?{urlencode(params)}"


# --- token exchange (the one network call) --------------------------------
def exchange_code(kind: str, code: str) -> dict:
    """Exchange an auth code for a credentials dict to store in the vault.

    Isolated so tests can monkeypatch it; the real path hits the provider's token URL.
    """
    import httpx

    p = PROVIDERS[kind]
    cid, csec = _client_creds(kind)
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(kind)}
    headers = {"Accept": "application/json"}
    auth = None
    if p.auth_style == "basic":
        auth = (cid, csec)
    else:
        data["client_id"], data["client_secret"] = cid, csec

    with httpx.Client(timeout=20) as client:
        r = client.post(p.token_url, data=data, headers=headers, auth=auth)
        r.raise_for_status()
        body = r.json()
    token = body.get(p.token_field)
    if not token:
        raise ValueError(f"no {p.token_field} in token response for {kind}")
    secrets = {"access_token": token}
    if body.get("refresh_token"):
        secrets["refresh_token"] = body["refresh_token"]
    return secrets
