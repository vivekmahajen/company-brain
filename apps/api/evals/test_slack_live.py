"""Phase-2 Slice 4: live Slack pull. Slack Web API mocked with httpx.MockTransport —
real cursor pagination, message filtering, channel selection, and ACL mirroring are
exercised offline. Fixture path unchanged."""
from __future__ import annotations

import httpx
import pytest

from apps.api.connectors.slack import SlackConnector

_CHANNELS = [{"id": "C100", "name": "support", "is_private": True},
             {"id": "C200", "name": "general", "is_private": False}]

_HISTORY = {
    "C100": [
        {"type": "message", "user": "U1", "text": "refunds within 30 days auto-approve", "ts": "1610000000.0001"},
        {"type": "message", "subtype": "channel_join", "user": "U2", "text": "joined", "ts": "1610000001.0001"},
        {"type": "message", "user": "U3", "text": "refunds above $500 require manager sign-off", "ts": "1610000002.0001"},
    ],
    "C200": [{"type": "message", "user": "U9", "text": "good morning team", "ts": "1610000100.0001"}],
}


def _handler(req: httpx.Request) -> httpx.Response:
    path = req.url.path.rsplit("/", 1)[-1]
    if path in ("conversations.list", "users.conversations"):
        return httpx.Response(200, json={"ok": True, "channels": _CHANNELS})
    if path == "conversations.history":
        cid = req.url.params.get("channel")
        return httpx.Response(200, json={"ok": True, "messages": _HISTORY.get(cid, []),
                                         "response_metadata": {"next_cursor": ""}})
    return httpx.Response(200, json={"ok": False, "error": "unknown_method"})


def _connector(config):
    c = SlackConnector(config)
    c._http_client = lambda token: httpx.Client(  # type: ignore[method-assign]
        base_url="https://slack.com/api", transport=httpx.MockTransport(_handler))
    return c


def test_live_pull_normalizes_messages_and_skips_system_subtypes():
    c = _connector({"access_token": "xoxb-x", "channels": ["support"]})
    arts = c.pull()
    texts = [a.content_text for a in arts]
    assert "refunds within 30 days auto-approve" in texts
    assert "refunds above $500 require manager sign-off" in texts
    assert all(a.kind == "slack_message" for a in arts)
    # the channel_join system message is filtered out
    assert "joined" not in texts
    assert arts[0].external_id.startswith("C100-")


def test_live_autodiscovers_channels_when_unset():
    c = _connector({"access_token": "xoxb-x"})  # no channels → users.conversations
    chans = {a.raw["channel"] for a in c.pull()}
    assert "#support" in chans and "#general" in chans


def test_live_acl_mirrors_channel_privacy():
    priv = _connector({"access_token": "x", "channels": ["support"]})   # private
    pub = _connector({"access_token": "x", "channels": ["general"]})    # public
    assert priv.pull_acls()["groups"] == ["support-team"]
    assert pub.pull_acls()["groups"] == ["all-staff"]
    # explicit config override wins
    over = _connector({"access_token": "x", "channels": ["support"], "acl_groups": ["legal-team"]})
    assert over.pull_acls()["groups"] == ["legal-team"]


def test_live_auth_error_raises():
    c = SlackConnector({"access_token": "bad", "channels": ["support"]})
    c._http_client = lambda token: httpx.Client(
        base_url="https://slack.com/api",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": False, "error": "invalid_auth"})))
    with pytest.raises(RuntimeError, match="invalid_auth"):
        c.pull()


def test_fixture_path_unchanged_without_token():
    c = SlackConnector({})
    arts = c.pull()
    assert arts and all(a.kind == "slack_message" for a in arts)
    assert c.pull_acls()["groups"] == ["support-team"]


def test_full_path_vault_to_live_pull_to_acl_mirror(seeded, db, monkeypatch):
    from sqlalchemy import select

    from apps.api.models.access import Group, SourceACL
    from apps.api.services.connections import connect_source, sync_tenant_source
    from apps.api.services.orgs import create_org

    monkeypatch.setattr(SlackConnector, "_http_client",
                        lambda self, token: httpx.Client(base_url="https://slack.com/api",
                                                         transport=httpx.MockTransport(_handler)))
    org = create_org(db, name="SlackCo")["id"]
    view = connect_source(db, org, kind="slack", name="acme workspace",
                          config={"channels": ["support"]}, secrets={"access_token": "xoxb-real"})
    res = sync_tenant_source(db, org, view["id"])
    assert res["inserted"] >= 2  # two real messages from #support

    eng = db.scalar(select(Group).where(Group.org_id == org, Group.name == "support-team"))
    acl = db.scalar(select(SourceACL).where(SourceACL.org_id == org, SourceACL.source_id == view["id"],
                                            SourceACL.subject_id == eng.id))
    assert acl is not None and acl.access == "allow"
