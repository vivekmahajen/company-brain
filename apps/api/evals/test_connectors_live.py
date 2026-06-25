"""Phase-2 Slice 5: live pull for Notion, Linear, Gmail, Zendesk. Each provider's
API is mocked with httpx.MockTransport — real parsing/normalization exercised
offline. Fixture fallback preserved for all four."""
from __future__ import annotations

import base64

import httpx
import pytest

from apps.api.connectors.gmail import GmailConnector
from apps.api.connectors.linear import LinearConnector
from apps.api.connectors.notion import NotionConnector
from apps.api.connectors.zendesk import ZendeskConnector


def _mock(connector, handler):
    connector._http_client = lambda *a, **k: httpx.Client(  # type: ignore[method-assign]
        base_url="https://mock", transport=httpx.MockTransport(handler))
    return connector


# --- Notion ---------------------------------------------------------------
def _notion_handler(req):
    p = req.url.path
    if p.endswith("/search"):
        return httpx.Response(200, json={"results": [
            {"id": "pg1", "last_edited_time": "2026-01-15T00:00:00Z", "last_edited_by": {"id": "u1"},
             "properties": {"Name": {"type": "title", "title": [{"plain_text": "Refund Policy"}]}}}]})
    if "/blocks/pg1/children" in p:
        return httpx.Response(200, json={"results": [
            {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Refunds within 30 days auto-approve."}]}}]})
    return httpx.Response(404, json={})


def test_notion_live_pull():
    c = _mock(NotionConnector({"access_token": "secret_x"}), _notion_handler)
    arts = c.pull()
    assert len(arts) == 1 and arts[0].kind == "notion_page"
    assert "Refund Policy" in arts[0].content_text
    assert "Refunds within 30 days auto-approve." in arts[0].content_text


def test_notion_fixture_fallback():
    arts = NotionConnector({}).pull()
    assert arts and all(a.kind == "notion_page" for a in arts)
    assert NotionConnector({}).pull_acls()["groups"] == ["all-staff"]


# --- Linear ---------------------------------------------------------------
def _linear_handler(req):
    return httpx.Response(200, json={"data": {"issues": {"nodes": [
        {"id": "i1", "title": "Sev1 checkout outage", "description": "Never deploy during an incident.",
         "updatedAt": "2026-03-01T00:00:00Z", "priority": 1, "state": {"name": "Done"},
         "labels": {"nodes": [{"name": "incident"}]},
         "comments": {"nodes": [{"id": "c1", "body": "postmortem posted",
                                 "updatedAt": "2026-03-02T00:00:00Z", "user": {"name": "alice"}}]}}]}}})


def test_linear_live_pull():
    c = _mock(LinearConnector({"api_key": "lin_api_x"}), _linear_handler)
    arts = c.pull()
    kinds = [a.kind for a in arts]
    assert "linear_issue" in kinds and "linear_comment" in kinds
    issue = next(a for a in arts if a.kind == "linear_issue")
    assert "Sev1 checkout outage" in issue.content_text and issue.raw["labels"] == ["incident"]


def test_linear_graphql_error_raises():
    c = _mock(LinearConnector({"access_token": "t"}), lambda r: httpx.Response(200, json={"errors": [{"message": "bad"}]}))
    with pytest.raises(RuntimeError, match="Linear API error"):
        c.pull()


# --- Gmail ----------------------------------------------------------------
def _gmail_handler(req):
    p = req.url.path
    if p.endswith("/messages"):
        return httpx.Response(200, json={"messages": [{"id": "m1"}]})
    if p.endswith("/messages/m1"):
        data = base64.urlsafe_b64encode(b"Never approve a discount above 50% without CFO sign-off.").decode()
        return httpx.Response(200, json={"threadId": "t1", "payload": {
            "mimeType": "text/plain", "body": {"data": data},
            "headers": [{"name": "From", "value": "maya@acme.com"},
                        {"name": "Subject", "value": "Pricing exception"},
                        {"name": "Date", "value": "Mon, 02 Mar 2026 10:00:00 +0000"}]}})
    return httpx.Response(404, json={})


def test_gmail_live_pull():
    c = _mock(GmailConnector({"access_token": "ya29.x"}), _gmail_handler)
    arts = c.pull()
    assert len(arts) == 1 and arts[0].kind == "email"
    assert "Pricing exception" in arts[0].content_text
    assert "discount above 50%" in arts[0].content_text
    assert arts[0].author == "maya@acme.com" and arts[0].occurred_at is not None


def test_gmail_fixture_fallback_owner_acl():
    assert GmailConnector({}).pull_acls()["groups"] == ["sales-team"]  # mailbox owner only


# --- Zendesk --------------------------------------------------------------
def _zendesk_handler(req):
    p = req.url.path
    if p.endswith("/tickets.json"):
        return httpx.Response(200, json={"tickets": [
            {"id": 1, "subject": "Refund request", "description": "Never refund digital goods after key activation.",
             "updated_at": "2026-03-01T00:00:00Z", "requester_id": 99, "status": "open"}]})
    if "/tickets/1/comments.json" in p:
        return httpx.Response(200, json={"comments": [
            {"id": 11, "body": "refunds above $500 need manager sign-off", "created_at": "2026-03-02T00:00:00Z",
             "author_id": 5}]})
    return httpx.Response(404, json={})


def test_zendesk_live_pull():
    c = _mock(ZendeskConnector({"subdomain": "acme", "api_token": "tok", "email": "a@acme.com"}), _zendesk_handler)
    arts = c.pull()
    kinds = [a.kind for a in arts]
    assert "zendesk_ticket" in kinds and "zendesk_comment" in kinds
    ticket = next(a for a in arts if a.kind == "zendesk_ticket")
    assert "Refund request" in ticket.content_text and ticket.raw["status"] == "open"


def test_zendesk_fixture_fallback():
    arts = ZendeskConnector({}).pull()
    assert arts and any(a.kind == "zendesk_ticket" for a in arts)
