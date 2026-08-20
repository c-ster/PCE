"""Append-only context event history (PRD section 14).

Answers "how did this change over time," not just "what does the latest
document say." Events are recorded explicitly by callers that know the
semantic meaning of what happened — nothing here infers an event type from
assertion state, since e.g. PROJECT_STARTED and RELATIONSHIP_CHANGED aren't
derivable from a status field. The one exception is AssertionRepository.
supersede(), which always means SOURCE_SUPERSEDED by definition.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field

from pce.context.time import utcnow


class ContextEventType(StrEnum):
    IDEA_PROPOSED = "idea_proposed"
    DECISION_MADE = "decision_made"
    DECISION_REVERSED = "decision_reversed"
    ASSUMPTION_INVALIDATED = "assumption_invalidated"
    PROJECT_STARTED = "project_started"
    PROJECT_PAUSED = "project_paused"
    PROJECT_COMPLETED = "project_completed"
    PERSON_JOINED = "person_joined"
    PERSON_ROLE_CHANGED = "person_role_changed"
    RELATIONSHIP_CHANGED = "relationship_changed"
    PREFERENCE_CHANGED = "preference_changed"
    MILESTONE_REACHED = "milestone_reached"
    STATUS_CHANGED = "status_changed"
    SOURCE_SUPERSEDED = "source_superseded"


class ContextEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))

    event_type: ContextEventType
    subject: str
    assertion_id: str | None = None
    description: str

    occurred_at: datetime = Field(default_factory=utcnow)
    recorded_at: datetime = Field(default_factory=utcnow)

    source: str | None = None


def _row_to_event(row: sqlite3.Row) -> ContextEvent:
    return ContextEvent(
        id=row["id"],
        event_type=ContextEventType(row["event_type"]),
        subject=row["subject"],
        assertion_id=row["assertion_id"],
        description=row["description"],
        occurred_at=datetime.fromisoformat(row["occurred_at"]),
        recorded_at=datetime.fromisoformat(row["recorded_at"]),
        source=row["source"],
    )


class EventRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def record(self, event: ContextEvent) -> ContextEvent:
        self._conn.execute(
            """
            INSERT INTO context_events
                (id, event_type, subject, assertion_id, description, occurred_at, recorded_at, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.event_type.value,
                event.subject,
                event.assertion_id,
                event.description,
                event.occurred_at.isoformat(),
                event.recorded_at.isoformat(),
                event.source,
            ),
        )
        self._conn.commit()
        return event

    def get(self, event_id: str) -> ContextEvent | None:
        row = self._conn.execute("SELECT * FROM context_events WHERE id = ?", (event_id,)).fetchone()
        return _row_to_event(row) if row else None

    def for_subject(self, subject: str) -> list[ContextEvent]:
        rows = self._conn.execute(
            "SELECT * FROM context_events WHERE subject = ? ORDER BY occurred_at", (subject,)
        ).fetchall()
        return [_row_to_event(row) for row in rows]

    def for_assertion(self, assertion_id: str) -> list[ContextEvent]:
        rows = self._conn.execute(
            "SELECT * FROM context_events WHERE assertion_id = ? ORDER BY occurred_at", (assertion_id,)
        ).fetchall()
        return [_row_to_event(row) for row in rows]

    def list(self) -> list[ContextEvent]:
        rows = self._conn.execute("SELECT * FROM context_events ORDER BY occurred_at").fetchall()
        return [_row_to_event(row) for row in rows]
