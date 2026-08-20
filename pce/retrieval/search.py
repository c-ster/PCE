"""Hybrid search: SQLite FTS5 (lexical) + embedding cosine similarity
(semantic), combined with reciprocal rank fusion (PRD section 16).

access_context is required, not optional, so a caller can't accidentally
search without a policy decision: the eligible document set is computed
from it *before* lexical/semantic scoring runs (section 29, "policy before
ranking"), not filtered out of a ranked list afterward.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass

from pce.context.chunks import ChunkRepository
from pce.context.models import SourceDocument
from pce.context.repository import SourceDocumentRepository
from pce.policy.engine import AccessContext, eligible_document_ids
from pce.providers.base import EmbeddingProvider
from pce.retrieval.fusion import reciprocal_rank_fusion


@dataclass
class SearchResult:
    chunk_id: str
    document: SourceDocument
    text: str
    score: float


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def semantic_ranking(
    chunk_repo: ChunkRepository,
    query_embedding: list[float],
    limit: int,
    eligible_ids: set[str] | None = None,
) -> list[str]:
    scored = [
        (chunk.id, _cosine(query_embedding, chunk.embedding))
        for chunk in chunk_repo.all_embedded(eligible_document_ids=eligible_ids)
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [chunk_id for chunk_id, _ in scored[:limit]]


def hybrid_search(
    conn: sqlite3.Connection,
    query: str,
    embedding_provider: EmbeddingProvider,
    access_context: AccessContext,
    limit: int = 10,
) -> list[SearchResult]:
    chunk_repo = ChunkRepository(conn)
    doc_repo = SourceDocumentRepository(conn)

    eligible_ids = eligible_document_ids(doc_repo.list(), access_context)
    if not eligible_ids:
        return []

    candidate_pool = limit * 4
    lexical_ranking = [
        chunk_id
        for chunk_id, _ in chunk_repo.lexical_search(query, limit=candidate_pool, eligible_document_ids=eligible_ids)
    ]

    query_embedding = embedding_provider.embed([query])[0]
    semantic_rank = semantic_ranking(chunk_repo, query_embedding, limit=candidate_pool, eligible_ids=eligible_ids)

    fused = reciprocal_rank_fusion([lexical_ranking, semantic_rank])

    results = []
    for chunk_id, score in fused[:limit]:
        chunk = chunk_repo.get(chunk_id)
        if not chunk:
            continue
        document = doc_repo.get(chunk.document_id)
        if not document:
            continue
        results.append(SearchResult(chunk_id=chunk.id, document=document, text=chunk.text, score=score))

    return results
