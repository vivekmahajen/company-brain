"""M1 — Connector interface.

Connectors pull raw artifacts (first sync + incrementally), normalize to the
`artifact` shape, and never lose provenance. Sync is idempotent: re-running adds
only new artifacts (dedupe on content_hash + unique external_id).
"""
from __future__ import annotations

import abc
import hashlib
from dataclasses import dataclass, field
from datetime import datetime


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
        groups that can access this source. Default: none ⇒ default-deny (VIS-1)."""
        return {"groups": []}
