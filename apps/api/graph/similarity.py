"""Similarity helpers (the pgvector seam at the application layer).

Phase 1 computes cosine in Python over stored vectors so the demo runs on
SQLite. In production, replace `nearest()` with a pgvector `ORDER BY embedding
<=> :q` query — callers are agnostic.
"""
from __future__ import annotations

from apps.api.llm.embeddings import cosine


def most_similar(query_vec, candidates: list[tuple[str, list[float]]], top_k: int = 5):
    scored = [(cid, cosine(query_vec, vec)) for cid, vec in candidates if vec]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]
