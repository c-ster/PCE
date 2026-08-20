"""Persistence for ContextChunk — the retrieval unit (PRD section 16)."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def _fts_match_query(query: str) -> str | None:
    """Build an FTS5 MATCH expression from raw, untrusted user input.

    Quotes every token as a literal phrase so punctuation/operators in the
    query (quotes, colons, hyphens, ``AND``/``NOT``) can't be interpreted as
    FTS5 query syntax. Returns None if the query has no word characters at
    all, so callers can skip the query instead of matching nothing.
    """
    tokens = _WORD_RE.findall(query)
    if not tokens:
        return None
    return " OR ".join('"{}"'.format(token.replace('"', '""')) for token in tokens)


@dataclass
class ContextChunk:
    id: str
    document_id: str
    sequence: int
    text: str
    source_content_hash: str
    embedding: list[float] | None
    embedding_model: str | None


def _row_to_chunk(row: sqlite3.Row) -> ContextChunk:
    return ContextChunk(
        id=row["id"],
        document_id=row["document_id"],
        sequence=row["sequence"],
        text=row["text"],
        source_content_hash=row["source_content_hash"],
        embedding=json.loads(row["embedding"]) if row["embedding"] else None,
        embedding_model=row["embedding_model"],
    )


class ChunkRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def is_up_to_date(self, document_id: str, content_hash: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM context_chunks WHERE document_id = ? AND source_content_hash = ? LIMIT 1",
            (document_id, content_hash),
        ).fetchone()
        return row is not None

    def replace_chunks(self, document_id: str, content_hash: str, texts: list[str]) -> list[ContextChunk]:
        """Delete any existing chunks for document_id and insert fresh ones
        (unembedded). Used whenever a document's content has changed."""
        self._conn.execute("DELETE FROM context_chunks WHERE document_id = ?", (document_id,))

        created_at = datetime.now(timezone.utc).isoformat()
        chunks = []
        for sequence, text in enumerate(texts):
            chunk = ContextChunk(
                id=str(uuid4()),
                document_id=document_id,
                sequence=sequence,
                text=text,
                source_content_hash=content_hash,
                embedding=None,
                embedding_model=None,
            )
            self._conn.execute(
                """
                INSERT INTO context_chunks
                    (id, document_id, sequence, text, source_content_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (chunk.id, chunk.document_id, chunk.sequence, chunk.text, chunk.source_content_hash, created_at),
            )
            chunks.append(chunk)

        self._conn.commit()
        return chunks

    def set_embedding(self, chunk_id: str, embedding: list[float], model_name: str) -> None:
        self._conn.execute(
            """
            UPDATE context_chunks
            SET embedding = ?, embedding_model = ?, embedding_dims = ?
            WHERE id = ?
            """,
            (json.dumps(embedding), model_name, len(embedding), chunk_id),
        )
        self._conn.commit()

    def get(self, chunk_id: str) -> ContextChunk | None:
        row = self._conn.execute("SELECT * FROM context_chunks WHERE id = ?", (chunk_id,)).fetchone()
        return _row_to_chunk(row) if row else None

    def get_for_document(self, document_id: str) -> list[ContextChunk]:
        rows = self._conn.execute(
            "SELECT * FROM context_chunks WHERE document_id = ? ORDER BY sequence", (document_id,)
        ).fetchall()
        return [_row_to_chunk(row) for row in rows]

    def all_embedded(self) -> list[ContextChunk]:
        rows = self._conn.execute("SELECT * FROM context_chunks WHERE embedding IS NOT NULL").fetchall()
        return [_row_to_chunk(row) for row in rows]

    def lexical_search(self, query: str, limit: int) -> list[tuple[str, float]]:
        """Return (chunk_id, bm25_score) pairs, best match first. FTS5's
        bm25() is negative-is-better, so we negate it into ascending "higher
        is better" like everything else in this module."""
        match_query = _fts_match_query(query)
        if match_query is None:
            return []

        rows = self._conn.execute(
            """
            SELECT c.id AS id, bm25(context_chunks_fts) AS rank
            FROM context_chunks_fts
            JOIN context_chunks c ON c.rowid = context_chunks_fts.rowid
            WHERE context_chunks_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (match_query, limit),
        ).fetchall()
        return [(row["id"], -row["rank"]) for row in rows]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) AS n FROM context_chunks").fetchone()["n"]
