from datetime import datetime, timezone
from pathlib import Path

from pce.context.assertions import AssertionRepository, ContextAssertion
from pce.context.db import connect
from pce.context.events import ContextEvent, ContextEventType, EventRepository


def test_record_and_get_round_trips(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = EventRepository(conn)

    event = repo.record(
        ContextEvent(
            event_type=ContextEventType.PROJECT_STARTED,
            subject="project:nightingale",
            description="Nightingale kicked off",
        )
    )

    fetched = repo.get(event.id)
    assert fetched == event


def test_for_subject_returns_events_in_chronological_order(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = EventRepository(conn)

    early = datetime(2026, 1, 1, tzinfo=timezone.utc)
    late = datetime(2026, 3, 1, tzinfo=timezone.utc)

    repo.record(
        ContextEvent(
            event_type=ContextEventType.PROJECT_STARTED,
            subject="project:nightingale",
            description="started",
            occurred_at=late,
        )
    )
    repo.record(
        ContextEvent(
            event_type=ContextEventType.IDEA_PROPOSED,
            subject="project:nightingale",
            description="proposed",
            occurred_at=early,
        )
    )

    events = repo.for_subject("project:nightingale")
    assert [e.event_type for e in events] == [ContextEventType.IDEA_PROPOSED, ContextEventType.PROJECT_STARTED]


def test_for_subject_ignores_other_subjects(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = EventRepository(conn)

    repo.record(
        ContextEvent(event_type=ContextEventType.PROJECT_STARTED, subject="project:a", description="a started")
    )
    repo.record(
        ContextEvent(event_type=ContextEventType.PROJECT_STARTED, subject="project:b", description="b started")
    )

    assert len(repo.for_subject("project:a")) == 1


def test_for_assertion_filters_by_assertion_id(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = EventRepository(conn)
    assertions = AssertionRepository(conn)

    assertion_1 = assertions.create(ContextAssertion(subject="project:a", predicate="price", value="1"))
    assertion_2 = assertions.create(ContextAssertion(subject="project:b", predicate="price", value="2"))

    repo.record(
        ContextEvent(
            event_type=ContextEventType.SOURCE_SUPERSEDED,
            subject="project:a",
            assertion_id=assertion_1.id,
            description="superseded",
        )
    )
    repo.record(
        ContextEvent(
            event_type=ContextEventType.SOURCE_SUPERSEDED,
            subject="project:b",
            assertion_id=assertion_2.id,
            description="superseded",
        )
    )

    events = repo.for_assertion(assertion_1.id)
    assert len(events) == 1
    assert events[0].assertion_id == assertion_1.id
