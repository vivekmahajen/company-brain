"""Connector registry. Phase 1: Slack + Notion real; the rest are stubbed behind
the same ABC so Phase 2 only fills in `pull()`."""
from __future__ import annotations

from datetime import datetime

from apps.api.connectors.base import Connector, NormalizedArtifact
from apps.api.connectors.notion import NotionConnector
from apps.api.connectors.slack import SlackConnector


class _Stub(Connector):
    def discover(self) -> dict:
        return {"stub": True, "kind": self.kind}

    def pull(self, since: datetime | None = None) -> list[NormalizedArtifact]:
        return []


class GmailConnector(_Stub):
    kind = "gmail"


class GitHubConnector(_Stub):
    kind = "github"


class LinearConnector(_Stub):
    kind = "linear"


class ZendeskConnector(_Stub):
    kind = "zendesk"


class PostgresReaderConnector(_Stub):
    kind = "postgres"


class TranscriptConnector(_Stub):
    kind = "transcript"


class ManualConnector(_Stub):
    """Manual console entry; artifacts are pushed in directly, not pulled."""

    kind = "manual"


REGISTRY: dict[str, type[Connector]] = {
    "slack": SlackConnector,
    "notion": NotionConnector,
    "gmail": GmailConnector,
    "github": GitHubConnector,
    "linear": LinearConnector,
    "zendesk": ZendeskConnector,
    "postgres": PostgresReaderConnector,
    "transcript": TranscriptConnector,
    "manual": ManualConnector,
}


def get_connector(kind: str, config: dict | None = None) -> Connector:
    cls = REGISTRY.get(kind)
    if not cls:
        raise ValueError(f"Unknown connector kind: {kind}")
    return cls(config)
