"""Builds the local retrieval index: chunk every registered source's
documents and embed the chunks. Skips documents whose content hasn't
changed since they were last indexed (PRD section 45, incremental indexing).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from pce.adapters.git import GitAdapter
from pce.adapters.local_file import LocalFileAdapter
from pce.context.chunks import ChunkRepository
from pce.context.registry import SourceRegistry
from pce.context.repository import SourceDocumentRepository
from pce.providers.base import EmbeddingProvider
from pce.retrieval.chunking import chunk_text


@dataclass
class IndexStats:
    documents_processed: int = 0
    documents_skipped: int = 0
    documents_failed: int = 0
    chunks_created: int = 0
    failures: list[str] = field(default_factory=list)


def build_index(conn: sqlite3.Connection, embedding_provider: EmbeddingProvider) -> IndexStats:
    registry = SourceRegistry(conn)
    doc_repo = SourceDocumentRepository(conn)
    chunk_repo = ChunkRepository(conn)
    stats = IndexStats()

    for source in registry.list():
        if source.kind == "local_file":
            adapter = LocalFileAdapter(approved_roots=[Path(source.path)])
        elif source.kind == "git":
            adapter = GitAdapter(repo_path=Path(source.path))
        else:
            continue

        for document_id in registry.document_ids(source.id):
            document = doc_repo.get(document_id)
            if not document:
                continue

            if chunk_repo.is_up_to_date(document.id, document.content_hash):
                stats.documents_skipped += 1
                continue

            try:
                content = adapter.read_document(document.source_ref)
            except Exception as exc:  # noqa: BLE001 - source may have moved/been deleted since ingestion
                stats.documents_failed += 1
                stats.failures.append(f"{document.source_ref}: {exc}")
                continue

            texts = chunk_text(content)
            chunks = chunk_repo.replace_chunks(document.id, document.content_hash, texts)

            if chunks:
                embeddings = embedding_provider.embed([chunk.text for chunk in chunks])
                for chunk, embedding in zip(chunks, embeddings):
                    chunk_repo.set_embedding(chunk.id, embedding, embedding_provider.name)

            stats.documents_processed += 1
            stats.chunks_created += len(texts)

    return stats
