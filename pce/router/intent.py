"""Query intent classification (PRD section 15).

A boring, inspectable keyword heuristic — not an LLM call — consistent with
section 43's dependency philosophy and with core PCE working fully offline.
Swappable later for a real classifier behind the same classify_intent()
signature without touching the router's downstream ranking logic.
"""

from __future__ import annotations

import re
from enum import StrEnum


class Intent(StrEnum):
    PROJECT_FACT_RECALL = "project_fact_recall"
    PROJECT_HISTORY = "project_history"
    DECISION_HISTORY = "decision_history"
    PUBLIC_WRITING = "public_writing"
    BUSINESS_WRITING = "business_writing"
    FICTION_WRITING = "fiction_writing"
    FICTION_CONTINUITY = "fiction_continuity"
    TECHNICAL_RESEARCH = "technical_research"
    IP_RESEARCH = "ip_research"
    RELATIONSHIP_CONTEXT = "relationship_context"
    INTELLECTUAL_INFLUENCE = "intellectual_influence"
    PERSONAL_REFLECTION = "personal_reflection"
    GENERAL = "general"


# Order matters only for tie-breaking (first-listed wins a tie). Keep
# multi-word phrases too — checked against the raw lowercased query, not
# just tokenized words, so "my voice" and "prior art" still match.
_KEYWORDS: dict[Intent, tuple[str, ...]] = {
    Intent.FICTION_WRITING: ("my voice", "chapter", "rewrite", "novel", "short story", "scene", "story"),
    Intent.FICTION_CONTINUITY: ("continuity", "plot", "character arc", "storyline", "previous chapter"),
    Intent.IP_RESEARCH: ("patent", "prior art", "intellectual property", "invention", "ip"),
    Intent.BUSINESS_WRITING: ("commit", "contract", "customer", "client", "proposal", "invoice", "agreement"),
    Intent.DECISION_HISTORY: ("decision", "decided", "approved", "rejected", "why did we"),
    Intent.PROJECT_HISTORY: ("history", "timeline", "originally", "used to be", "over time"),
    Intent.PROJECT_FACT_RECALL: ("status", "deadline", "current price", "budget", "what is the current"),
    Intent.TECHNICAL_RESEARCH: ("architecture", "implementation", "algorithm", "spec", "technical"),
    Intent.PUBLIC_WRITING: ("blog post", "published article", "public writing"),
    Intent.RELATIONSHIP_CONTEXT: ("relationship", "contact info", "colleague", "who is"),
    Intent.INTELLECTUAL_INFLUENCE: ("inspired by", "influenced by", "book", "author", "reading list"),
    Intent.PERSONAL_REFLECTION: ("how do i feel", "reflect", "journal entry", "personal reflection"),
}


# Word-boundary matched, not plain substring containment — otherwise short
# keywords like "ip" match inside unrelated words like "recipe".
_PATTERNS: dict[Intent, tuple[re.Pattern, ...]] = {
    intent: tuple(re.compile(r"\b" + re.escape(phrase) + r"\b") for phrase in phrases)
    for intent, phrases in _KEYWORDS.items()
}


def classify_intent(query: str) -> Intent:
    lowered = query.lower()
    best_intent = Intent.GENERAL
    best_score = 0

    for intent, patterns in _PATTERNS.items():
        score = sum(1 for pattern in patterns if pattern.search(lowered))
        if score > best_score:
            best_score = score
            best_intent = intent

    return best_intent
