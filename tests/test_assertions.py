from datetime import datetime, timezone
from pathlib import Path

import pytest

from pce.context.assertions import AssertionRepository, AssertionStatus, ContextAssertion
from pce.context.db import connect
from pce.context.events import ContextEventType, EventRepository

JANUARY = datetime(2026, 1, 15, tzinfo=timezone.utc)
MARCH = datetime(2026, 3, 1, tzinfo=timezone.utc)


def test_create_and_get_round_trips(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = AssertionRepository(conn)

    created = repo.create(
        ContextAssertion(subject="project:nightingale", predicate="price", value="3000")
    )

    fetched = repo.get(created.id)
    assert fetched == created
    assert fetched.status == AssertionStatus.PROPOSED  # default


def test_acceptance_scenario_current_vs_historical(tmp_path: Path):
    """PRD section 49, "Temporal state": January proposed, March approved —
    current queries return March, historical queries still reach January."""
    conn = connect(tmp_path / "pce.sqlite3")
    repo = AssertionRepository(conn)

    january = repo.create(
        ContextAssertion(
            subject="project:nightingale",
            predicate="status",
            value="proposed",
            status=AssertionStatus.PROPOSED,
            valid_from=JANUARY,
        )
    )
    march = repo.supersede(
        january.id,
        ContextAssertion(
            subject="project:nightingale",
            predicate="status",
            value="approved",
            status=AssertionStatus.APPROVED,
            valid_from=MARCH,
        ),
    )

    [current] = repo.list_current(subject="project:nightingale")
    assert current.id == march.id
    assert current.value == "approved"

    history = repo.list_history("project:nightingale", "status")
    assert [a.value for a in history] == ["proposed", "approved"]

    reloaded_january = repo.get(january.id)
    assert reloaded_january.status == AssertionStatus.SUPERSEDED
    assert reloaded_january.superseded_by == march.id
    assert reloaded_january.valid_until == MARCH
    assert reloaded_january.value == "proposed"  # never mutated


def test_supersede_emits_source_superseded_event(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = AssertionRepository(conn)

    old = repo.create(ContextAssertion(subject="project:nightingale", predicate="price", value="3000"))
    new = repo.supersede(
        old.id, ContextAssertion(subject="project:nightingale", predicate="price", value="5000")
    )

    [event] = EventRepository(conn).for_assertion(new.id)
    assert event.event_type == ContextEventType.SOURCE_SUPERSEDED
    assert "3000" in event.description and "5000" in event.description


def test_supersede_unknown_id_raises(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = AssertionRepository(conn)

    with pytest.raises(ValueError):
        repo.supersede("does-not-exist", ContextAssertion(subject="a", predicate="b", value="c"))


def test_list_current_excludes_superseded_but_keeps_other_subjects(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = AssertionRepository(conn)

    old = repo.create(ContextAssertion(subject="project:a", predicate="price", value="1"))
    repo.supersede(old.id, ContextAssertion(subject="project:a", predicate="price", value="2"))
    repo.create(ContextAssertion(subject="project:b", predicate="price", value="9"))

    current = repo.list_current()
    subjects_and_values = {(a.subject, a.value) for a in current}
    assert subjects_and_values == {("project:a", "2"), ("project:b", "9")}


def test_rejected_assertion_can_still_be_current(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = AssertionRepository(conn)

    created = repo.create(
        ContextAssertion(subject="project:a", predicate="price_increase", value="declined", status=AssertionStatus.REJECTED)
    )

    [current] = repo.list_current(subject="project:a")
    assert current.id == created.id
    assert current.status == AssertionStatus.REJECTED


def test_confirm_sets_last_confirmed_at_without_changing_value(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = AssertionRepository(conn)

    created = repo.create(ContextAssertion(subject="a", predicate="b", value="c"))
    assert created.last_confirmed_at is None

    confirmed = repo.confirm(created.id)
    assert confirmed.last_confirmed_at is not None
    assert confirmed.value == "c"


def test_set_status_updates_in_place(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = AssertionRepository(conn)

    created = repo.create(ContextAssertion(subject="a", predicate="b", value="c"))
    updated = repo.set_status(created.id, AssertionStatus.APPROVED)

    assert updated.status == AssertionStatus.APPROVED
    assert updated.id == created.id


def test_importance_and_confidence_are_bounded(tmp_path: Path):
    with pytest.raises(Exception):
        ContextAssertion(subject="a", predicate="b", value="c", importance=1.5)
    with pytest.raises(Exception):
        ContextAssertion(subject="a", predicate="b", value="c", confidence=-0.1)


def test_deleting_source_document_keeps_assertion(tmp_path: Path):
    """Assertions are durable interpreted memory, not raw content — removing
    the document that supported a claim must not erase the claim itself."""
    from pce.context.models import SourceDocument
    from pce.context.repository import SourceDocumentRepository

    conn = connect(tmp_path / "pce.sqlite3")
    doc = SourceDocumentRepository(conn).upsert(
        SourceDocument(
            source_type="markdown",
            source_system="local_file",
            source_ref="/root/a.md",
            content_hash="hash-1",
            parser_version="v1",
            chunking_version="v1",
        )
    )

    repo = AssertionRepository(conn)
    created = repo.create(ContextAssertion(subject="a", predicate="b", value="c", source=doc.id))

    SourceDocumentRepository(conn).delete(doc.id)

    survived = repo.get(created.id)
    assert survived is not None
    assert survived.source is None  # FK ON DELETE SET NULL
