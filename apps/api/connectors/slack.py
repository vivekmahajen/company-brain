"""Slack connector (M1). Fixture-first dual mode (D2).

With an access_token in config (the OAuth bot token, merged from the vault at sync
time) it pulls live from the Slack Web API — the channels the token can see (or a
configured subset), via conversations.history with cursor pagination. Without a
token it reads the bundled fixture so the demo/evals run offline. Per-company Slack
= one Slack app (the vendor's), authorized into each company's workspace; the token
lands in that company's org-scoped vault.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from apps.api.config import get_settings
from apps.api.connectors.base import Connector, NormalizedArtifact

_API = "https://slack.com/api"


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _ts_to_iso(ts: str) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()


class SlackConnector(Connector):
    kind = "slack"

    # -- HTTP seam (overridden in tests with httpx.MockTransport) -------------
    def _http_client(self, token: str):
        import httpx

        return httpx.Client(base_url=_API, headers={"Authorization": f"Bearer {token}"}, timeout=30)

    # -- records: live when there's a token, else the fixture ----------------
    def _records(self) -> dict:
        token = self.config.get("access_token")
        if token:
            return self._live_records(token)
        if self.config.get("mode") == "live":
            raise RuntimeError("live Slack mode requires an access_token (connect via OAuth)")
        return self._fixture_records()

    def _fixture_records(self) -> dict:
        path = self.config.get("fixture_path") or os.path.join(
            get_settings().fixtures_dir, "slack", "support.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        # wrap the single-channel fixture into the generalized multi-channel shape
        return {"channels": [{"channel": data.get("channel", "#unknown"), "id": data.get("channel", "fixture"),
                              "is_private": True, "messages": data.get("messages", [])}]}

    def _live_records(self, token: str) -> dict:
        max_messages = int(self.config.get("max_messages", 200))
        wanted_refs = self.config.get("channels")  # list of channel ids or names; None → all the token is in
        with self._http_client(token) as client:
            def api(method, params=None):
                r = client.get(f"/{method}", params=params or {})
                r.raise_for_status()
                body = r.json()
                if not body.get("ok"):
                    raise RuntimeError(f"Slack API error on {method}: {body.get('error')}")
                return body

            if wanted_refs:
                listed = api("conversations.list",
                             {"types": "public_channel,private_channel", "limit": 1000}).get("channels", [])
                by_id = {c["id"]: c for c in listed}
                by_name = {c.get("name"): c for c in listed}
                channels = [by_id.get(ref) or by_name.get(str(ref).lstrip("#")) for ref in wanted_refs]
                channels = [c for c in channels if c]
            else:
                channels = api("users.conversations",
                               {"types": "public_channel,private_channel", "limit": 1000}).get("channels", [])

            out = []
            for ch in channels:
                cid, cname, priv = ch["id"], ch.get("name", ch["id"]), bool(ch.get("is_private", False))
                msgs, cursor = [], None
                while len(msgs) < max_messages:
                    params = {"channel": cid, "limit": min(200, max_messages - len(msgs))}
                    if cursor:
                        params["cursor"] = cursor
                    hist = api("conversations.history", params)
                    for m in hist.get("messages", []):
                        if m.get("type") != "message" or m.get("subtype"):
                            continue  # skip joins / bot / system messages
                        msgs.append({"id": f"{cid}-{m['ts']}", "text": m.get("text", ""),
                                     "user": m.get("user"), "occurred_at": _ts_to_iso(m["ts"])})
                    cursor = (hist.get("response_metadata") or {}).get("next_cursor")
                    if not cursor:
                        break
                out.append({"channel": f"#{cname}", "id": cid, "is_private": priv, "messages": msgs})
            return {"channels": out}

    # -- consumed identically by fixture + live ------------------------------
    def discover(self) -> dict:
        rec = self._records()
        return {"channels": [c["channel"] for c in rec.get("channels", [])],
                "message_count": sum(len(c.get("messages", [])) for c in rec.get("channels", []))}

    def pull_acls(self) -> dict:
        # Mirror native audience: any private channel → restricted (support-team by
        # default), all public → all-staff. config['acl_groups'] overrides.
        rec = self._records()
        any_private = any(c.get("is_private") for c in rec.get("channels", []))
        return self._native_groups(["support-team"] if any_private else ["all-staff"])

    def pull(self, since: datetime | None = None) -> list[NormalizedArtifact]:
        rec = self._records()
        out: list[NormalizedArtifact] = []
        for ch in rec.get("channels", []):
            channel = ch.get("channel", "#unknown")
            for m in ch.get("messages", []):
                occurred = _parse_dt(m.get("occurred_at"))
                if since and occurred and occurred <= since:
                    continue
                out.append(NormalizedArtifact(
                    external_id=m["id"], kind="slack_message", content_text=m.get("text", ""),
                    author=m.get("user"), occurred_at=occurred, raw={**m, "channel": channel}))
        return out
