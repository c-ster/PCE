"""Reciprocal rank fusion — the "simple, inspectable technique" PRD section
16 asks for, rather than a learned or opaque re-ranker."""

from __future__ import annotations


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """rankings: one or more best-first lists of item ids (e.g. lexical and
    semantic result lists). Returns (item_id, fused_score) best-first."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
