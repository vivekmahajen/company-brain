"""Golden dataset loader + dev/test split + contamination check (TRUST-2/3).

Goldens are versioned JSON in apps/api/evals/golden/. Bump DATASET_VERSION when
they change so every scorecard is attributable to a dataset.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

GOLDEN_DIR = os.path.dirname(os.path.abspath(__file__))
GOLDEN_PATH = os.path.join(GOLDEN_DIR, "golden")

# Bump when golden datasets change.
DATASET_VERSION = "v0.2"


@lru_cache(maxsize=None)
def _load(stage: str) -> dict:
    with open(os.path.join(GOLDEN_PATH, f"{stage}.json"), encoding="utf-8") as f:
        return json.load(f)


def load_cases(stage: str, split: str | None = None) -> list[dict]:
    """Return cases for a stage, optionally filtered to a split (dev|test)."""
    cases = _load(stage).get("cases", [])
    if split:
        cases = [c for c in cases if c.get("split") == split]
    return cases


def counts() -> dict:
    """Per-stage case counts (reported on the scorecard)."""
    out = {}
    for stage in ("extraction", "synthesis", "compilation", "routing", "execution", "adversarial"):
        cases = _load(stage).get("cases", [])
        out[stage] = {
            "total": len(cases),
            "dev": sum(1 for c in cases if c.get("split") == "dev"),
            "test": sum(1 for c in cases if c.get("split") == "test"),
        }
    perm = _load("permission")
    pc = (perm.get("matrix", []) + perm.get("adversarial", []))
    out["permission"] = {
        "total": len(pc),
        "dev": sum(1 for c in pc if c.get("split") == "dev"),
        "test": sum(1 for c in pc if c.get("split") == "test"),
    }
    return out


def _golden_strings() -> list[str]:
    """Statements/content that must NOT leak into any prompt (few-shot contamination)."""
    strings: list[str] = []
    for stage in ("extraction", "synthesis", "compilation", "routing", "execution", "adversarial"):
        for c in _load(stage).get("cases", []):
            if c.get("content"):
                strings.append(c["content"])
            for u in c.get("expected_units", []) or []:
                if u.get("statement"):
                    strings.append(u["statement"])
            for u in c.get("inputs", []) or []:
                if u.get("statement"):
                    strings.append(u["statement"])
            if c.get("task"):
                strings.append(c["task"])
    return [s for s in strings if len(s) > 12]


def contamination_check() -> dict:
    """TRUST-3: ensure no golden string appears verbatim in a prompt template."""
    from apps.api.llm import prompts

    prompt_blob = "\n".join(
        v for k, v in vars(prompts).items() if isinstance(v, str) and not k.startswith("_")
    ).lower()
    leaks = []
    for s in _golden_strings():
        # check the first clause of each golden string
        probe = s.strip().split("\n")[0][:40].lower()
        if probe and probe in prompt_blob:
            leaks.append(probe)
    return {"clean": not leaks, "leaks": leaks}
