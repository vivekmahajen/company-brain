"""Slack connector (M1).

For Phase 1 this reads from local fixture JSON so the demo runs offline. The
shape of `pull()` / `normalize()` is identical to a real Slack Web API
integration (conversations.history with a cursor); swap `_load()` for a real
client and the rest is unchanged.
"""
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


class SlackConnector(Connector):
    kind = "slack"

    def _load(self) -> dict:
        path = self.config.get("fixture_path") or os.path.join(
            get_settings().fixtures_dir, "slack", "support.json"
        )
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def discover(self) -> dict:
        data = self._load()
        return {"channels": [data.get("channel", "#unknown")], "message_count": len(data.get("messages", []))}

    def pull(self, since: datetime | None = None) -> list[NormalizedArtifact]:
        data = self._load()
        channel = data.get("channel", "#unknown")
        out: list[NormalizedArtifact] = []
        for m in data.get("messages", []):
            occurred = _parse_dt(m.get("occurred_at"))
            if since and occurred and occurred <= since:
                continue
            out.append(
                NormalizedArtifact(
                    external_id=m["id"],
                    kind="slack_message",
                    content_text=m.get("text", ""),
                    author=m.get("user"),
                    occurred_at=occurred,
                    raw={**m, "channel": channel},
                )
            )
        return out
