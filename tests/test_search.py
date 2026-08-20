from pathlib import Path

from pce.adapters.local_file import LocalFileAdapter
from pce.context.db import connect
from pce.context.registry import SourceRegistry
from pce.context.repository import SourceDocumentRepository
from pce.policy.engine import AccessContext
from pce.providers.hashing_embeddings import HashingEmbeddingProvider
from pce.retrieval.indexer import build_index
from pce.retrieval.search import hybrid_search

_ALLOW_ALL = AccessContext(allowed_compartments=None, allow_unclassified=True)


def _build_indexed_corpus(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "pricing.md").write_text(
        "# Nightingale Pricing\n\nThe approved price for the Nightingale project is five thousand dollars.\n"
    )
    (root / "bread.md").write_text(
        "# Sourdough\n\nHow to bake sourdough bread with a long slow overnight rise.\n"
    )

    conn = connect(tmp_path / "pce.sqlite3")
    registry = SourceRegistry(conn)
    doc_repo = SourceDocumentRepository(conn)
    source = registry.register("local_file", str(root))
    for doc in LocalFileAdapter(approved_roots=[root]).sync():
        stored = doc_repo.upsert(doc)
        registry.link_document(source.id, stored.id)

    build_index(conn, HashingEmbeddingProvider())
    return conn


def test_hybrid_search_ranks_relevant_document_first(tmp_path: Path):
    conn = _build_indexed_corpus(tmp_path)
    results = hybrid_search(conn, "Nightingale price approved", HashingEmbeddingProvider(), _ALLOW_ALL, limit=5)

    assert results
    assert results[0].document.title == "Nightingale Pricing"


def test_hybrid_search_returns_empty_for_unindexed_corpus(tmp_path: Path):
    conn = connect(tmp_path / "empty.sqlite3")
    results = hybrid_search(conn, "anything at all", HashingEmbeddingProvider(), _ALLOW_ALL, limit=5)
    assert results == []


def test_hybrid_search_respects_limit(tmp_path: Path):
    conn = _build_indexed_corpus(tmp_path)
    results = hybrid_search(conn, "the", HashingEmbeddingProvider(), _ALLOW_ALL, limit=1)
    assert len(results) <= 1


def test_hybrid_search_excludes_unclassified_by_default(tmp_path: Path):
    conn = _build_indexed_corpus(tmp_path)
    default_context = AccessContext()  # allow_unclassified defaults to False

    results = hybrid_search(conn, "Nightingale price approved", HashingEmbeddingProvider(), default_context, limit=5)
    assert results == []


def test_hybrid_search_respects_compartment_scope(tmp_path: Path):
    conn = _build_indexed_corpus(tmp_path)
    doc_repo = SourceDocumentRepository(conn)
    [pricing_doc] = [d for d in doc_repo.list() if d.title == "Nightingale Pricing"]
    doc_repo.upsert(pricing_doc.model_copy(update={"compartments": ["CLIENT_A"]}))

    excluded = hybrid_search(
        conn,
        "Nightingale price approved",
        HashingEmbeddingProvider(),
        AccessContext(allowed_compartments=frozenset({"OTHER"}), allow_unclassified=True),
        limit=5,
    )
    assert all(r.document.title != "Nightingale Pricing" for r in excluded)

    included = hybrid_search(
        conn,
        "Nightingale price approved",
        HashingEmbeddingProvider(),
        AccessContext(allowed_compartments=frozenset({"CLIENT_A"}), allow_unclassified=True),
        limit=5,
    )
    assert any(r.document.title == "Nightingale Pricing" for r in included)
