"""Embeddings behind a seam.

Fixture mode uses a deterministic, dependency-free hashed bag-of-tokens
embedding so dedup / entity resolution / semantic routing all work offline and
reproducibly. In production, point `embed()` at a real embedding model
(Voyage/OpenAI) and write the vector into the pgvector column — the rest of the
system is agnostic to how the vector was produced.
"""
from __future__ import annotations

import hashlib
import math
import re

from apps.api.models.db import EMBED_DIM

_TOKEN = re.compile(r"[a-z0-9$]+")
# light stopword list so common words don't dominate similarity
_STOP = {
    "the", "a", "an", "of", "to", "and", "or", "is", "are", "for", "in", "on",
    "at", "we", "you", "it", "that", "this", "be", "with", "as", "by", "if",
}


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 1]


def embed(text: str, dim: int = EMBED_DIM) -> list[float]:
    """Deterministic hashed-trigram + token embedding, L2-normalized."""
    vec = [0.0] * dim
    toks = _tokens(text)
    grams = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]  # unigrams + bigrams
    for g in grams:
        h = int(hashlib.sha1(g.encode()).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    return sum(x * y for x, y in zip(a, b))  # vectors are pre-normalized
