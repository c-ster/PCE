"""Tool implementations for the MCP server (PRD section 36) — plain
functions, independent of MCP protocol machinery, so they're directly
unit-testable without spinning up a server or a client.

access_context is fixed by whoever ran `pce serve-mcp`, not a parameter the
connecting model can supply — see pce/mcp/server.py.
"""

from __future__ import annotations

import sqlite3

from pce.context.chunks import ChunkRepository
from pce.context.repository import SourceDocumentRepository
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


def search_memory(query: str) -> dict:
    return {"error": "search_memory is not implemented yet in this build (PRD section 25, Memory Governance)"}
