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


# Strict rubric: the judge must be SENSITIVE to numbers, comparators, and
# negation — the exact ways a near-miss extraction silently changes meaning.
# These are the failure modes that a loose token-overlap proxy misses, so the
# rubric calls them out explicitly. (Validated against HUMAN_PAIRS → Cohen's κ.)
_JUDGE_RUBRIC = (
    "You decide whether two statements express the SAME policy, rule, procedure, or fact. "
    "Judge MEANING, not wording — paraphrases, synonyms, and reordering are equivalent. "
    "But you MUST treat these as NON-equivalent (different meaning):\n"
    "  - any different number or threshold (20% vs 25%, $500 vs $5000, 30 days vs 60 days);\n"
    "  - a flipped comparator or direction (above vs below, more vs less, within vs after);\n"
    "  - added or removed negation (require vs not require, never vs always);\n"
    "  - a different actor, channel, object, or approval authority (manager vs VP, order vs account).\n"
    "When unsure, default to equivalent=false. "
    'Return JSON only: {"equivalent": bool, "confidence": 0..1, "rationale": "<one sentence>"}.'
)


def equivalent(a: str, b: str, samples: int = 3) -> dict:
    """Semantic-equivalence verdict.

    fixture: deterministic token-overlap proxy (offline, no key).
    anthropic: the real model with the strict rubric above + N-sample self-consistency
    (majority vote), so a single stochastic flip can't decide a match.
    """
    settings = get_settings()
    if settings.llm_provider != "anthropic":
        eq = _fixture_equivalent(a, b)
        return {"equivalent": eq, "confidence": 1.0, "rationale": "fixture token-overlap",
                "judge": "fixture", "model": "fixture"}

    from apps.api.llm.base import get_llm

    llm = get_llm()
    votes, confs = [], []
    for _ in range(max(1, samples)):  # self-consistency
        r = llm.complete_json(
            system=_JUDGE_RUBRIC,
            prompt=f"Statement A: {a}\nStatement B: {b}",
            model=settings.model_extract,
        )
        votes.append(bool(r.data.get("equivalent")))
        try:
            confs.append(float(r.data.get("confidence", 0.0)))
        except (TypeError, ValueError):
            confs.append(0.0)
    eq = sum(votes) > len(votes) / 2  # strict majority
    return {
        "equivalent": eq,
        "confidence": round(sum(votes) / len(votes), 3),
        "model_confidence": round(sum(confs) / len(confs), 3) if confs else 0.0,
        "rationale": f"majority {sum(votes)}/{len(votes)}",
        "judge": "anthropic",
        "model": settings.model_extract,
        "disagreement": len(set(votes)) > 1,
    }
