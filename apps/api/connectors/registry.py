"""Connector registry. Slack + Notion + GitHub/Linear/Gmail/Postgres/Transcript/
Zendesk are real (fixture-first dual mode); `manual` is push-only. Nothing
downstream special-cases a source kind (D1)."""
from __future__ import annotations

from datetime import datetime

from apps.api.connectors.base import Connector, NormalizedArtifact
from apps.api.connectors.github import GitHubConnector
from apps.api.connectors.gmail import GmailConnector
from apps.api.connectors.linear import LinearConnector
from apps.api.connectors.notion import NotionConnector
from apps.api.connectors.postgres import PostgresReaderConnector
from apps.api.connectors.slack import SlackConnector
from apps.api.connectors.transcript import TranscriptConnector
from apps.api.connectors.zendesk import ZendeskConnector


class ManualConnector(Connector):
    """Manual console entry; artifacts are pushed in directly, not pulled."""

    kind = "manual"

    def discover(self) -> dict:
        return {"kind": "manual"}

    def pull(self, since: datetime | None = None) -> list[NormalizedArtifact]:
        return []


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
