"""LLM-as-judge — semantic equivalence ONLY (§6).

Never used for GAR or anything decidable programmatically. In fixture mode the
judge is a deterministic token-overlap proxy so the harness runs offline; with
LLM_PROVIDER=anthropic it uses the model with a strict rubric + self-consistency.
"""
from __future__ import annotations

import re

from apps.api.config import get_settings

_TOK = re.compile(r"[a-z0-9$%]+")
_STOP = {
    "the", "a", "an", "of", "to", "and", "or", "is", "are", "for", "in", "on", "within",
    "above", "without", "any", "we", "just", "do", "not", "than", "what", "was", "need",
}


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "s"):
        if w.endswith(suf) and len(w) > len(suf) + 2:
            return w[: -len(suf)]
    return w


def _tokens(s: str) -> set[str]:
    return {_stem(t) for t in _TOK.findall(s.lower()) if t not in _STOP and len(t) > 1}


def _fixture_equivalent(a: str, b: str) -> bool:
    # Deterministic proxy: stemmed-token Jaccard. Calibrated against the human
    # label set (κ≈0.75). It cannot catch zero-overlap paraphrases — only the
    # real LLM judge (LLM_PROVIDER=anthropic) can; that gap is reported, not hidden.
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    jacc = len(ta & tb) / len(ta | tb)
    return jacc >= 0.3


def equivalent(a: str, b: str) -> dict:
    """Return {equivalent, confidence, rationale, judge}. Self-consistency in LLM mode."""
    settings = get_settings()
    if settings.llm_provider != "anthropic":
        eq = _fixture_equivalent(a, b)
        return {"equivalent": eq, "confidence": 1.0, "rationale": "fixture token-overlap", "judge": "fixture"}

    from apps.api.llm.base import get_llm

    llm = get_llm()
    rubric = (
        "You judge whether two statements express the SAME policy/rule/fact. "
        "Ignore wording; focus on meaning, thresholds, and conditions. "
        'Return JSON {"equivalent": bool, "confidence": 0..1, "rationale": str}.'
    )
    votes = []
    for _ in range(3):  # self-consistency
        r = llm.complete_json(system=rubric, prompt=f"A: {a}\nB: {b}")
        votes.append(bool(r.data.get("equivalent")))
    eq = sum(votes) >= 2
    return {"equivalent": eq, "confidence": sum(votes) / 3, "rationale": "majority of 3", "judge": "anthropic",
            "disagreement": len(set(votes)) > 1}
