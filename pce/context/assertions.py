"""ContextAssertion: a durable claim, tracked separately from raw chunks so
it survives supersession (PRD sections 12-13).

Superseding an assertion never deletes the old one: the old row's status
becomes SUPERSEDED, its valid_until closes at the new assertion's
valid_from, and both rows stay independently retrievable — "what's the
current price" and "why did we originally consider $3" are both answerable.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field

from pce.context.events import ContextEvent, ContextEventType, EventRepository
from pce.context.time import utcnow


class AssertionStatus(StrEnum):
    PROPOSED = "proposed"
    WORKING = "working"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ContextAssertion(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))

    subject: str
    predicate: str
    value: str

    status: AssertionStatus = AssertionStatus.PROPOSED
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    valid_from: datetime = Field(default_factory=utcnow)
    valid_until: datetime | None = None
    last_confirmed_at: datetime | None = None

    source: str | None = None

    supersedes: str | None = None
    superseded_by: str | None = None


def _row_to_assertion(row: sqlite3.Row) -> ContextAssertion:
    return ContextAssertion(
        id=row["id"],
        subject=row["subject"],
        predicate=row["predicate"],
        value=row["value"],
        status=AssertionStatus(row["status"]),
        importance=row["importance"],
        confidence=row["confidence"],
        valid_from=datetime.fromisoformat(row["valid_from"]),
        valid_until=datetime.fromisoformat(row["valid_until"]) if row["valid_until"] else None,
        last_confirmed_at=datetime.fromisoformat(row["last_confirmed_at"]) if row["last_confirmed_at"] else None,
        source=row["source"],
        supersedes=row["supersedes"],
        superseded_by=row["superseded_by"],
    )


class AssertionRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(self, assertion: ContextAssertion) -> ContextAssertion:
        self._conn.execute(
            """
            INSERT INTO context_assertions
                (id, subject, predicate, value, status, importance, confidence,
                 valid_from, valid_until, last_confirmed_at, source, supersedes, superseded_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                assertion.id,
                assertion.subject,
                assertion.predicate,
                assertion.value,
                assertion.status.value,
                assertion.importance,
                assertion.confidence,
                assertion.valid_from.isoformat(),
                assertion.valid_until.isoformat() if assertion.valid_until else None,
                assertion.last_confirmed_at.isoformat() if assertion.last_confirmed_at else None,
                assertion.source,
                assertion.supersedes,
                assertion.superseded_by,
                utcnow().isoformat(),
            ),
        )
        self._conn.commit()
        return assertion

    def get(self, assertion_id: str) -> ContextAssertion | None:
        row = self._conn.execute(
            "SELECT * FROM context_assertions WHERE id = ?", (assertion_id,)
        ).fetchone()
        return _row_to_assertion(row) if row else None

    def list_current(self, subject: str | None = None) -> list[ContextAssertion]:
        """Assertions nothing has superseded yet — the "what's true now"
        view. A rejected assertion can still be current: rejecting a
        proposal is itself the current state of that predicate."""
        if subject is None:
            rows = self._conn.execute(
                "SELECT * FROM context_assertions WHERE superseded_by IS NULL ORDER BY subject, predicate"
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM context_assertions
                WHERE superseded_by IS NULL AND subject = ?
                ORDER BY predicate
                """,
                (subject,),
            ).fetchall()
        return [_row_to_assertion(row) for row in rows]

    def list_history(self, subject: str, predicate: str) -> list[ContextAssertion]:
        """The full supersession chain for one (subject, predicate), oldest
        first — including superseded entries, so past reasoning stays
        retrievable (section 13)."""
        rows = self._conn.execute(
            """
            SELECT * FROM context_assertions
            WHERE subject = ? AND predicate = ?
            ORDER BY valid_from
            """,
            (subject, predicate),
        ).fetchall()
        return [_row_to_assertion(row) for row in rows]

    def supersede(self, old_id: str, new_assertion: ContextAssertion) -> ContextAssertion:
        """Insert new_assertion as the replacement for old_id: close out
        old_id (status -> SUPERSEDED, valid_until -> new_assertion.valid_from,
        superseded_by -> new_assertion.id) and record a SOURCE_SUPERSEDED
        event. Old_id is never deleted or otherwise modified beyond that."""
        old = self.get(old_id)
        if old is None:
            raise ValueError(f"no assertion with id {old_id}")

        linked = new_assertion.model_copy(update={"supersedes": old_id})
        self.create(linked)

        self._conn.execute(
            """
            UPDATE context_assertions
            SET status = ?, valid_until = ?, superseded_by = ?
            WHERE id = ?
            """,
            (AssertionStatus.SUPERSEDED.value, linked.valid_from.isoformat(), linked.id, old_id),
        )
        self._conn.commit()

        EventRepository(self._conn).record(
            ContextEvent(
                event_type=ContextEventType.SOURCE_SUPERSEDED,
                subject=old.subject,
                assertion_id=linked.id,
                description=f"{old.subject} {old.predicate}: {old.value!r} superseded by {linked.value!r}",
                occurred_at=linked.valid_from,
                source=linked.source,
            )
        )
        return linked

    def confirm(self, assertion_id: str) -> ContextAssertion:
        """Record that a human re-confirmed this assertion still holds,
        without changing its value or supersession chain."""
        now = utcnow()
        self._conn.execute(
            "UPDATE context_assertions SET last_confirmed_at = ? WHERE id = ?",
            (now.isoformat(), assertion_id),
        )
        self._conn.commit()
        updated = self.get(assertion_id)
        if updated is None:
            raise ValueError(f"no assertion with id {assertion_id}")
        return updated

    def set_status(self, assertion_id: str, status: AssertionStatus) -> ContextAssertion:
        self._conn.execute(
            "UPDATE context_assertions SET status = ? WHERE id = ?",
            (status.value, assertion_id),
        )
        self._conn.commit()
        updated = self.get(assertion_id)
        if updated is None:
            raise ValueError(f"no assertion with id {assertion_id}")
        return updated
