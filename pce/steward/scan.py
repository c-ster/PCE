"""Context Steward scanning (PRD section 17).

Only detects what's mechanically detectable without an LLM: two unresolved
"current" assertions for the same (subject, predicate) is a genuine
conflict, not a guess; an assertion nobody's reconfirmed in a long time is
genuinely stale by the clock. Ambiguity, recurring themes, and "high-value
missing context" would need real semantic reasoning this build doesn't
have — they are deliberately not attempted here rather than faked with a
heuristic that would just be guessing.
"""

from __future__ import annotations

import sqlite3
from datetime import timedelta

from pce.context.assertions import AssertionRepository
from pce.context.time import utcnow
from pce.memory.observations import ObservationRepository, ObservationStatus
from pce.steward.questions import ContextQuestion, QuestionRepository, QuestionType, QuestionUrgency

DEFAULT_STALENESS_DAYS = 90


def scan_conflicts(conn: sqlite3.Connection) -> list[ContextQuestion]:
    """Two or more assertions still 'current' for the same (subject,
    predicate) that were never linked by supersession — a real, unresolved
    conflict, not a guess. Suggested answer: the more recent one, since
    recency is the one honest signal available without an LLM."""
    assertions = AssertionRepository(conn).list_current()
    groups: dict[tuple[str, str], list] = {}
    for assertion in assertions:
        groups.setdefault((assertion.subject, assertion.predicate), []).append(assertion)

    repo = QuestionRepository(conn)
    created = []
    for (subject, predicate), group in groups.items():
        if len(group) < 2:
            continue

        group.sort(key=lambda a: a.valid_from, reverse=True)
        newest, *rest = group
        others = ", ".join(f"{a.value!r} ({a.valid_from.date()})" for a in rest)

        question = ContextQuestion(
            question_type=QuestionType.ASSERTION_CONFLICT,
            urgency=QuestionUrgency.IMMEDIATE,
            subject=subject,
            description=f"Unresolved conflicting values for {subject} {predicate}: {[a.value for a in group]}",
            suggested_answer=(
                f"{newest.value!r} ({newest.valid_from.date()}) is the most recent — "
                f"more likely current than {others}."
            ),
            related_assertion_ids=[a.id for a in group],
            dedupe_key=f"conflict:{subject}:{predicate}",
        )
        result = repo.create_if_new(question)
        if result is not None:
            created.append(result)

    return created


def scan_staleness(conn: sqlite3.Connection, max_age_days: int = DEFAULT_STALENESS_DAYS) -> list[ContextQuestion]:
    """A current assertion nobody's reconfirmed in max_age_days — a
    freshness signal (section 18), not proof it's false."""
    threshold = timedelta(days=max_age_days)
    now = utcnow()

    repo = QuestionRepository(conn)
    created = []
    for assertion in AssertionRepository(conn).list_current():
        reference = assertion.last_confirmed_at or assertion.valid_from
        if now - reference < threshold:
            continue

        question = ContextQuestion(
            question_type=QuestionType.ASSERTION_STALE,
            urgency=QuestionUrgency.DEFERRED,
            subject=assertion.subject,
            description=(
                f"{assertion.subject} {assertion.predicate} = {assertion.value!r} "
                f"hasn't been reconfirmed since {reference.date()}."
            ),
            suggested_answer=f"Still true as of today? (last confirmed {reference.date()})",
            related_assertion_ids=[assertion.id],
            dedupe_key=f"stale:{assertion.id}",
        )
        result = repo.create_if_new(question)
        if result is not None:
            created.append(result)

    return created


def scan_unreviewed_observations(conn: sqlite3.Connection) -> list[ContextQuestion]:
    """A proposed observation nobody's accepted or rejected yet — surfaced
    in the inbox so it doesn't just sit invisibly in `pce memory list`."""
    repo = QuestionRepository(conn)
    created = []
    for observation in ObservationRepository(conn).list(status=ObservationStatus.PROPOSED):
        question = ContextQuestion(
            question_type=QuestionType.OBSERVATION_REVIEW,
            urgency=QuestionUrgency.DEFERRED,
            subject=observation.subject,
            description=f"Proposed observation about {observation.subject}: {observation.description!r}",
            suggested_answer=observation.description,
            related_observation_id=observation.id,
            dedupe_key=f"observation:{observation.id}",
        )
        result = repo.create_if_new(question)
        if result is not None:
            created.append(result)

    return created


def run_steward_scan(conn: sqlite3.Connection, max_age_days: int = DEFAULT_STALENESS_DAYS) -> list[ContextQuestion]:
    return (
        scan_conflicts(conn)
        + scan_staleness(conn, max_age_days=max_age_days)
        + scan_unreviewed_observations(conn)
    )
