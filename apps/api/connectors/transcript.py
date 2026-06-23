"""Call-transcript connector (M1) — VTT or JSON, with speaker + timestamp
attribution so a spoken commitment is provenance-citable. Unlocks
`handle-pricing-exception` (sales call) and `respond-to-incident` (on-call retro)."""
from __future__ import annotations

import re
from datetime import datetime

from apps.api.connectors.base import Connector, NormalizedArtifact, _parse_dt

_VTT_CUE = re.compile(r"(?:(\w+):\s*)?(.+)")


def _parse_vtt(text: str) -> list[dict]:
    segs, speaker = [], None
    for block in text.split("\n\n"):
        lines = [ln for ln in block.splitlines() if ln.strip() and "-->" not in ln and ln != "WEBVTT"]
        for ln in lines:
            m = re.match(r"<v ([^>]+)>(.*)", ln)
            if m:
                segs.append({"speaker": m.group(1), "text": m.group(2)})
            elif ":" in ln:
                spk, _, txt = ln.partition(":")
                segs.append({"speaker": spk.strip(), "text": txt.strip()})
            else:
                segs.append({"speaker": speaker, "text": ln.strip()})
    return segs


class TranscriptConnector(Connector):
    kind = "transcript"

    def _records(self) -> dict:
        if self.config.get("mode") == "live":  # pragma: no cover
            raise RuntimeError("live transcript mode requires a recording-provider client")
        return self._load_fixture("calls.json")

    def discover(self) -> dict:
        d = self._records()
        return {"calls": len(d.get("calls", []))}

    def pull_acls(self) -> dict:
        return self._native_groups(["sales-team"])

    def pull(self, since: datetime | None = None) -> list[NormalizedArtifact]:
        d = self._records()
        out: list[NormalizedArtifact] = []
        for call in d.get("calls", []):
            occ = _parse_dt(call.get("occurred_at"))
            if not self._since_ok(since, occ):
                continue
            if call.get("vtt"):
                segs = _parse_vtt(call["vtt"])
            else:
                segs = call.get("segments", [])
            text = "\n".join(s.get("text", "") for s in segs)
            speakers = sorted({s.get("speaker") for s in segs if s.get("speaker")})
            out.append(NormalizedArtifact(
                external_id=f"transcript-{call['id']}", kind="transcript", content_text=text,
                author=(speakers[0] if speakers else call.get("host")), occurred_at=occ,
                raw={"id": call["id"], "speakers": speakers, "segments": segs,
                     "title": call.get("title")}))
        return out
