"""Zendesk connector (M1) — tickets + comments. Fixture-first dual mode (D2).

With a subdomain + (OAuth access_token | email+api_token) it pulls live via the
Zendesk REST API; otherwise the fixture. Keeps ticket status and the
customer-vs-agent author distinction in `raw`. Deepens `handle-refund`.
"""
from __future__ import annotations

from datetime import datetime

from apps.api.connectors.base import Connector, NormalizedArtifact, _parse_dt


class ZendeskConnector(Connector):
    kind = "zendesk"

    def _http_client(self):
        import httpx

        sub = self.config["subdomain"]
        token = self.config.get("access_token")
        if token:
            headers, auth = {"Authorization": f"Bearer {token}"}, None
        else:  # API-token (Basic) auth: "{email}/token:{api_token}"
            headers, auth = {}, (f"{self.config.get('email','')}/token", self.config.get("api_token", ""))
        return httpx.Client(base_url=f"https://{sub}.zendesk.com/api/v2", timeout=30,
                            headers=headers, auth=auth)

    def _records(self) -> dict:
        sub = self.config.get("subdomain")
        has_cred = self.config.get("access_token") or self.config.get("api_token")
        if sub and has_cred:
            return self._live_records()
        if self.config.get("mode") == "live":
            raise RuntimeError("live Zendesk mode requires a subdomain + API token (or OAuth)")
        return self._load_fixture("tickets.json")

    def _live_records(self) -> dict:
        maxn = int(self.config.get("max_tickets", 50))
        with self._http_client() as client:
            def get(path, params=None):
                r = client.get(path, params=params or {})
                r.raise_for_status()
                return r.json()

            data = get("/tickets.json", {"per_page": min(100, maxn)})
            tickets = []
            for t in data.get("tickets", [])[:maxn]:
                comments = []
                for c in get(f"/tickets/{t['id']}/comments.json").get("comments", []):
                    comments.append({"id": c["id"], "body": c.get("body", ""),
                                     "updated_at": c.get("created_at"), "author": c.get("author_id"),
                                     "author_role": None})
                tickets.append({"id": t["id"], "subject": t.get("subject", ""),
                                "description": t.get("description", ""), "updated_at": t.get("updated_at"),
                                "requester": t.get("requester_id"), "status": t.get("status"),
                                "comments": comments})
            return {"brand": self.config["subdomain"], "tickets": tickets}

    def discover(self) -> dict:
        d = self._records()
        return {"brand": d.get("brand"), "tickets": len(d.get("tickets", []))}

    def pull_acls(self) -> dict:
        return self._native_groups(["support-team"])

    def pull(self, since: datetime | None = None) -> list[NormalizedArtifact]:
        d = self._records()
        out: list[NormalizedArtifact] = []
        for t in d.get("tickets", []):
            occ = _parse_dt(t.get("updated_at"))
            if self._since_ok(since, occ):
                out.append(NormalizedArtifact(
                    external_id=f"zd-ticket-{t['id']}", kind="zendesk_ticket",
                    content_text=f"{t.get('subject','')}\n{t.get('description','')}",
                    author=t.get("requester"), occurred_at=occ, raw={**t, "status": t.get("status")}))
            for c in t.get("comments", []):
                cocc = _parse_dt(c.get("updated_at"))
                if self._since_ok(since, cocc):
                    out.append(NormalizedArtifact(
                        external_id=f"zd-comment-{c['id']}", kind="zendesk_comment",
                        content_text=c.get("body", ""), author=c.get("author"), occurred_at=cocc,
                        raw={**c, "ticket_id": t["id"], "author_role": c.get("author_role")}))
        return out
