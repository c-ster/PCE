from pathlib import Path

from pce.adapters.local_file import LocalFileAdapter
from pce.context.chunks import ChunkRepository
from pce.context.db import connect
from pce.context.registry import SourceRegistry
from pce.context.repository import SourceDocumentRepository
from pce.providers.hashing_embeddings import HashingEmbeddingProvider
from pce.retrieval.indexer import build_index


def _register_and_ingest(conn, root: Path):
    registry = SourceRegistry(conn)
    doc_repo = SourceDocumentRepository(conn)
    source = registry.register("local_file", str(root))
    for doc in LocalFileAdapter(approved_roots=[root]).sync():
        stored = doc_repo.upsert(doc)
        registry.link_document(source.id, stored.id)
    return source


def test_build_index_creates_embedded_chunks(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "a.md").write_text("# A\n\nSome unique aardvark content.\n")
    (root / "b.md").write_text("# B\n\nSome unique bumblebee content.\n")

    conn = connect(tmp_path / "pce.sqlite3")
    _register_and_ingest(conn, root)

    stats = build_index(conn, HashingEmbeddingProvider())

    assert stats.documents_processed == 2
    assert stats.documents_skipped == 0
    assert stats.documents_failed == 0

    chunk_repo = ChunkRepository(conn)
    assert chunk_repo.count() == 2
    assert len(chunk_repo.all_embedded()) == 2


def test_build_index_skips_unchanged_documents_on_rerun(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "a.md").write_text("# A\n\nStable content.\n")

    conn = connect(tmp_path / "pce.sqlite3")
    _register_and_ingest(conn, root)

    first = build_index(conn, HashingEmbeddingProvider())
    second = build_index(conn, HashingEmbeddingProvider())

    assert first.documents_processed == 1
    assert second.documents_processed == 0
    assert second.documents_skipped == 1


def test_build_index_reprocesses_changed_documents(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    doc_path = root / "a.md"
    doc_path.write_text("# A\n\nOriginal content.\n")

    conn = connect(tmp_path / "pce.sqlite3")
    source = _register_and_ingest(conn, root)
    build_index(conn, HashingEmbeddingProvider())

    doc_path.write_text("# A\n\nCompletely rewritten content.\n")
    registry = SourceRegistry(conn)
    doc_repo = SourceDocumentRepository(conn)
    for doc in LocalFileAdapter(approved_roots=[root]).sync():
        stored = doc_repo.upsert(doc)
        registry.link_document(source.id, stored.id)

    second = build_index(conn, HashingEmbeddingProvider())
    assert second.documents_processed == 1
    assert second.documents_skipped == 0

    chunk_repo = ChunkRepository(conn)
    [document] = doc_repo.list()
    [chunk] = chunk_repo.get_for_document(document.id)
    assert "rewritten" in chunk.text


def test_build_index_records_failure_for_unreadable_document(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    doc_path = root / "a.md"
    doc_path.write_text("# A\n\nWill be deleted.\n")

    conn = connect(tmp_path / "pce.sqlite3")
    _register_and_ingest(conn, root)
    doc_path.unlink()

    stats = build_index(conn, HashingEmbeddingProvider())
    assert stats.documents_failed == 1
    assert stats.documents_processed == 0
    assert len(stats.failures) == 1
