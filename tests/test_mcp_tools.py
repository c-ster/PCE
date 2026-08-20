from pathlib import Path

from pce.adapters.local_file import LocalFileAdapter
from pce.context.db import connect
from pce.context.registry import SourceRegistry
from pce.context.repository import SourceDocumentRepository
from pce.mcp import tools
from pce.policy.engine import AccessContext
from pce.providers.hashing_embeddings import HashingEmbeddingProvider
from pce.retrieval.indexer import build_index

_ALLOW_ALL = AccessContext(allowed_compartments=None, allow_unclassified=True)


def _build_indexed_corpus(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "pricing.md").write_text(
        "# Nightingale Pricing\n\nThe approved price for the Nightingale project is five thousand dollars.\n"
    )
    (root / "bread.md").write_text("# Sourdough\n\nHow to bake sourdough bread overnight.\n")

    conn = connect(tmp_path / "pce.sqlite3")
    registry = SourceRegistry(conn)
    doc_repo = SourceDocumentRepository(conn)
    source = registry.register("local_file", str(root))
    for doc in LocalFileAdapter(approved_roots=[root]).sync():
        stored = doc_repo.upsert(doc)
        registry.link_document(source.id, stored.id)

    build_index(conn, HashingEmbeddingProvider())
    return conn, doc_repo


def test_search_context_returns_provenance_fields(tmp_path: Path):
    conn, _ = _build_indexed_corpus(tmp_path)
    results = tools.search_context(conn, HashingEmbeddingProvider(), _ALLOW_ALL, "Nightingale price", limit=5)

    assert results
    top = results[0]
    assert top["title"] == "Nightingale Pricing"
    assert set(top.keys()) == {"document_id", "title", "source", "epistemic_role", "sensitivity", "score", "text"}


def test_search_context_respects_access_scope(tmp_path: Path):
    conn, _ = _build_indexed_corpus(tmp_path)
    restricted = AccessContext(allow_unclassified=False)  # excludes UNKNOWN sensitivity
    results = tools.search_context(conn, HashingEmbeddingProvider(), restricted, "Nightingale price", limit=5)
    assert results == []


def test_read_source_returns_full_text(tmp_path: Path):
    conn, doc_repo = _build_indexed_corpus(tmp_path)
    [doc] = [d for d in doc_repo.list() if d.title == "Nightingale Pricing"]

    result = tools.read_source(conn, _ALLOW_ALL, doc.id)
    assert "error" not in result
    assert "five thousand" in result["text"]
    assert result["document_id"] == doc.id


def test_read_source_denies_outside_scope(tmp_path: Path):
    conn, doc_repo = _build_indexed_corpus(tmp_path)
    [doc] = [d for d in doc_repo.list() if d.title == "Nightingale Pricing"]

    result = tools.read_source(conn, AccessContext(allow_unclassified=False), doc.id)
    assert "error" in result
    assert "denied" in result["error"]


def test_read_source_missing_document_returns_error(tmp_path: Path):
    conn, _ = _build_indexed_corpus(tmp_path)
    result = tools.read_source(conn, _ALLOW_ALL, "does-not-exist")
    assert "error" in result


def test_search_memory_reports_not_implemented():
    result = tools.search_memory("anything")
    assert "error" in result
    assert "not implemented" in result["error"]
