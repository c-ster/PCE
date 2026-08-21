from pathlib import Path

from pce.adapters.local_file import LocalFileAdapter
from pce.context.assertions import AssertionRepository, ContextAssertion
from pce.context.db import connect
from pce.context.registry import SourceRegistry
from pce.context.repository import SourceDocumentRepository
from pce.mcp import tools
from pce.memory.observations import ContextObservation, ObservationRepository
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
    assert set(top.keys()) == {
        "document_id",
        "title",
        "source",
        "epistemic_role",
        "sensitivity",
        "score",
        "text",
        "detected_intent",
    }


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


def test_search_memory_finds_current_assertions(tmp_path: Path):
    conn, _ = _build_indexed_corpus(tmp_path)
    AssertionRepository(conn).create(
        ContextAssertion(subject="project:nightingale", predicate="price", value="5000")
    )

    results = tools.search_memory(conn, "nightingale")
    assert len(results) == 1
    assert results[0]["subject"] == "project:nightingale"


def test_search_memory_no_match_returns_empty(tmp_path: Path):
    conn, _ = _build_indexed_corpus(tmp_path)
    assert tools.search_memory(conn, "nonexistent-subject") == []


def test_accept_observation_creates_assertion(tmp_path: Path):
    conn, _ = _build_indexed_corpus(tmp_path)
    observation = ObservationRepository(conn).create(
        ContextObservation(subject="user:preferences", description="Likes terse answers.")
    )

    result = tools.accept_observation(conn, observation.id)
    assert "error" not in result
    assert result["value"] == "Likes terse answers."

    [current] = AssertionRepository(conn).list_current(subject="user:preferences")
    assert current.id == result["assertion_id"]


def test_accept_observation_unknown_id_returns_error(tmp_path: Path):
    conn, _ = _build_indexed_corpus(tmp_path)
    result = tools.accept_observation(conn, "does-not-exist")
    assert "error" in result


def test_reject_observation_creates_no_assertion(tmp_path: Path):
    conn, _ = _build_indexed_corpus(tmp_path)
    observation = ObservationRepository(conn).create(
        ContextObservation(subject="user:preferences", description="Some pattern.")
    )

    result = tools.reject_observation(conn, observation.id)
    assert result["status"] == "rejected"
    assert AssertionRepository(conn).list_current() == []


def test_get_context_review_finds_conflict_and_lists_it(tmp_path: Path):
    conn, _ = _build_indexed_corpus(tmp_path)
    AssertionRepository(conn).create(
        ContextAssertion(subject="project:a", predicate="price", value="3000")
    )
    AssertionRepository(conn).create(
        ContextAssertion(subject="project:a", predicate="price", value="5000")
    )

    review = tools.get_context_review(conn)
    assert review["new_items_found"] == 1
    assert len(review["open_questions"]) == 1
    assert review["open_questions"][0]["question_type"] == "assertion_conflict"


def test_get_context_questions_is_read_only(tmp_path: Path):
    conn, _ = _build_indexed_corpus(tmp_path)
    AssertionRepository(conn).create(ContextAssertion(subject="project:a", predicate="price", value="3000"))
    AssertionRepository(conn).create(ContextAssertion(subject="project:a", predicate="price", value="5000"))

    assert tools.get_context_questions(conn) == []  # no scan has run yet
    tools.get_context_review(conn)
    assert len(tools.get_context_questions(conn)) == 1


def test_answer_context_question_with_reconfirm(tmp_path: Path):
    conn, _ = _build_indexed_corpus(tmp_path)
    assertion = AssertionRepository(conn).create(
        ContextAssertion(subject="project:a", predicate="status", value="approved")
    )
    review = tools.get_context_review(conn, staleness_days=0)
    [question] = review["open_questions"]

    result = tools.answer_context_question(conn, question["id"], "still true", reconfirm=True)
    assert result["status"] == "answered"

    reconfirmed = AssertionRepository(conn).get(assertion.id)
    assert reconfirmed.last_confirmed_at is not None


def test_defer_and_dismiss_context_question(tmp_path: Path):
    conn, _ = _build_indexed_corpus(tmp_path)
    AssertionRepository(conn).create(ContextAssertion(subject="project:a", predicate="price", value="3000"))
    AssertionRepository(conn).create(ContextAssertion(subject="project:a", predicate="price", value="5000"))
    review = tools.get_context_review(conn)
    [question] = review["open_questions"]

    deferred = tools.defer_context_question(conn, question["id"])
    assert deferred["status"] == "deferred"
    assert tools.get_context_questions(conn) == []

    dismissed = tools.dismiss_context_question(conn, question["id"])
    assert dismissed["status"] == "dismissed"


def test_answer_context_question_unknown_id_returns_error(tmp_path: Path):
    conn, _ = _build_indexed_corpus(tmp_path)
    result = tools.answer_context_question(conn, "does-not-exist", "note")
    assert "error" in result
