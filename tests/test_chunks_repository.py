from pathlib import Path

from pce.context.chunks import ChunkRepository
from pce.context.db import connect
from pce.context.models import SourceDocument
from pce.context.repository import SourceDocumentRepository


def _doc(**overrides) -> SourceDocument:
    defaults = dict(
        source_type="markdown",
        source_system="local_file",
        source_ref="/root/a.md",
        content_hash="hash-1",
        parser_version="v1",
        chunking_version="v1",
    )
    defaults.update(overrides)
    return SourceDocument(**defaults)


def test_replace_chunks_then_lexical_search_finds_it(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    doc = SourceDocumentRepository(conn).upsert(_doc())
    chunk_repo = ChunkRepository(conn)

    chunk_repo.replace_chunks(doc.id, doc.content_hash, ["The nightingale price was approved at five thousand."])

    hits = chunk_repo.lexical_search("nightingale", limit=10)
    assert len(hits) == 1
    assert hits[0][1] > 0


def test_lexical_search_sanitizes_punctuation_without_raising(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    doc = SourceDocumentRepository(conn).upsert(_doc())
    chunk_repo = ChunkRepository(conn)
    chunk_repo.replace_chunks(doc.id, doc.content_hash, ["Quoted text with \"weird\" punctuation: like - this."])

    # Should not raise even though the query contains FTS5 syntax characters.
    hits = chunk_repo.lexical_search('weird" OR NOT * :', limit=10)
    assert isinstance(hits, list)


def test_lexical_search_with_no_word_characters_returns_empty(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    chunk_repo = ChunkRepository(conn)
    assert chunk_repo.lexical_search("   ---   ", limit=10) == []


def test_is_up_to_date_reflects_content_hash(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    doc = SourceDocumentRepository(conn).upsert(_doc())
    chunk_repo = ChunkRepository(conn)

    assert chunk_repo.is_up_to_date(doc.id, doc.content_hash) is False
    chunk_repo.replace_chunks(doc.id, doc.content_hash, ["some text"])
    assert chunk_repo.is_up_to_date(doc.id, doc.content_hash) is True
    assert chunk_repo.is_up_to_date(doc.id, "a-different-hash") is False


def test_set_embedding_round_trips(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    doc = SourceDocumentRepository(conn).upsert(_doc())
    chunk_repo = ChunkRepository(conn)
    [chunk] = chunk_repo.replace_chunks(doc.id, doc.content_hash, ["some text"])

    chunk_repo.set_embedding(chunk.id, [0.1, 0.2, 0.3], "hashing_v1")

    fetched = chunk_repo.get(chunk.id)
    assert fetched.embedding == [0.1, 0.2, 0.3]
    assert fetched.embedding_model == "hashing_v1"
    assert chunk_repo.all_embedded() == [fetched]


def test_replace_chunks_deletes_old_chunks_and_fts_entries(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    doc = SourceDocumentRepository(conn).upsert(_doc())
    chunk_repo = ChunkRepository(conn)

    chunk_repo.replace_chunks(doc.id, "hash-1", ["original unique wombat text"])
    assert len(chunk_repo.lexical_search("wombat", limit=10)) == 1

    chunk_repo.replace_chunks(doc.id, "hash-2", ["completely different content"])
    assert chunk_repo.lexical_search("wombat", limit=10) == []
    assert len(chunk_repo.get_for_document(doc.id)) == 1


def test_deleting_document_cascades_to_chunks(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    doc_repo = SourceDocumentRepository(conn)
    doc = doc_repo.upsert(_doc())
    chunk_repo = ChunkRepository(conn)
    chunk_repo.replace_chunks(doc.id, doc.content_hash, ["some text"])

    doc_repo.delete(doc.id)

    assert chunk_repo.get_for_document(doc.id) == []
    assert chunk_repo.count() == 0
