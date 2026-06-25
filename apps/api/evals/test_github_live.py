"""Phase-2 Slice 3: live GitHub pull. The network is mocked with httpx.MockTransport
so the REST parsing, pagination, PR-skipping, ACL mirroring, and the full
vault→live-pull→ACL path are all exercised offline. The fixture path still works."""
from __future__ import annotations

import httpx
import pytest

from apps.api.connectors.github import GitHubConnector


def _handler(private=True):
    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if p == "/user/repos":
            return httpx.Response(200, json=[{"full_name": "acme/platform"}])
        if p == "/repos/acme/platform":
            return httpx.Response(200, json={"private": private})
        if p == "/repos/acme/platform/issues":
            if request.url.params.get("page") == "1":
                return httpx.Response(200, json=[
                    {"number": 7, "title": "Sev1 checkout outage",
                     "body": "Never deploy during an active incident.",
                     "user": {"login": "alice"}, "updated_at": "2026-03-01T00:00:00Z", "comments": 1},
                    {"number": 8, "title": "a pull request", "pull_request": {"url": "x"},
                     "user": {"login": "bob"}, "updated_at": "2026-03-02T00:00:00Z", "comments": 0},
                ])
            return httpx.Response(200, json=[])
        if p == "/repos/acme/platform/issues/7/comments":
            return httpx.Response(200, json=[
                {"id": 555, "body": "postmortem posted", "user": {"login": "carol"},
                 "updated_at": "2026-03-03T00:00:00Z"}])
        return httpx.Response(404, json={})
    return handler


def _connector(config, private=True):
    c = GitHubConnector(config)
    c._http_client = lambda token: httpx.Client(  # type: ignore[method-assign]
        base_url="https://api.github.com", transport=httpx.MockTransport(_handler(private)))
    return c


def test_live_pull_normalizes_issues_and_comments_and_skips_prs():
    c = _connector({"access_token": "ghp_x", "repos": ["acme/platform"]})
    arts = c.pull()
    kinds = [a.kind for a in arts]
    assert "github_issue" in kinds and "github_comment" in kinds
    issue = next(a for a in arts if a.kind == "github_issue")
    assert "Sev1 checkout outage" in issue.content_text and issue.author == "alice"
    # the PR (#8) must be skipped — only one issue
    assert kinds.count("github_issue") == 1
    comment = next(a for a in arts if a.kind == "github_comment")
    assert "postmortem posted" in comment.content_text


def test_live_pull_autodiscovers_repo_when_unset():
    c = _connector({"access_token": "ghp_x"})  # no repos → /user/repos
    arts = c.pull()
    assert any(a.kind == "github_issue" for a in arts)


def test_live_acl_mirrors_repo_visibility():
    priv = _connector({"access_token": "ghp_x", "repos": ["acme/platform"]}, private=True)
    pub = _connector({"access_token": "ghp_x", "repos": ["acme/platform"]}, private=False)
    assert priv.pull_acls()["groups"] == ["eng-team"]      # private → restricted
    assert pub.pull_acls()["groups"] == ["all-staff"]      # public → broad


def test_live_auth_failure_raises_clearly():
    c = GitHubConnector({"access_token": "bad", "repos": ["acme/platform"]})
    c._http_client = lambda token: httpx.Client(  # type: ignore[method-assign]
        base_url="https://api.github.com",
        transport=httpx.MockTransport(lambda req: httpx.Response(401, json={})))
    with pytest.raises(RuntimeError, match="auth failed"):
        c.pull()


def test_fixture_path_still_works_without_a_token():
    c = GitHubConnector({})  # no token, no live mode → bundled fixture
    arts = c.pull()
    assert arts and all(a.kind.startswith("github_") for a in arts)


def test_full_path_vault_to_live_pull_to_acl_mirror(seeded, db, monkeypatch):
    """End-to-end through the service: connect a github source with a vaulted token,
    sync it (live pull, mocked), and confirm artifacts land + ACLs mirror to eng-team."""
    from sqlalchemy import select

    from apps.api.models.access import Group, SourceACL
    from apps.api.services.connections import connect_source, sync_tenant_source
    from apps.api.services.orgs import create_org

    # patch the HTTP seam for every GitHubConnector the registry builds
    monkeypatch.setattr(GitHubConnector, "_http_client",
                        lambda self, token: httpx.Client(base_url="https://api.github.com",
                                                         transport=httpx.MockTransport(_handler(private=True))))
    org = create_org(db, name="LivePull Inc")["id"]
    view = connect_source(db, org, kind="github", name="acme/platform (live)",
                          config={"repos": ["acme/platform"]}, secrets={"access_token": "ghp_real"})
    res = sync_tenant_source(db, org, view["id"])
    assert res["inserted"] >= 2  # issue + comment landed

    # ACLs mirrored from the private repo → eng-team
    eng = db.scalar(select(Group).where(Group.org_id == org, Group.name == "eng-team"))
    acl = db.scalar(select(SourceACL).where(SourceACL.org_id == org, SourceACL.source_id == view["id"],
                                            SourceACL.subject_id == eng.id))
    assert acl is not None and acl.access == "allow"
