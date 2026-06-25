"""Linear connector (M1) — issues + comments. Fixture-first dual mode (D2).

With an api_key or OAuth access_token it pulls live via the Linear GraphQL API;
otherwise the fixture. Carries state/priority/labels in `raw`. Unlocks
`respond-to-incident`. (Jira is the same shape — add jira.py later.)
"""
from __future__ import annotations

from datetime import datetime

from apps.api.connectors.base import Connector, NormalizedArtifact, _parse_dt

_QUERY = """
{ issues(first: %d) { nodes {
  id title description updatedAt priority
  state { name }
  labels { nodes { name } }
  comments { nodes { id body updatedAt user { name } } }
} } }
"""


class LinearConnector(Connector):
    kind = "linear"

    def _http_client(self, auth: str):
        import httpx

        return httpx.Client(base_url="https://api.linear.app", timeout=30,
                            headers={"Authorization": auth, "Content-Type": "application/json"})

    def _records(self) -> dict:
        token = self.config.get("access_token")
        api_key = self.config.get("api_key")
        if token or api_key:
            return self._live_records(f"Bearer {token}" if token else api_key)
        if self.config.get("mode") == "live":
            raise RuntimeError("live Linear mode requires an api_key or OAuth access_token")
        return self._load_fixture("incidents.json")

    def _live_records(self, auth: str) -> dict:
        n = int(self.config.get("max_issues", 50))
        with self._http_client(auth) as client:
            r = client.post("/graphql", json={"query": _QUERY % n})
            r.raise_for_status()
            body = r.json()
            if body.get("errors"):
                raise RuntimeError(f"Linear API error: {body['errors']}")
            nodes = (((body.get("data") or {}).get("issues")) or {}).get("nodes", [])
        issues = [{
            "id": x["id"], "title": x.get("title", ""), "description": x.get("description") or "",
            "updated_at": x.get("updatedAt"), "priority": x.get("priority"),
            "state": (x.get("state") or {}).get("name"),
            "labels": [l["name"] for l in (x.get("labels") or {}).get("nodes", [])],
            "comments": [{"id": c["id"], "body": c.get("body", ""), "updated_at": c.get("updatedAt"),
                          "author": (c.get("user") or {}).get("name")}
                         for c in (x.get("comments") or {}).get("nodes", [])],
        } for x in nodes]
        return {"team": self.config.get("team", "core"), "issues": issues}

    def discover(self) -> dict:
        d = self._records()
        return {"team": d.get("team"), "issues": len(d.get("issues", []))}

    def pull_acls(self) -> dict:
        d = self._records()
        return self._native_groups([f"linear-team:{d.get('team', 'core')}", "eng-team"])

    def pull(self, since: datetime | None = None) -> list[NormalizedArtifact]:
        d = self._records()
        team = d.get("team", "core")
        out: list[NormalizedArtifact] = []
        for i in d.get("issues", []):
            occ = _parse_dt(i.get("updated_at"))
            if self._since_ok(since, occ):
                out.append(NormalizedArtifact(
                    external_id=f"linear-{i['id']}", kind="linear_issue",
                    content_text=f"{i.get('title','')}\n{i.get('description','')}",
                    author=i.get("author"), occurred_at=occ,
                    raw={**i, "team": team, "state": i.get("state"), "priority": i.get("priority"),
                         "labels": i.get("labels", [])}))
            for c in i.get("comments", []):
                cocc = _parse_dt(c.get("updated_at"))
                if self._since_ok(since, cocc):
                    out.append(NormalizedArtifact(
                        external_id=f"linear-comment-{c['id']}", kind="linear_comment",
                        content_text=c.get("body", ""), author=c.get("author"), occurred_at=cocc,
                        raw={**c, "team": team, "issue_id": i["id"]}))
        return out
