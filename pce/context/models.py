"""Canonical context model: SourceDocument and its supporting enums.

See docs/ARCHITECTURE.md section "Canonical context model" and PRD sections
7-9, 27.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field

from pce.context.time import utcnow


class EpistemicRole(StrEnum):
    """What kind of evidence a SourceDocument represents.

    Prevents common errors: a novel should not automatically represent the
    user's beliefs, a brainstorm should not become a decision, a patent
    should not automatically represent the current implementation.
    """

    PROJECT_SPECIFICATION = "project_specification"
    DECISION_RECORD = "decision_record"
    FORMAL_IP_RECORD = "formal_ip_record"
    CORRESPONDENCE = "correspondence"
    MEETING_NOTE = "meeting_note"
    PERSONAL_VIEW = "personal_view"
    PUBLIC_WRITING = "public_writing"
    FICTION = "fiction"
    CREATIVE_NOTE = "creative_note"
    INTELLECTUAL_INFLUENCE = "intellectual_influence"
    READING_NOTE = "reading_note"
    REFERENCE_MATERIAL = "reference_material"
    CONVERSATION = "conversation"
    CONTRACTUAL_RECORD = "contractual_record"
    PRESENTATION = "presentation"
    UNKNOWN = "unknown"


class Sensitivity(StrEnum):
    """Access-control level. UNKNOWN fails closed by default."""

    PUBLIC = "public"
    PRIVATE = "private"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    UNKNOWN = "unknown"


class SourceStatus(StrEnum):
    """Lifecycle status of a SourceDocument itself (not its content's truth
    value — see ContextAssertion for that)."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    REMOVED = "removed"


class SourceDocument(BaseModel):
    """A single ingested resource, in PCE's canonical context model."""

    id: str = Field(default_factory=lambda: str(uuid4()))

    source_type: str
    source_system: str
    source_ref: str
    source_version: str | None = None

    title: str | None = None
    author: str | None = None
    authorship: str | None = None

    created_at_source: datetime | None = None
    updated_at_source: datetime | None = None
    ingested_at: datetime = Field(default_factory=utcnow)

    domains: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)

    epistemic_role: EpistemicRole = EpistemicRole.UNKNOWN
    authority: str | None = None
    status: SourceStatus = SourceStatus.ACTIVE

    sensitivity: Sensitivity = Sensitivity.UNKNOWN
    compartments: list[str] = Field(default_factory=list)

    voice_sample: bool = False
    fiction: bool = False

    content_hash: str
    parser_version: str
    chunking_version: str
    embedding_generation: str | None = None
