from pathlib import Path

from pce.adapters.local_file import LocalFileAdapter
from pce.context.db import connect
from pce.context.models import EpistemicRole, Sensitivity
from pce.context.registry import SourceRegistry
from pce.context.repository import SourceDocumentRepository
from pce.policy.engine import AccessContext
from pce.providers.hashing_embeddings import HashingEmbeddingProvider
from pce.retrieval.indexer import build_index
from pce.retrieval.search import SearchResult, hybrid_search
from pce.router.intent import Intent
from pce.router.search import apply_intent_bias, route_and_search

_ALLOW_ALL = AccessContext(allowed_compartments=None, allow_unclassified=True)


def _fake_result(role: EpistemicRole, score: float) -> SearchResult:
    from pce.context.models import SourceDocument

    doc = SourceDocument(
        source_type="markdown",
        source_system="local_file",
        source_ref="/root/a.md",
        content_hash="hash",
        parser_version="v1",
        chunking_version="v1",
        epistemic_role=role,
    )
    return SearchResult(chunk_id="c1", document=doc, text="text", score=score)


def test_apply_intent_bias_boosts_preferred_role():
    results = [
        _fake_result(EpistemicRole.MEETING_NOTE, score=1.0),
        _fake_result(EpistemicRole.FICTION, score=0.9),
    ]
    reranked = apply_intent_bias(results, Intent.FICTION_WRITING)

    assert reranked[0].document.epistemic_role == EpistemicRole.FICTION
    assert reranked[0].score == 0.9 * 1.5
    assert reranked[1].score == 1.0 * 0.5


def test_apply_intent_bias_is_noop_for_general():
    results = [_fake_result(EpistemicRole.FICTION, score=0.5), _fake_result(EpistemicRole.MEETING_NOTE, score=0.9)]
    reranked = apply_intent_bias(results, Intent.GENERAL)
    assert [r.score for r in reranked] == [0.9, 0.5]  # order unchanged, no bias applied


def _build_corpus(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "fiction.md").write_text(
        "# Chapter Draft\n\nMira walked into the vault, voice steady, ready for the reveal.\n"
    )
    (root / "contract.md").write_text(
        "# Client Agreement\n\nMira Corp committed to a $5,000 contract for the vault security audit.\n"
    )

    conn = connect(tmp_path / "pce.sqlite3")
    registry = SourceRegistry(conn)
    doc_repo = SourceDocumentRepository(conn)
    source = registry.register("local_file", str(root))
    for doc in LocalFileAdapter(approved_roots=[root]).sync():
        stored = doc_repo.upsert(doc)
        registry.link_document(source.id, stored.id)

    for doc in doc_repo.list():
        role = EpistemicRole.FICTION if "fiction" in doc.source_ref else EpistemicRole.CONTRACTUAL_RECORD
        doc_repo.upsert(doc.model_copy(update={"epistemic_role": role, "sensitivity": Sensitivity.PUBLIC}))

    build_index(conn, HashingEmbeddingProvider())
    return conn


def test_route_and_search_classifies_and_reranks(tmp_path: Path):
    conn = _build_corpus(tmp_path)

    intent, results = route_and_search(
        conn, "Rewrite this chapter in my voice, Mira.", HashingEmbeddingProvider(), _ALLOW_ALL, limit=5
    )

    assert intent == Intent.FICTION_WRITING
    assert results
    assert results[0].document.epistemic_role == EpistemicRole.FICTION


def test_route_and_search_prefers_contract_for_business_query(tmp_path: Path):
    conn = _build_corpus(tmp_path)

    intent, results = route_and_search(
        conn, "What did Mira Corp commit to in this contract?", HashingEmbeddingProvider(), _ALLOW_ALL, limit=5
    )

    assert intent == Intent.BUSINESS_WRITING
    assert results
    assert results[0].document.epistemic_role == EpistemicRole.CONTRACTUAL_RECORD


def test_route_and_search_respects_access_context(tmp_path: Path):
    conn = _build_corpus(tmp_path)
    restricted = AccessContext(allow_unclassified=False, allowed_compartments=frozenset({"NOTHING"}))

    # Force every document into a compartment the context doesn't grant.
    doc_repo = SourceDocumentRepository(conn)
    for doc in doc_repo.list():
        doc_repo.upsert(doc.model_copy(update={"compartments": ["SECRET"]}))

    intent, results = route_and_search(
        conn, "Rewrite this chapter in my voice.", HashingEmbeddingProvider(), restricted, limit=5
    )
    assert results == []
