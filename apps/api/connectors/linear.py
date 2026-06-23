"""Linear connector (M1) — issues + comments. Carries state/priority/labels in
`raw` (the structured incident signal). Jira is the same shape (add jira.py later).
Unlocks `respond-to-incident`."""
from __future__ import annotations

from datetime import datetime

from apps.api.connectors.base import Connector, NormalizedArtifact, _parse_dt


class LinearConnector(Connector):
    kind = "linear"

    def _records(self) -> dict:
        if self.config.get("mode") == "live":  # pragma: no cover
            raise RuntimeError("live Linear mode requires LINEAR_API_KEY")
        return self._load_fixture("incidents.json")

    def discover(self) -> dict:
        d = self._records()
        return {"team": d.get("team"), "issues": len(d.get("issues", []))}

    def pull_acls(self) -> dict:
        d = self._records()
        return self._native_groups([f"linear-team:{d.get('team','core')}", "eng-team"])

    def pull(self, since: datetime | None = None) -> list[NormalizedArtifact]:
        d = self._records()
        team = d.get("team", "core")
        out: list[NormalizedArtifact] = []
        for i in d.get("issues", []):
            occ = _parse_dt(i.get("updated_at"))
            if self._since_ok(since, occ):
                body = f"{i.get('title','')}\n{i.get('description','')}"
                out.append(NormalizedArtifact(
                    external_id=f"linear-{i['id']}", kind="linear_issue", content_text=body,
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
