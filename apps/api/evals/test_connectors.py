"""Connector acceptance (§8): fixture mode, incremental, ACL mirroring, and the
Postgres reader's read-only guard + live fact resolution."""
from datetime import datetime, timezone

import pytest

from apps.api.connectors.postgres import PostgresReaderConnector, ReadOnlyViolation
from apps.api.connectors.registry import get_connector

KINDS = ["github", "linear", "gmail", "postgres", "transcript", "zendesk"]


def _config(kind):
    import os

    from apps.api.config import get_settings

    files = {"github": "github/incident.json", "linear": "linear/incidents.json",
             "gmail": "gmail/deal-desk.json", "postgres": "postgres/pricing.json",
             "transcript": "transcript/sales-call.json", "zendesk": "zendesk/tickets.json"}
    return {"fixture_path": os.path.join(get_settings().fixtures_dir, files[kind]), "acl_groups": ["eng-team"]}


@pytest.mark.parametrize("kind", KINDS)
def test_pull_yields_artifacts_with_provenance(kind):
    conn = get_connector(kind, _config(kind))
    arts = conn.pull(since=None)
    assert arts, f"{kind} produced no artifacts"
    for a in arts:
        assert a.external_id and a.kind and a.content_text and a.content_hash
        assert a.occurred_at is not None  # real timestamps (D4)


@pytest.mark.parametrize("kind", KINDS)
def test_incremental_returns_only_new(kind):
    conn = get_connector(kind, _config(kind))
    future = datetime(2030, 1, 1, tzinfo=timezone.utc)
    assert conn.pull(since=future) == []  # nothing newer than the future


@pytest.mark.parametrize("kind", KINDS)
def test_acl_mirroring_with_override(kind):
    conn = get_connector(kind, _config(kind))
    assert conn.pull_acls()["groups"] == ["eng-team"]  # config override honored (D5)


def test_acl_default_deny_without_config():
    # Postgres has no native doc ACL → default-deny (VIS-1).
    conn = get_connector("postgres", {"fixture_path": _config("postgres")["fixture_path"]})
    assert conn.pull_acls()["groups"] == []


def test_postgres_is_read_only():
    with pytest.raises(ReadOnlyViolation):
        PostgresReaderConnector.assert_readonly("UPDATE orders SET amount = 0")
    with pytest.raises(ReadOnlyViolation):
        PostgresReaderConnector.assert_readonly("DELETE FROM orders")
    PostgresReaderConnector.assert_readonly("SELECT * FROM orders")  # allowed


def test_postgres_resolves_live_facts():
    conn = get_connector("postgres", _config("postgres"))
    facts = conn.resolve_facts("1234")
    assert facts and facts["amount"] == 620 and facts["age_days"] == 40


def test_gmail_strips_quotes_and_signature():
    arts = get_connector("gmail", _config("gmail")).pull()
    body = arts[0].content_text
    assert "Never approve a discount above 50%" in body
    assert "Deal Desk" not in body  # signature stripped
    assert "> Can we get a discount" not in body  # quoted reply stripped
