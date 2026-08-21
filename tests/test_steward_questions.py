from pathlib import Path

import pytest

from pce.context.db import connect
from pce.steward.questions import ContextQuestion, QuestionRepository, QuestionStatus, QuestionType


def _question(**overrides) -> ContextQuestion:
    defaults = dict(
        question_type=QuestionType.ASSERTION_STALE,
        subject="project:a",
        description="something is stale",
        dedupe_key="stale:x",
    )
    defaults.update(overrides)
    return ContextQuestion(**defaults)


def test_create_if_new_inserts_once(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = QuestionRepository(conn)

    first = repo.create_if_new(_question())
    second = repo.create_if_new(_question())  # same dedupe_key, still open

    assert first is not None
    assert second is None
    assert len(repo.list()) == 1


def test_create_if_new_allows_recreation_after_resolution(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = QuestionRepository(conn)

    first = repo.create_if_new(_question())
    repo.dismiss(first.id)

    second = repo.create_if_new(_question())
    assert second is not None
    assert len(repo.list()) == 2


def test_answer_sets_status_and_note(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = QuestionRepository(conn)
    question = repo.create_if_new(_question())

    updated = repo.answer(question.id, "reconfirmed, still true")
    assert updated.status == QuestionStatus.ANSWERED
    assert updated.resolution_note == "reconfirmed, still true"
    assert updated.resolved_at is not None


def test_defer_is_not_terminal(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = QuestionRepository(conn)
    question = repo.create_if_new(_question())

    updated = repo.defer(question.id)
    assert updated.status == QuestionStatus.DEFERRED
    assert updated.resolved_at is None


def test_dismiss_sets_status(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = QuestionRepository(conn)
    question = repo.create_if_new(_question())

    updated = repo.dismiss(question.id)
    assert updated.status == QuestionStatus.DISMISSED


def test_list_filters_by_status(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = QuestionRepository(conn)
    a = repo.create_if_new(_question(dedupe_key="a"))
    b = repo.create_if_new(_question(dedupe_key="b"))
    repo.dismiss(b.id)

    assert [q.id for q in repo.list(statuses=(QuestionStatus.OPEN,))] == [a.id]


def test_stats_counts_by_status(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = QuestionRepository(conn)
    repo.create_if_new(_question(dedupe_key="a"))
    b = repo.create_if_new(_question(dedupe_key="b"))
    repo.dismiss(b.id)

    stats = repo.stats()
    assert stats["open"] == 1
    assert stats["dismissed"] == 1
    assert stats["answered"] == 0


def test_answer_unknown_id_raises(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = QuestionRepository(conn)
    with pytest.raises(ValueError):
        repo.answer("does-not-exist", "note")
