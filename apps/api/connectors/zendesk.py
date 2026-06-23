"""Zendesk connector (M1) — tickets + comments. Keeps ticket status and the
customer-vs-agent author distinction in `raw`. Deepens `handle-refund`."""
from __future__ import annotations

from datetime import datetime

from apps.api.connectors.base import Connector, NormalizedArtifact, _parse_dt


class ZendeskConnector(Connector):
    kind = "zendesk"

    def _records(self) -> dict:
        if self.config.get("mode") == "live":  # pragma: no cover
            raise RuntimeError("live Zendesk mode requires a subdomain + API token")
        return self._load_fixture("tickets.json")

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
                    author=t.get("requester"), occurred_at=occ,
                    raw={**t, "status": t.get("status")}))
            for c in t.get("comments", []):
                cocc = _parse_dt(c.get("updated_at"))
                if self._since_ok(since, cocc):
                    out.append(NormalizedArtifact(
                        external_id=f"zd-comment-{c['id']}", kind="zendesk_comment",
                        content_text=c.get("body", ""), author=c.get("author"), occurred_at=cocc,
                        raw={**c, "ticket_id": t["id"], "author_role": c.get("author_role")}))
        return out
