"""Gmail connector (M1) — messages, thread-aware, with reply-chain + signature
stripping so the same approval isn't double-counted across replies. Fixture-first
dual mode (D2): with an OAuth access_token it pulls live via the Gmail API. Mailbox
is sensitive: ACL mirrors to the owner's group only (default-deny otherwise).
Unlocks `handle-pricing-exception`.
"""
from __future__ import annotations

import base64
import re
from datetime import datetime
from email.utils import parsedate_to_datetime

from apps.api.connectors.base import Connector, NormalizedArtifact, _parse_dt

_QUOTE = re.compile(r"^\s*>.*$", re.M)
_ON_WROTE = re.compile(r"On .+ wrote:.*$", re.S)
_SIG = re.compile(r"\n--\s*\n.*$", re.S)
_API = "https://gmail.googleapis.com/gmail/v1"


def _strip(body: str) -> str:
    body = _ON_WROTE.sub("", body)
    body = _QUOTE.sub("", body)
    body = _SIG.sub("", body)
    return "\n".join(line for line in body.splitlines() if line.strip()).strip()


class GmailConnector(Connector):
    kind = "gmail"

    def _http_client(self, token: str):
        import httpx

        return httpx.Client(base_url=_API, timeout=30, headers={"Authorization": f"Bearer {token}"})

    def _records(self) -> dict:
        token = self.config.get("access_token")
        if token:
            return self._live_records(token)
        if self.config.get("mode") == "live":
            raise RuntimeError("live Gmail mode requires an OAuth access_token (read-only scope)")
        return self._load_fixture("deal-desk.json")

    def _live_records(self, token: str) -> dict:
        maxn = int(self.config.get("max_messages", 50))
        q = self.config.get("query", "")
        with self._http_client(token) as client:
            params = {"maxResults": maxn}
            if q:
                params["q"] = q
            lst = client.get("/users/me/messages", params=params)
            lst.raise_for_status()
            messages = []
            for ref in lst.json().get("messages", [])[:maxn]:
                full = client.get(f"/users/me/messages/{ref['id']}", params={"format": "full"})
                full.raise_for_status()
                msg = full.json()
                hdrs = {h["name"].lower(): h["value"] for h in (msg.get("payload") or {}).get("headers", [])}
                date_iso = None
                if hdrs.get("date"):
                    try:
                        date_iso = parsedate_to_datetime(hdrs["date"]).isoformat()
                    except (TypeError, ValueError):
                        date_iso = None
                messages.append({"id": ref["id"], "thread_id": msg.get("threadId"),
                                 "from": hdrs.get("from"), "subject": hdrs.get("subject", ""),
                                 "date": date_iso, "body": self._body(msg.get("payload") or {})})
            return {"mailbox": self.config.get("mailbox", "me"),
                    "owner_group": self.config.get("owner_group", "sales-team"), "messages": messages}

    @staticmethod
    def _body(payload: dict) -> str:
        def walk(p):
            if p.get("mimeType") == "text/plain" and (p.get("body") or {}).get("data"):
                raw = p["body"]["data"]
                return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8", "replace")
            for part in p.get("parts") or []:
                t = walk(part)
                if t:
                    return t
            return ""
        return walk(payload)

    def discover(self) -> dict:
        d = self._records()
        return {"mailbox": d.get("mailbox"), "messages": len(d.get("messages", []))}

    def pull_acls(self) -> dict:
        d = self._records()
        return self._native_groups([d.get("owner_group", "sales-team")])  # owner's group only

    def pull(self, since: datetime | None = None) -> list[NormalizedArtifact]:
        d = self._records()
        out: list[NormalizedArtifact] = []
        for m in d.get("messages", []):
            occ = _parse_dt(m.get("date"))
            if not self._since_ok(since, occ):
                continue
            out.append(NormalizedArtifact(
                external_id=f"gmail-{m['id']}", kind="email",
                content_text=f"{m.get('subject','')}\n{_strip(m.get('body',''))}",
                author=m.get("from"), occurred_at=occ,
                raw={**m, "thread_id": m.get("thread_id"), "mailbox": d.get("mailbox")}))
        return out
