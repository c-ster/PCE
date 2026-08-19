"""CRUD persistence for SourceDocument against the source_documents table."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from pce.context.models import EpistemicRole, Sensitivity, SourceDocument, SourceStatus

_COLUMNS = [
    "id",
    "source_type",
    "source_system",
    "source_ref",
    "source_version",
    "title",
    "author",
    "authorship",
    "created_at_source",
    "updated_at_source",
    "ingested_at",
    "domains",
    "projects",
    "organizations",
    "epistemic_role",
    "authority",
    "status",
    "sensitivity",
    "compartments",
    "voice_sample",
    "fiction",
    "content_hash",
    "parser_version",
    "chunking_version",
    "embedding_generation",
]

# Columns updated on re-ingestion; `id` is deliberately excluded so a
# document's identity stays stable across repeated syncs of the same
# (source_system, source_ref).
_UPDATE_COLUMNS = [c for c in _COLUMNS if c not in ("id", "source_system", "source_ref")]


def _to_row(doc: SourceDocument) -> dict:
    return {
        "id": doc.id,
        "source_type": doc.source_type,
        "source_system": doc.source_system,
        "source_ref": doc.source_ref,
        "source_version": doc.source_version,
        "title": doc.title,
        "author": doc.author,
        "authorship": doc.authorship,
        "created_at_source": doc.created_at_source.isoformat() if doc.created_at_source else None,
        "updated_at_source": doc.updated_at_source.isoformat() if doc.updated_at_source else None,
        "ingested_at": doc.ingested_at.isoformat(),
        "domains": json.dumps(doc.domains),
        "projects": json.dumps(doc.projects),
        "organizations": json.dumps(doc.organizations),
        "epistemic_role": doc.epistemic_role.value,
        "authority": doc.authority,
        "status": doc.status.value,
        "sensitivity": doc.sensitivity.value,
        "compartments": json.dumps(doc.compartments),
        "voice_sample": int(doc.voice_sample),
        "fiction": int(doc.fiction),
        "content_hash": doc.content_hash,
        "parser_version": doc.parser_version,
        "chunking_version": doc.chunking_version,
        "embedding_generation": doc.embedding_generation,
    }


def _from_row(row: sqlite3.Row) -> SourceDocument:
    return SourceDocument(
        id=row["id"],
        source_type=row["source_type"],
        source_system=row["source_system"],
        source_ref=row["source_ref"],
        source_version=row["source_version"],
        title=row["title"],
        author=row["author"],
        authorship=row["authorship"],
        created_at_source=datetime.fromisoformat(row["created_at_source"]) if row["created_at_source"] else None,
        updated_at_source=datetime.fromisoformat(row["updated_at_source"]) if row["updated_at_source"] else None,
        ingested_at=datetime.fromisoformat(row["ingested_at"]),
        domains=json.loads(row["domains"]),
        projects=json.loads(row["projects"]),
        organizations=json.loads(row["organizations"]),
        epistemic_role=EpistemicRole(row["epistemic_role"]),
        authority=row["authority"],
        status=SourceStatus(row["status"]),
        sensitivity=Sensitivity(row["sensitivity"]),
        compartments=json.loads(row["compartments"]),
        voice_sample=bool(row["voice_sample"]),
        fiction=bool(row["fiction"]),
        content_hash=row["content_hash"],
        parser_version=row["parser_version"],
        chunking_version=row["chunking_version"],
        embedding_generation=row["embedding_generation"],
    )


class SourceDocumentRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def upsert(self, doc: SourceDocument) -> SourceDocument:
        """Insert doc, or update it in place if (source_system, source_ref)
        already exists — keeping the existing id stable."""
        row = _to_row(doc)
        placeholders = ", ".join(f":{c}" for c in _COLUMNS)
        update_clause = ", ".join(f"{c} = excluded.{c}" for c in _UPDATE_COLUMNS)
        self._conn.execute(
            f"""
            INSERT INTO source_documents ({", ".join(_COLUMNS)})
            VALUES ({placeholders})
            ON CONFLICT (source_system, source_ref) DO UPDATE SET {update_clause}
            """,
            row,
        )
        self._conn.commit()
        return self.get_by_source_ref(doc.source_system, doc.source_ref)

    def get(self, doc_id: str) -> SourceDocument | None:
        row = self._conn.execute(
            "SELECT * FROM source_documents WHERE id = ?", (doc_id,)
        ).fetchone()
        return _from_row(row) if row else None

    def get_by_source_ref(self, source_system: str, source_ref: str) -> SourceDocument | None:
        row = self._conn.execute(
            "SELECT * FROM source_documents WHERE source_system = ? AND source_ref = ?",
            (source_system, source_ref),
        ).fetchone()
        return _from_row(row) if row else None

    def list(self) -> list[SourceDocument]:
        rows = self._conn.execute("SELECT * FROM source_documents ORDER BY ingested_at").fetchall()
        return [_from_row(row) for row in rows]

    def delete(self, doc_id: str) -> None:
        self._conn.execute("DELETE FROM source_documents WHERE id = ?", (doc_id,))
        self._conn.commit()
