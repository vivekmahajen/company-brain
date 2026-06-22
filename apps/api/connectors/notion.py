"""Notion connector (M1). Reads fixture JSON for Phase 1; same shape as the real
Notion API (search + blocks.children). Swap `_load()` for a real client."""
from __future__ import annotations

import json
import os
from datetime import datetime

from apps.api.config import get_settings
from apps.api.connectors.base import Connector, NormalizedArtifact


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class NotionConnector(Connector):
    kind = "notion"

    def _load(self) -> dict:
        path = self.config.get("fixture_path") or os.path.join(
            get_settings().fixtures_dir, "notion", "refund-policy.json"
        )
        with open(path) as f:
            return json.load(f)

    def discover(self) -> dict:
        data = self._load()
        return {"pages": [p["title"] for p in data.get("pages", [])]}

    def pull(self, since: datetime | None = None) -> list[NormalizedArtifact]:
        data = self._load()
        out: list[NormalizedArtifact] = []
        for p in data.get("pages", []):
            edited = _parse_dt(p.get("last_edited"))
            if since and edited and edited <= since:
                continue
            body = f"{p.get('title', '')}\n{p.get('content', '')}"
            out.append(
                NormalizedArtifact(
                    external_id=p["id"],
                    kind="notion_page",
                    content_text=body,
                    author=p.get("author"),
                    occurred_at=edited,
                    raw=p,
                )
            )
        return out
