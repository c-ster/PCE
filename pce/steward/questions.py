"""The Context Inbox (PRD sections 21-22): unresolved questions the
steward surfaced, waiting for a human to triage — not administration as a
hobby, review in minutes.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field

from pce.context.time import utcnow


class QuestionType(StrEnum):
    ASSERTION_CONFLICT = "assertion_conflict"
    ASSERTION_STALE = "assertion_stale"
    OBSERVATION_REVIEW = "observation_review"


class QuestionUrgency(StrEnum):
    """Section 21: how much this is worth interrupting anything for."""

    IMMEDIATE = "immediate"
    DEFERRED = "deferred"
    SILENT = "silent"


class QuestionStatus(StrEnum):
    OPEN = "open"
    DEFERRED = "deferred"
    DISMISSED = "dismissed"
    ANSWERED = "answered"


class ContextQuestion(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))

    question_type: QuestionType
    urgency: QuestionUrgency = QuestionUrgency.DEFERRED

    subject: str
    description: str
    suggested_answer: str | None = None  # section 19: suggested answer first

    related_assertion_ids: list[str] = Field(default_factory=list)
    related_observation_id: str | None = None

    status: QuestionStatus = QuestionStatus.OPEN
    dedupe_key: str

    created_at: datetime = Field(default_factory=utcnow)
    resolved_at: datetime | None = None
    resolution_note: str | None = None


def _row_to_question(row: sqlite3.Row) -> ContextQuestion:
    return ContextQuestion(
        id=row["id"],
        question_type=QuestionType(row["question_type"]),
        urgency=QuestionUrgency(row["urgency"]),
        subject=row["subject"],
        description=row["description"],
        suggested_answer=row["suggested_answer"],
        related_assertion_ids=json.loads(row["related_assertion_ids"]),
        related_observation_id=row["related_observation_id"],
        status=QuestionStatus(row["status"]),
        dedupe_key=row["dedupe_key"],
        created_at=datetime.fromisoformat(row["created_at"]),
        resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
        resolution_note=row["resolution_note"],
    )


class QuestionRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create_if_new(self, question: ContextQuestion) -> ContextQuestion | None:
        """Insert unless an OPEN question with the same dedupe_key already
        exists — repeated scans shouldn't spam duplicates. Returns None if
        skipped."""
        existing = self._conn.execute(
            "SELECT 1 FROM context_questions WHERE dedupe_key = ? AND status = 'open' LIMIT 1",
            (question.dedupe_key,),
        ).fetchone()
        if existing:
            return None

        self._conn.execute(
            """
            INSERT INTO context_questions
                (id, question_type, urgency, subject, description, suggested_answer,
                 related_assertion_ids, related_observation_id, status, dedupe_key, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                question.id,
                question.question_type.value,
                question.urgency.value,
                question.subject,
                question.description,
                question.suggested_answer,
                json.dumps(question.related_assertion_ids),
                question.related_observation_id,
                question.status.value,
                question.dedupe_key,
                question.created_at.isoformat(),
            ),
        )
        self._conn.commit()
        return question

    def get(self, question_id: str) -> ContextQuestion | None:
        row = self._conn.execute("SELECT * FROM context_questions WHERE id = ?", (question_id,)).fetchone()
        return _row_to_question(row) if row else None

    def list(self, statuses: tuple[QuestionStatus, ...] | None = None) -> list[ContextQuestion]:
        if statuses is None:
            rows = self._conn.execute("SELECT * FROM context_questions ORDER BY created_at").fetchall()
        else:
            placeholders = ", ".join("?" for _ in statuses)
            rows = self._conn.execute(
                f"SELECT * FROM context_questions WHERE status IN ({placeholders}) ORDER BY created_at",
                tuple(s.value for s in statuses),
            ).fetchall()
        return [_row_to_question(row) for row in rows]

    def answer(self, question_id: str, resolution_note: str) -> ContextQuestion:
        return self._resolve(question_id, QuestionStatus.ANSWERED, resolution_note)

    def dismiss(self, question_id: str) -> ContextQuestion:
        return self._resolve(question_id, QuestionStatus.DISMISSED, None)

    def defer(self, question_id: str) -> ContextQuestion:
        """Deferred is not a terminal state — no resolved_at — it's still
        pending, just lower priority than open."""
        question = self.get(question_id)
        if question is None:
            raise ValueError(f"no question with id {question_id}")

        self._conn.execute("UPDATE context_questions SET status = ? WHERE id = ?", (QuestionStatus.DEFERRED.value, question_id))
        self._conn.commit()
        return self.get(question_id)

    def _resolve(
        self, question_id: str, status: QuestionStatus, resolution_note: str | None
    ) -> ContextQuestion:
        question = self.get(question_id)
        if question is None:
            raise ValueError(f"no question with id {question_id}")

        self._conn.execute(
            "UPDATE context_questions SET status = ?, resolved_at = ?, resolution_note = ? WHERE id = ?",
            (status.value, utcnow().isoformat(), resolution_note, question_id),
        )
        self._conn.commit()
        return self.get(question_id)

    def stats(self) -> dict[str, int]:
        rows = self._conn.execute("SELECT status, COUNT(*) AS n FROM context_questions GROUP BY status").fetchall()
        counts = {status.value: 0 for status in QuestionStatus}
        for row in rows:
            counts[row["status"]] = row["n"]
        return counts
