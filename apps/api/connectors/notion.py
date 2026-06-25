"""Notion connector (M1). Fixture-first dual mode (D2).

With an access_token (OAuth, merged from the vault at sync) it pulls live via the
Notion API (search → block children → plain text); otherwise it reads the fixture.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from apps.api.config import get_settings
from apps.api.connectors.base import Connector, NormalizedArtifact

_API = "https://api.notion.com/v1"


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class NotionConnector(Connector):
    kind = "notion"

    def _http_client(self, token: str):
        import httpx

        return httpx.Client(base_url=_API, timeout=30, headers={
            "Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28"})

    def _load(self) -> dict:
        path = self.config.get("fixture_path") or os.path.join(
            get_settings().fixtures_dir, "notion", "refund-policy.json")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _records(self) -> dict:
        token = self.config.get("access_token")
        if token:
            return self._live_records(token)
        if self.config.get("mode") == "live":
            raise RuntimeError("live Notion mode requires an access_token (connect via OAuth)")
        return self._load()

    def _live_records(self, token: str) -> dict:
        max_pages = int(self.config.get("max_pages", 50))
        with self._http_client(token) as client:
            res = client.post("/search", json={"filter": {"property": "object", "value": "page"},
                                               "page_size": min(100, max_pages)})
            res.raise_for_status()
            pages = []
            for pg in res.json().get("results", [])[:max_pages]:
                pid = pg["id"]
                pages.append({"id": pid, "title": self._title(pg), "content": self._page_text(client, pid),
                              "last_edited": pg.get("last_edited_time"),
                              "author": (pg.get("last_edited_by") or {}).get("id")})
            return {"pages": pages}

    @staticmethod
    def _title(pg: dict) -> str:
        for v in (pg.get("properties") or {}).values():
            if v.get("type") == "title":
                return "".join(t.get("plain_text", "") for t in v.get("title", [])) or "Untitled"
        return "Untitled"

    @staticmethod
    def _page_text(client, pid: str) -> str:
        r = client.get(f"/blocks/{pid}/children", params={"page_size": 100})
        r.raise_for_status()
        lines = []
        for b in r.json().get("results", []):
            blk = b.get(b.get("type"), {})
            rich = blk.get("rich_text") if isinstance(blk, dict) else None
            if rich:
                line = "".join(t.get("plain_text", "") for t in rich)
                if line:
                    lines.append(line)
        return "\n".join(lines)

    def discover(self) -> dict:
        return {"pages": [p["title"] for p in self._records().get("pages", [])]}

    def pull_acls(self) -> dict:
        # Workspace-wide pages → all-staff (mirrored native permission); config overrides.
        return self._native_groups(["all-staff"])

    def pull(self, since: datetime | None = None) -> list[NormalizedArtifact]:
        out: list[NormalizedArtifact] = []
        for p in self._records().get("pages", []):
            edited = _parse_dt(p.get("last_edited"))
            if since and edited and edited <= since:
                continue
            out.append(NormalizedArtifact(
                external_id=p["id"], kind="notion_page",
                content_text=f"{p.get('title', '')}\n{p.get('content', '')}",
                author=p.get("author"), occurred_at=edited, raw=p))
        return out
