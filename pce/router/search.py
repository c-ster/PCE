"""Context Router (PRD section 15): classify query intent, then bias
ranking toward the epistemic roles that intent's own PRD examples call for.

This runs strictly after hybrid_search, which has already applied policy
filtering — routing only reorders documents already eligible to be seen,
it never makes an ineligible document visible (section 29, policy before
ranking still holds).
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace

from pce.context.models import EpistemicRole
from pce.policy.engine import AccessContext
from pce.providers.base import EmbeddingProvider
from pce.retrieval.search import SearchResult, hybrid_search
from pce.router.intent import Intent, classify_intent

_BOOST = 1.5
_PENALTY = 0.5

# Preferred/deprioritized roles per intent, per PRD section 15's own worked
# examples ("rewrite this chapter in my voice" / "what did we commit to
# this customer"); the rest are direct name-correspondence with the role
# enum, not invented taxonomy. Intents without a clear correspondence are
# left unbiased (GENERAL always is).
_PREFERRED: dict[Intent, frozenset[EpistemicRole]] = {
    Intent.FICTION_WRITING: frozenset({EpistemicRole.FICTION, EpistemicRole.CREATIVE_NOTE, EpistemicRole.PERSONAL_VIEW}),
    Intent.FICTION_CONTINUITY: frozenset({EpistemicRole.FICTION, EpistemicRole.CREATIVE_NOTE}),
    Intent.BUSINESS_WRITING: frozenset(
        {EpistemicRole.CONTRACTUAL_RECORD, EpistemicRole.CORRESPONDENCE, EpistemicRole.DECISION_RECORD, EpistemicRole.PROJECT_SPECIFICATION}
    ),
    Intent.DECISION_HISTORY: frozenset({EpistemicRole.DECISION_RECORD, EpistemicRole.MEETING_NOTE}),
    Intent.PROJECT_HISTORY: frozenset(
        {EpistemicRole.PROJECT_SPECIFICATION, EpistemicRole.DECISION_RECORD, EpistemicRole.MEETING_NOTE}
    ),
    Intent.PROJECT_FACT_RECALL: frozenset({EpistemicRole.PROJECT_SPECIFICATION, EpistemicRole.DECISION_RECORD}),
    Intent.IP_RESEARCH: frozenset({EpistemicRole.FORMAL_IP_RECORD}),
    Intent.TECHNICAL_RESEARCH: frozenset({EpistemicRole.PROJECT_SPECIFICATION, EpistemicRole.REFERENCE_MATERIAL}),
    Intent.PUBLIC_WRITING: frozenset({EpistemicRole.PUBLIC_WRITING}),
    Intent.RELATIONSHIP_CONTEXT: frozenset({EpistemicRole.CORRESPONDENCE, EpistemicRole.CONVERSATION}),
    Intent.INTELLECTUAL_INFLUENCE: frozenset({EpistemicRole.INTELLECTUAL_INFLUENCE, EpistemicRole.READING_NOTE}),
    Intent.PERSONAL_REFLECTION: frozenset({EpistemicRole.PERSONAL_VIEW}),
}

_DEPRIORITIZED: dict[Intent, frozenset[EpistemicRole]] = {
    Intent.FICTION_WRITING: frozenset(
        {EpistemicRole.PROJECT_SPECIFICATION, EpistemicRole.FORMAL_IP_RECORD, EpistemicRole.MEETING_NOTE}
    ),
    Intent.FICTION_CONTINUITY: frozenset(
        {EpistemicRole.PROJECT_SPECIFICATION, EpistemicRole.FORMAL_IP_RECORD, EpistemicRole.MEETING_NOTE}
    ),
    Intent.BUSINESS_WRITING: frozenset({EpistemicRole.FICTION, EpistemicRole.READING_NOTE, EpistemicRole.PUBLIC_WRITING}),
    Intent.DECISION_HISTORY: frozenset({EpistemicRole.FICTION, EpistemicRole.CREATIVE_NOTE}),
    Intent.PROJECT_HISTORY: frozenset({EpistemicRole.FICTION, EpistemicRole.CREATIVE_NOTE}),
    Intent.PROJECT_FACT_RECALL: frozenset({EpistemicRole.FICTION, EpistemicRole.CREATIVE_NOTE}),
}


def apply_intent_bias(results: list[SearchResult], intent: Intent) -> list[SearchResult]:
    preferred = _PREFERRED.get(intent, frozenset())
    deprioritized = _DEPRIORITIZED.get(intent, frozenset())

    adjusted = []
    for result in results:
        weight = 1.0
        role = result.document.epistemic_role
        if role in preferred:
            weight = _BOOST
        elif role in deprioritized:
            weight = _PENALTY
        adjusted.append(replace(result, score=result.score * weight))

    adjusted.sort(key=lambda r: r.score, reverse=True)
    return adjusted


def route_and_search(
    conn: sqlite3.Connection,
    query: str,
    embedding_provider: EmbeddingProvider,
    access_context: AccessContext,
    limit: int = 10,
) -> tuple[Intent, list[SearchResult]]:
    intent = classify_intent(query)
    candidates = hybrid_search(conn, query, embedding_provider, access_context, limit=limit * 3)
    reranked = apply_intent_bias(candidates, intent)
    return intent, reranked[:limit]
