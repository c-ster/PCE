from datetime import datetime, timedelta, timezone
from pathlib import Path

from pce.context.assertions import AssertionRepository, ContextAssertion
from pce.context.db import connect
from pce.memory.observations import ContextObservation, ObservationRepository
from pce.steward.questions import QuestionRepository, QuestionStatus, QuestionType
from pce.steward.scan import run_steward_scan, scan_conflicts, scan_staleness, scan_unreviewed_observations

NOW = datetime.now(timezone.utc)


def test_scan_conflicts_detects_unresolved_duplicate_subject_predicate(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = AssertionRepository(conn)
    repo.create(
        ContextAssertion(
            subject="project:a", predicate="price", value="3000", valid_from=NOW - timedelta(days=10)
        )
    )
    repo.create(
        ContextAssertion(subject="project:a", predicate="price", value="5000", valid_from=NOW - timedelta(days=1))
    )

    questions = scan_conflicts(conn)
    assert len(questions) == 1
    q = questions[0]
    assert q.question_type == QuestionType.ASSERTION_CONFLICT
    assert "5000" in q.suggested_answer  # more recent one suggested
    assert len(q.related_assertion_ids) == 2


def test_scan_conflicts_ignores_properly_superseded_assertions(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = AssertionRepository(conn)
    old = repo.create(ContextAssertion(subject="project:a", predicate="price", value="3000"))
    repo.supersede(old.id, ContextAssertion(subject="project:a", predicate="price", value="5000"))

    assert scan_conflicts(conn) == []


def test_scan_conflicts_is_idempotent_across_reruns(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = AssertionRepository(conn)
    repo.create(ContextAssertion(subject="project:a", predicate="price", value="3000"))
    repo.create(ContextAssertion(subject="project:a", predicate="price", value="5000"))

    first = scan_conflicts(conn)
    second = scan_conflicts(conn)
    assert len(first) == 1
    assert len(second) == 0  # already an open question, not duplicated
    assert len(QuestionRepository(conn).list()) == 1


def test_scan_staleness_flags_old_unconfirmed_assertion(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    AssertionRepository(conn).create(
        ContextAssertion(subject="project:a", predicate="status", value="approved", valid_from=NOW - timedelta(days=200))
    )

    questions = scan_staleness(conn, max_age_days=90)
    assert len(questions) == 1
    assert questions[0].question_type == QuestionType.ASSERTION_STALE


def test_scan_staleness_skips_recently_confirmed_assertion(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    repo = AssertionRepository(conn)
    created = repo.create(
        ContextAssertion(subject="project:a", predicate="status", value="approved", valid_from=NOW - timedelta(days=200))
    )
    repo.confirm(created.id)  # confirmed just now

    assert scan_staleness(conn, max_age_days=90) == []


def test_scan_staleness_skips_recent_assertions(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    AssertionRepository(conn).create(
        ContextAssertion(subject="project:a", predicate="status", value="approved", valid_from=NOW - timedelta(days=5))
    )
    assert scan_staleness(conn, max_age_days=90) == []


def test_scan_unreviewed_observations_finds_proposed_ones(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    obs_repo = ObservationRepository(conn)
    proposed = obs_repo.create(ContextObservation(subject="user:preferences", description="Likes brevity."))
    accepted = obs_repo.create(ContextObservation(subject="user:preferences", description="Likes structure."))
    obs_repo.accept(accepted.id)

    questions = scan_unreviewed_observations(conn)
    assert len(questions) == 1
    assert questions[0].related_observation_id == proposed.id


def test_run_steward_scan_combines_all_three(tmp_path: Path):
    conn = connect(tmp_path / "pce.sqlite3")
    AssertionRepository(conn).create(ContextAssertion(subject="project:a", predicate="price", value="3000"))
    AssertionRepository(conn).create(ContextAssertion(subject="project:a", predicate="price", value="5000"))
    AssertionRepository(conn).create(
        ContextAssertion(subject="project:b", predicate="status", value="approved", valid_from=NOW - timedelta(days=200))
    )
    ObservationRepository(conn).create(ContextObservation(subject="user:preferences", description="Likes brevity."))

    questions = run_steward_scan(conn)
    types = {q.question_type for q in questions}
    assert types == {QuestionType.ASSERTION_CONFLICT, QuestionType.ASSERTION_STALE, QuestionType.OBSERVATION_REVIEW}
    assert len(QuestionRepository(conn).list(statuses=(QuestionStatus.OPEN,))) == 3
