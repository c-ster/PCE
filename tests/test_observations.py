from pathlib import Path

import pytest

from pce.context.assertions import AssertionRepository
from pce.context.db import connect
from pce.memory.observations import ContextObservation, ObservationRepository, ObservationStatus


def _obs(**overrides) -> ContextObservation:
    defaults = dict(subject="user:preferences", description="Prefers concise technical explanations.")
    defaults.update(overrides)
    return ContextObservation(**defaults)


def test_create_defaults_to_proposed(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = ObservationRepository(conn)
    created = repo.create(_obs())

    assert created.status == ObservationStatus.PROPOSED
    assert repo.get(created.id) == created


def test_accept_creates_durable_assertion_and_links_it(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = ObservationRepository(conn)
    observation = repo.create(_obs())

    updated, assertion = repo.accept(observation.id)

    assert updated.status == ObservationStatus.ACCEPTED
    assert updated.resulting_assertion_id == assertion.id
    assert updated.resolved_at is not None
    assert assertion.subject == "user:preferences"
    assert assertion.value == "Prefers concise technical explanations."

    [current] = AssertionRepository(conn).list_current(subject="user:preferences")
    assert current.id == assertion.id


def test_accept_allows_overriding_predicate_and_value(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = ObservationRepository(conn)
    observation = repo.create(_obs())

    _, assertion = repo.accept(observation.id, predicate="explanation_style", value="concise_technical")

    assert assertion.predicate == "explanation_style"
    assert assertion.value == "concise_technical"


def test_reject_leaves_no_durable_assertion(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = ObservationRepository(conn)
    observation = repo.create(_obs())

    updated = repo.reject(observation.id)

    assert updated.status == ObservationStatus.REJECTED
    assert updated.resulting_assertion_id is None
    assert AssertionRepository(conn).list_current() == []


def test_expire_leaves_no_durable_assertion(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = ObservationRepository(conn)
    observation = repo.create(_obs())

    updated = repo.expire(observation.id)
    assert updated.status == ObservationStatus.EXPIRED


def test_edit_only_works_while_proposed(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = ObservationRepository(conn)
    observation = repo.create(_obs())

    edited = repo.edit(observation.id, "Prefers terse, code-first answers.")
    assert edited.description == "Prefers terse, code-first answers."

    repo.accept(observation.id)
    with pytest.raises(ValueError):
        repo.edit(observation.id, "too late")


def test_cannot_accept_twice(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = ObservationRepository(conn)
    observation = repo.create(_obs())
    repo.accept(observation.id)

    with pytest.raises(ValueError):
        repo.accept(observation.id)


def test_list_filters_by_status(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = ObservationRepository(conn)
    a = repo.create(_obs(subject="a"))
    b = repo.create(_obs(subject="b"))
    repo.accept(a.id)

    assert [o.id for o in repo.list(ObservationStatus.PROPOSED)] == [b.id]
    assert [o.id for o in repo.list(ObservationStatus.ACCEPTED)] == [a.id]
