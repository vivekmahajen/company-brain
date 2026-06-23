"""Gmail connector (M1) — messages, thread-aware, with reply-chain + signature
stripping so the same approval isn't double-counted across replies. Mailbox is
sensitive: ACL mirrors to the owner's group only (default-deny otherwise).
Unlocks `handle-pricing-exception`."""
from __future__ import annotations

import re
from datetime import datetime

from apps.api.connectors.base import Connector, NormalizedArtifact, _parse_dt

_QUOTE = re.compile(r"^\s*>.*$", re.M)
_ON_WROTE = re.compile(r"On .+ wrote:.*$", re.S)
_SIG = re.compile(r"\n--\s*\n.*$", re.S)


def _strip(body: str) -> str:
    body = _ON_WROTE.sub("", body)
    body = _QUOTE.sub("", body)
    body = _SIG.sub("", body)
    return "\n".join(line for line in body.splitlines() if line.strip()).strip()


class GmailConnector(Connector):
    kind = "gmail"

    def _records(self) -> dict:
        if self.config.get("mode") == "live":  # pragma: no cover - needs OAuth
            raise RuntimeError("live Gmail mode requires OAuth (read-only scope)")
        return self._load_fixture("deal-desk.json")

    def discover(self) -> dict:
        d = self._records()
        return {"mailbox": d.get("mailbox"), "messages": len(d.get("messages", []))}

    def pull_acls(self) -> dict:
        d = self._records()
        owner_group = d.get("owner_group", "sales-team")  # mailbox owner's group only
        return self._native_groups([owner_group])

    def pull(self, since: datetime | None = None) -> list[NormalizedArtifact]:
        d = self._records()
        out: list[NormalizedArtifact] = []
        for m in d.get("messages", []):
            occ = _parse_dt(m.get("date"))
            if not self._since_ok(since, occ):
                continue
            text = f"{m.get('subject','')}\n{_strip(m.get('body',''))}"
            out.append(NormalizedArtifact(
                external_id=f"gmail-{m['id']}", kind="email", content_text=text,
                author=m.get("from"), occurred_at=occ,
                raw={**m, "thread_id": m.get("thread_id"), "mailbox": d.get("mailbox")}))
        return out
