"""Hybrid search: SQLite FTS5 (lexical) + embedding cosine similarity
(semantic), combined with reciprocal rank fusion (PRD section 16).

Deliberately does not filter by sensitivity/compartment — policy
enforcement doesn't exist yet (see docs/THREAT_MODEL.md "Policy before
ranking"). Callers must not present this as access-controlled.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass

from pce.context.chunks import ChunkRepository
from pce.context.models import SourceDocument
from pce.context.repository import SourceDocumentRepository
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


def semantic_ranking(chunk_repo: ChunkRepository, query_embedding: list[float], limit: int) -> list[str]:
    scored = [(chunk.id, _cosine(query_embedding, chunk.embedding)) for chunk in chunk_repo.all_embedded()]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [chunk_id for chunk_id, _ in scored[:limit]]


def hybrid_search(
    conn: sqlite3.Connection,
    query: str,
    embedding_provider: EmbeddingProvider,
    limit: int = 10,
) -> list[SearchResult]:
    chunk_repo = ChunkRepository(conn)
    doc_repo = SourceDocumentRepository(conn)

    candidate_pool = limit * 4
    lexical_ranking = [chunk_id for chunk_id, _ in chunk_repo.lexical_search(query, limit=candidate_pool)]

    query_embedding = embedding_provider.embed([query])[0]
    semantic_rank = semantic_ranking(chunk_repo, query_embedding, limit=candidate_pool)

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
