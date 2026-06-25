"""GitHub connector (M1) — issues, PRs, comments, discussions, and repo docs
(runbooks / postmortems). Fixture-first dual mode (D2): with an access_token in
config (merged from the vault at sync time) it pulls live from the REST API;
otherwise it reads the bundled fixture. Unlocks `respond-to-incident`.
"""
from __future__ import annotations

from datetime import datetime

from apps.api.connectors.base import Connector, NormalizedArtifact, _parse_dt

_API = "https://api.github.com"


class GitHubConnector(Connector):
    kind = "github"

    # -- HTTP seam (overridden in tests with an httpx.MockTransport) ----------
    def _http_client(self, token: str):
        import httpx

        return httpx.Client(
            base_url=_API,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30,
        )

    def _records(self) -> dict:
        token = self.config.get("access_token")
        if token:
            return self._live_records(token)
        if self.config.get("mode") == "live":
            raise RuntimeError("live GitHub mode requires an access_token (connect via OAuth)")
        return self._load_fixture("incident.json")

    # -- live pull (real REST API) -------------------------------------------
    def _live_records(self, token: str) -> dict:
        max_issues = int(self.config.get("max_issues", 50))
        want_comments = self.config.get("with_comments", True)
        with self._http_client(token) as client:
            def api(path, params=None):
                r = client.get(path, params=params or {})
                if r.status_code in (401, 403):
                    raise RuntimeError(f"GitHub auth failed ({r.status_code}) — token invalid or missing scope")
                r.raise_for_status()
                return r.json()

            repos = self.config.get("repos")
            if not repos:  # auto-pick the most recently pushed accessible repo
                mine = api("/user/repos", {"per_page": 100, "sort": "pushed"})
                repos = [r["full_name"] for r in mine][:1]
            if not repos:
                return {"repo": None, "private": True, "issues": [], "docs": []}

            full = repos[0]
            owner, name = full.split("/", 1)
            meta = api(f"/repos/{owner}/{name}")
            private = bool(meta.get("private", True))

            issues, page = [], 1
            while len(issues) < max_issues:
                batch = api(f"/repos/{owner}/{name}/issues", {"state": "all", "per_page": 50, "page": page})
                if not batch:
                    break
                for it in batch:
                    if "pull_request" in it:  # the issues endpoint also lists PRs; skip them
                        continue
                    comments = []
                    if want_comments and it.get("comments", 0):
                        for c in api(f"/repos/{owner}/{name}/issues/{it['number']}/comments", {"per_page": 50}):
                            comments.append({"id": f"{it['number']}-{c['id']}", "body": c.get("body", ""),
                                             "author": (c.get("user") or {}).get("login"),
                                             "updated_at": c.get("updated_at")})
                    issues.append({"number": it["number"], "title": it.get("title", ""),
                                   "body": it.get("body") or "", "author": (it.get("user") or {}).get("login"),
                                   "updated_at": it.get("updated_at"), "comments": comments})
                    if len(issues) >= max_issues:
                        break
                page += 1
            return {"repo": full, "private": private, "issues": issues, "docs": []}

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
