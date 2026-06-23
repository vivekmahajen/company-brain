"""GitHub connector (M1) — issues, PRs, comments, discussions, and repo docs
(runbooks / postmortems). Fixture-first dual mode (D2); swap `_records()` for the
REST/GraphQL client in live mode. Unlocks `respond-to-incident`.
"""
from __future__ import annotations

from datetime import datetime

from apps.api.connectors.base import Connector, NormalizedArtifact, _parse_dt


class GitHubConnector(Connector):
    kind = "github"

    def _records(self) -> dict:
        if self.config.get("mode") == "live":  # pragma: no cover - needs a token
            raise RuntimeError("live GitHub mode requires GITHUB_TOKEN + repo config")
        return self._load_fixture("incident.json")

    def discover(self) -> dict:
        d = self._records()
        return {"repo": d.get("repo"), "private": d.get("private", True),
                "issues": len(d.get("issues", [])), "docs": len(d.get("docs", []))}

    def pull_acls(self) -> dict:
        d = self._records()
        # private repo → team group; public → all-staff (mirrored from repo access)
        native = ["eng-team"] if d.get("private", True) else ["all-staff"]
        return self._native_groups(native)

    def pull(self, since: datetime | None = None) -> list[NormalizedArtifact]:
        d = self._records()
        repo = d.get("repo", "acme/repo")
        out: list[NormalizedArtifact] = []
        for issue in d.get("issues", []):
            occ = _parse_dt(issue.get("updated_at"))
            if self._since_ok(since, occ):
                out.append(NormalizedArtifact(
                    external_id=f"gh-issue-{repo}#{issue['number']}", kind="github_issue",
                    content_text=f"{issue.get('title','')}\n{issue.get('body','')}",
                    author=issue.get("author"), occurred_at=occ,
                    raw={**issue, "repo": repo}))
            for c in issue.get("comments", []):
                cocc = _parse_dt(c.get("updated_at"))
                if self._since_ok(since, cocc):
                    out.append(NormalizedArtifact(
                        external_id=f"gh-comment-{c['id']}", kind="github_comment",
                        content_text=c.get("body", ""), author=c.get("author"), occurred_at=cocc,
                        raw={**c, "repo": repo, "issue_number": issue["number"]}))
        for doc in d.get("docs", []):  # runbooks / postmortems are documents
            occ = _parse_dt(doc.get("updated_at"))
            if self._since_ok(since, occ):
                out.append(NormalizedArtifact(
                    external_id=f"gh-doc-{repo}-{doc['path']}", kind="github_doc",
                    content_text=f"{doc.get('title','')}\n{doc.get('content','')}",
                    author=doc.get("author"), occurred_at=occ, raw={**doc, "repo": repo}))
        return out
