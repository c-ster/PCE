"""Deterministic policy engine (PRD section 26).

The LLM is not the security boundary — this is. Every retrieval path must
compute the eligible document set from an AccessContext *before* running
lexical/semantic scoring (section 29, "policy before ranking"), not filter
a ranked list afterward.
"""

from __future__ import annotations

from dataclasses import dataclass

from pce.context.models import Sensitivity, SourceDocument


@dataclass(frozen=True)
class AccessContext:
    """What a given request is allowed to see.

    allowed_compartments=None means no compartment restriction (a document
    is visible regardless of what compartments it's in). An empty
    frozenset means no compartments are granted — only documents with no
    compartments at all remain visible.

    allow_unclassified=False (the default) excludes UNKNOWN-sensitivity
    documents, per section 27: "UNKNOWN must fail closed by default."
    """

    allowed_compartments: frozenset[str] | None = None
    allow_unclassified: bool = False


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


def evaluate(document: SourceDocument, context: AccessContext) -> PolicyDecision:
    if document.sensitivity == Sensitivity.UNKNOWN and not context.allow_unclassified:
        return PolicyDecision(
            allowed=False,
            reason=(
                "sensitivity is UNKNOWN and this request does not allow unclassified "
                "sources (PRD section 27: UNKNOWN fails closed by default)"
            ),
        )

    if context.allowed_compartments is not None and document.compartments:
        if not (set(document.compartments) & context.allowed_compartments):
            return PolicyDecision(
                allowed=False,
                reason=(
                    f"document is scoped to compartment(s) {sorted(document.compartments)}, "
                    f"none of which are in the allowed scope {sorted(context.allowed_compartments)}"
                ),
            )

    return PolicyDecision(allowed=True, reason="sensitivity and compartment checks passed")


def eligible_document_ids(documents: list[SourceDocument], context: AccessContext) -> set[str]:
    return {doc.id for doc in documents if evaluate(doc, context).allowed}
