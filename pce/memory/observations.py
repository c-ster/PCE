"""Durable memory governance (PRD sections 24-25).

The model may propose noticing a pattern — a ContextObservation — but it
must never silently become authoritative durable memory. Accepting one
creates a ContextAssertion (reusing the existing durable-claim
infrastructure rather than a second, parallel one); rejecting or letting
it expire leaves no durable trace. This is the mechanism behind the
"Suggested memory: Save / Edit / Don't save" interaction in section 25.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field

from pce.context.assertions import AssertionRepository, AssertionStatus, ContextAssertion
from pce.context.time import utcnow


class ObservationStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ContextObservation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))

    subject: str
    description: str

    status: ObservationStatus = ObservationStatus.PROPOSED
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    source: str | None = None
    resulting_assertion_id: str | None = None

    created_at: datetime = Field(default_factory=utcnow)
    resolved_at: datetime | None = None


def _row_to_observation(row: sqlite3.Row) -> ContextObservation:
    return ContextObservation(
        id=row["id"],
        subject=row["subject"],
        description=row["description"],
        status=ObservationStatus(row["status"]),
        confidence=row["confidence"],
        source=row["source"],
        resulting_assertion_id=row["resulting_assertion_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
    )


class ObservationRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(self, observation: ContextObservation) -> ContextObservation:
        self._conn.execute(
            """
            INSERT INTO context_observations
                (id, subject, description, status, confidence, source, resulting_assertion_id, created_at, resolved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation.id,
                observation.subject,
                observation.description,
                observation.status.value,
                observation.confidence,
                observation.source,
                observation.resulting_assertion_id,
                observation.created_at.isoformat(),
                observation.resolved_at.isoformat() if observation.resolved_at else None,
            ),
        )
        self._conn.commit()
        return observation

    def get(self, observation_id: str) -> ContextObservation | None:
        row = self._conn.execute(
            "SELECT * FROM context_observations WHERE id = ?", (observation_id,)
        ).fetchone()
        return _row_to_observation(row) if row else None

    def list(self, status: ObservationStatus | None = None) -> list[ContextObservation]:
        if status is None:
            rows = self._conn.execute("SELECT * FROM context_observations ORDER BY created_at").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM context_observations WHERE status = ? ORDER BY created_at", (status.value,)
            ).fetchall()
        return [_row_to_observation(row) for row in rows]

    def edit(self, observation_id: str, description: str) -> ContextObservation:
        """Only meaningful while still PROPOSED — matches the "Edit" option
        in the Save/Edit/Don't save interaction, before it's ever durable."""
        observation = self.get(observation_id)
        if observation is None:
            raise ValueError(f"no observation with id {observation_id}")
        if observation.status != ObservationStatus.PROPOSED:
            raise ValueError(f"observation {observation_id} is {observation.status}, not proposed — nothing to edit")

        self._conn.execute(
            "UPDATE context_observations SET description = ? WHERE id = ?", (description, observation_id)
        )
        self._conn.commit()
        return self.get(observation_id)

    def accept(
        self, observation_id: str, predicate: str = "observation", value: str | None = None
    ) -> tuple[ContextObservation, ContextAssertion]:
        """"Save": create the durable ContextAssertion and mark this
        observation accepted. value defaults to the observation's own
        description if not overridden."""
        observation = self.get(observation_id)
        if observation is None:
            raise ValueError(f"no observation with id {observation_id}")
        if observation.status != ObservationStatus.PROPOSED:
            raise ValueError(f"observation {observation_id} is already {observation.status}")

        assertion = AssertionRepository(self._conn).create(
            ContextAssertion(
                subject=observation.subject,
                predicate=predicate,
                value=value if value is not None else observation.description,
                status=AssertionStatus.APPROVED,
                confidence=observation.confidence,
                source=observation.source,
            )
        )

        now = utcnow()
        self._conn.execute(
            """
            UPDATE context_observations
            SET status = ?, resulting_assertion_id = ?, resolved_at = ?
            WHERE id = ?
            """,
            (ObservationStatus.ACCEPTED.value, assertion.id, now.isoformat(), observation_id),
        )
        self._conn.commit()
        return self.get(observation_id), assertion

    def reject(self, observation_id: str) -> ContextObservation:
        return self._resolve(observation_id, ObservationStatus.REJECTED)

    def expire(self, observation_id: str) -> ContextObservation:
        return self._resolve(observation_id, ObservationStatus.EXPIRED)

    def _resolve(self, observation_id: str, status: ObservationStatus) -> ContextObservation:
        observation = self.get(observation_id)
        if observation is None:
            raise ValueError(f"no observation with id {observation_id}")
        if observation.status != ObservationStatus.PROPOSED:
            raise ValueError(f"observation {observation_id} is already {observation.status}")

        self._conn.execute(
            "UPDATE context_observations SET status = ?, resolved_at = ? WHERE id = ?",
            (status.value, utcnow().isoformat(), observation_id),
        )
        self._conn.commit()
        return self.get(observation_id)
