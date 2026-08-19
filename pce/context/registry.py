"""Registered-source bookkeeping backing `pce source`, `pce repo`, `pce sync`.

Tracks which approved root or git repo was registered, and which
SourceDocuments it produced, so the CLI can list, inspect, re-sync, and
remove a source without re-deriving that from scratch.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class RegisteredSource:
    id: str
    kind: str  # "local_file" | "git"
    path: str
    added_at: datetime


def _row_to_source(row: sqlite3.Row) -> RegisteredSource:
    return RegisteredSource(
        id=row["id"],
        kind=row["kind"],
        path=row["path"],
        added_at=datetime.fromisoformat(row["added_at"]),
    )


class SourceRegistry:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def register(self, kind: str, path: str) -> RegisteredSource:
        """Register a source root, or return the existing registration if
        this (kind, path) is already registered."""
        existing = self.get_by_path(kind, path)
        if existing:
            return existing

        source = RegisteredSource(
            id=str(uuid4()), kind=kind, path=path, added_at=datetime.now(timezone.utc)
        )
        self._conn.execute(
            "INSERT INTO registered_sources (id, kind, path, added_at) VALUES (?, ?, ?, ?)",
            (source.id, source.kind, source.path, source.added_at.isoformat()),
        )
        self._conn.commit()
        return source

    def get(self, source_id: str) -> RegisteredSource | None:
        row = self._conn.execute(
            "SELECT * FROM registered_sources WHERE id = ?", (source_id,)
        ).fetchone()
        return _row_to_source(row) if row else None

    def get_by_path(self, kind: str, path: str) -> RegisteredSource | None:
        row = self._conn.execute(
            "SELECT * FROM registered_sources WHERE kind = ? AND path = ?", (kind, path)
        ).fetchone()
        return _row_to_source(row) if row else None

    def list(self, kind: str | None = None) -> list[RegisteredSource]:
        if kind:
            rows = self._conn.execute(
                "SELECT * FROM registered_sources WHERE kind = ? ORDER BY added_at", (kind,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM registered_sources ORDER BY added_at"
            ).fetchall()
        return [_row_to_source(row) for row in rows]

    def link_document(self, source_id: str, document_id: str) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO registered_source_documents
                (registered_source_id, document_id)
            VALUES (?, ?)
            """,
            (source_id, document_id),
        )
        self._conn.commit()

    def document_ids(self, source_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT document_id FROM registered_source_documents WHERE registered_source_id = ?",
            (source_id,),
        ).fetchall()
        return [row["document_id"] for row in rows]

    def remove(self, source_id: str) -> None:
        self._conn.execute("DELETE FROM registered_sources WHERE id = ?", (source_id,))
        self._conn.commit()
