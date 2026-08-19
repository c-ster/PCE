from pathlib import Path

import pytest

from pce.adapters.errors import SourceRootViolation
from pce.adapters.local_file import LocalFileAdapter


@pytest.fixture
def approved_root(tmp_path: Path) -> Path:
    root = tmp_path / "approved"
    root.mkdir()
    (root / "note.md").write_text("# My Title\n\nSome body text.\n")
    (root / "plain.txt").write_text("Plain text content.\n")
    nested = root / "nested"
    nested.mkdir()
    (nested / "deep.md").write_text("# Deep Note\n\nDeep body.\n")
    return root


def test_discover_finds_supported_files_recursively(approved_root: Path):
    adapter = LocalFileAdapter(approved_roots=[approved_root])
    refs = adapter.discover()
    names = {Path(ref).name for ref in refs}
    assert names == {"note.md", "plain.txt", "deep.md"}


def test_read_document_returns_content(approved_root: Path):
    adapter = LocalFileAdapter(approved_roots=[approved_root])
    ref = str(approved_root / "note.md")
    assert "Some body text." in adapter.read_document(ref)


def test_get_metadata_extracts_title_from_heading(approved_root: Path):
    adapter = LocalFileAdapter(approved_roots=[approved_root])
    metadata = adapter.get_metadata(str(approved_root / "note.md"))
    assert metadata["title"] == "My Title"
    assert metadata["source_type"] == "markdown"


def test_get_metadata_falls_back_to_filename_for_txt(approved_root: Path):
    adapter = LocalFileAdapter(approved_roots=[approved_root])
    metadata = adapter.get_metadata(str(approved_root / "plain.txt"))
    assert metadata["title"] == "plain"
    assert metadata["source_type"] == "text"


def test_read_document_outside_approved_root_raises(approved_root: Path, tmp_path: Path):
    adapter = LocalFileAdapter(approved_roots=[approved_root])
    outside_file = tmp_path / "outside.md"
    outside_file.write_text("should never be read")

    with pytest.raises(SourceRootViolation):
        adapter.read_document(str(outside_file))


def test_sync_yields_source_documents_with_content_hash(approved_root: Path):
    adapter = LocalFileAdapter(approved_roots=[approved_root])
    docs = list(adapter.sync())

    assert len(docs) == 3
    assert all(doc.source_system == "local_file" for doc in docs)
    assert all(doc.content_hash for doc in docs)
    titles = {doc.title for doc in docs}
    assert titles == {"My Title", "plain", "Deep Note"}
