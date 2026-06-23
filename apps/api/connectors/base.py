"""M1 — Connector interface.

Connectors pull raw artifacts (first sync + incrementally), normalize to the
`artifact` shape, and never lose provenance. Sync is idempotent: re-running adds
only new artifacts (dedupe on content_hash + unique external_id).
"""
from __future__ import annotations

import abc
import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class NormalizedArtifact:
    external_id: str
    kind: str
    content_text: str
    author: str | None = None
    occurred_at: datetime | None = None
    raw: dict = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content_text.strip().encode()).hexdigest()


class Connector(abc.ABC):
    kind: str = "base"

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}

    @abc.abstractmethod
    def discover(self) -> dict:
        """Return metadata about what is available to sync (channels, pages, ...)."""

    @abc.abstractmethod
    def pull(self, since: datetime | None = None) -> list[NormalizedArtifact]:
        """Return artifacts created/updated since `since` (None = full sync)."""

    def pull_acls(self) -> dict:
        """Mirror source-native permissions (§6). Returns {"groups": [...]} of the
        groups that can access this source. Default: none ⇒ default-deny (VIS-1).

        Honors a per-source config override (`acl_groups`) so the same connector
        kind can back sources with different native audiences (e.g. a private vs
        public repo). Subclasses fall back to their native default."""
        return {"groups": self.config.get("acl_groups", [])}

    # -- fixture-first dual mode (D2) --------------------------------------
    def _fixture_path(self, default_name: str) -> str:
        from apps.api.config import get_settings

        return self.config.get("fixture_path") or os.path.join(
            get_settings().fixtures_dir, self.kind, default_name
        )

    def _load_fixture(self, default_name: str) -> dict:
        with open(self._fixture_path(default_name), encoding="utf-8") as f:
            return json.load(f)

    def _native_groups(self, default: list[str]) -> dict:
        """Config override wins; else the connector's native default group(s)."""
        return {"groups": self.config.get("acl_groups") or default}

    @staticmethod
    def _since_ok(since: datetime | None, occurred: datetime | None) -> bool:
        return not (since and occurred and occurred <= since)
