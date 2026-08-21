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
