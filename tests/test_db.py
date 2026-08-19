from pathlib import Path

from pce.context.db import connect, run_migrations
from pce.context.models import SourceDocument
from pce.context.repository import SourceDocumentRepository


def _doc(source_ref: str, content_hash: str, **overrides) -> SourceDocument:
    defaults = dict(
        source_type="markdown",
        source_system="local_file",
        source_ref=source_ref,
        content_hash=content_hash,
        parser_version="v1",
        chunking_version="v1",
    )
    defaults.update(overrides)
    return SourceDocument(**defaults)


def test_migrations_create_source_documents_table(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "source_documents" in tables
    assert "schema_migrations" in tables


def test_migrations_are_idempotent(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    # Re-running should apply nothing new and not raise.
    applied = run_migrations(conn)
    assert applied == []


def test_repository_upsert_and_get(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = SourceDocumentRepository(conn)

    doc = _doc("/root/a.md", "hash-1", title="A")
    stored = repo.upsert(doc)

    fetched = repo.get(stored.id)
    assert fetched is not None
    assert fetched.title == "A"
    assert fetched.content_hash == "hash-1"


def test_repository_upsert_keeps_id_stable_on_reingestion(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = SourceDocumentRepository(conn)

    first = repo.upsert(_doc("/root/a.md", "hash-1", title="Draft"))
    second = repo.upsert(_doc("/root/a.md", "hash-2", title="Final"))

    assert first.id == second.id
    assert repo.list() == [second]

    fetched = repo.get_by_source_ref("local_file", "/root/a.md")
    assert fetched is not None
    assert fetched.title == "Final"
    assert fetched.content_hash == "hash-2"


def test_repository_delete(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = SourceDocumentRepository(conn)

    stored = repo.upsert(_doc("/root/a.md", "hash-1"))
    repo.delete(stored.id)

    assert repo.get(stored.id) is None
    assert repo.list() == []
