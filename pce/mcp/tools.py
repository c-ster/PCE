"""Tool implementations for the MCP server (PRD section 36) — plain
functions, independent of MCP protocol machinery, so they're directly
unit-testable without spinning up a server or a client.

access_context is fixed by whoever ran `pce serve-mcp`, not a parameter the
connecting model can supply — see pce/mcp/server.py.
"""

from __future__ import annotations

import sqlite3

from pce.context.assertions import AssertionRepository
from pce.context.chunks import ChunkRepository
from pce.context.repository import SourceDocumentRepository
from pce.memory.observations import ObservationRepository
from pce.policy.engine import AccessContext, evaluate
from pce.providers.base import EmbeddingProvider
from pce.router.search import route_and_search
from pce.steward.questions import ContextQuestion, QuestionRepository, QuestionStatus
from pce.steward.scan import DEFAULT_STALENESS_DAYS, run_steward_scan


def search_context(
    conn: sqlite3.Connection,
    embedding_provider: EmbeddingProvider,
    access_context: AccessContext,
    query: str,
    limit: int = 10,
) -> list[dict]:
    intent, results = route_and_search(conn, query, embedding_provider, access_context, limit=limit)
    return [
        {
            "document_id": result.document.id,
            "title": result.document.title or result.document.source_ref,
            "source": result.document.source_ref,
            "epistemic_role": result.document.epistemic_role.value,
            "sensitivity": result.document.sensitivity.value,
            "score": result.score,
            "text": result.text,
            "detected_intent": intent.value,
        }
        for result in results
    ]


def read_source(conn: sqlite3.Connection, access_context: AccessContext, document_id: str) -> dict:
    document = SourceDocumentRepository(conn).get(document_id)
    if not document:
        return {"error": f"no document with id {document_id}"}

    decision = evaluate(document, access_context)
    if not decision.allowed:
        return {"error": f"access denied: {decision.reason}"}

    chunks = ChunkRepository(conn).get_for_document(document_id)
    return {
        "document_id": document.id,
        "title": document.title or document.source_ref,
        "source": document.source_ref,
        "epistemic_role": document.epistemic_role.value,
        "sensitivity": document.sensitivity.value,
        "text": "\n\n".join(chunk.text for chunk in chunks),
    }


def search_memory(conn: sqlite3.Connection, query: str, limit: int = 10) -> list[dict]:
    """Searches durable memory (current ContextAssertions) by plain
    case-insensitive substring match — boring and inspectable, no separate
    index needed at this scale. Does not yet apply sensitivity/compartment
    policy: ContextAssertion has no sensitivity field of its own."""
    lowered = query.lower()
    matches = []
    for assertion in AssertionRepository(conn).list_current():
        haystack = f"{assertion.subject} {assertion.predicate} {assertion.value}".lower()
        if lowered in haystack:
            matches.append(
                {
                    "assertion_id": assertion.id,
                    "subject": assertion.subject,
                    "predicate": assertion.predicate,
                    "value": assertion.value,
                    "status": assertion.status.value,
                    "confidence": assertion.confidence,
                }
            )
    return matches[:limit]


def accept_observation(
    conn: sqlite3.Connection, observation_id: str, predicate: str = "observation", value: str | None = None
) -> dict:
    """"Save": promotes a proposed observation into a durable
    ContextAssertion. Only call this after the human has actually approved
    it (section 25) — this tool itself does not verify that; it does
    whatever it's asked, same as read_source/search_context."""
    try:
        observation, assertion = ObservationRepository(conn).accept(observation_id, predicate=predicate, value=value)
    except ValueError as exc:
        return {"error": str(exc)}
    return {
        "observation_id": observation.id,
        "assertion_id": assertion.id,
        "subject": assertion.subject,
        "predicate": assertion.predicate,
        "value": assertion.value,
    }


def reject_observation(conn: sqlite3.Connection, observation_id: str) -> dict:
    """"Don't save": rejects a proposed observation. No assertion is created."""
    try:
        observation = ObservationRepository(conn).reject(observation_id)
    except ValueError as exc:
        return {"error": str(exc)}
    return {"observation_id": observation.id, "status": observation.status.value}


def _question_to_dict(question: ContextQuestion) -> dict:
    return {
        "id": question.id,
        "question_type": question.question_type.value,
        "urgency": question.urgency.value,
        "subject": question.subject,
        "description": question.description,
        "suggested_answer": question.suggested_answer,
        "status": question.status.value,
    }


def get_context_questions(conn: sqlite3.Connection, include_deferred: bool = False) -> list[dict]:
    """Lists unresolved context questions. Read-only — does not scan for
    new ones; see get_context_review for that."""
    statuses = (QuestionStatus.OPEN, QuestionStatus.DEFERRED) if include_deferred else (QuestionStatus.OPEN,)
    return [_question_to_dict(q) for q in QuestionRepository(conn).list(statuses=statuses)]


def get_context_review(conn: sqlite3.Connection, staleness_days: int = DEFAULT_STALENESS_DAYS) -> dict:
    """Scans for conflicts, staleness, and unreviewed observations, then
    returns the resulting open inbox."""
    new_questions = run_steward_scan(conn, max_age_days=staleness_days)
    open_questions = QuestionRepository(conn).list(statuses=(QuestionStatus.OPEN,))
    return {
        "new_items_found": len(new_questions),
        "open_questions": [_question_to_dict(q) for q in open_questions],
    }


def answer_context_question(
    conn: sqlite3.Connection, question_id: str, note: str, reconfirm: bool = False
) -> dict:
    """Resolves a question with a decision. reconfirm=True also marks any
    related assertions reconfirmed today (for staleness questions)."""
    repo = QuestionRepository(conn)
    question = repo.get(question_id)
    if question is None:
        return {"error": f"no question with id {question_id}"}

    if reconfirm:
        assertion_repo = AssertionRepository(conn)
        for assertion_id in question.related_assertion_ids:
            assertion_repo.confirm(assertion_id)

    return _question_to_dict(repo.answer(question_id, note))


def defer_context_question(conn: sqlite3.Connection, question_id: str) -> dict:
    """Postpones a question — still pending, just deprioritized."""
    try:
        updated = QuestionRepository(conn).defer(question_id)
    except ValueError as exc:
        return {"error": str(exc)}
    return _question_to_dict(updated)


def dismiss_context_question(conn: sqlite3.Connection, question_id: str) -> dict:
    """Dismisses a question — not worth resolving, no action taken."""
    try:
        updated = QuestionRepository(conn).dismiss(question_id)
    except ValueError as exc:
        return {"error": str(exc)}
    return _question_to_dict(updated)
