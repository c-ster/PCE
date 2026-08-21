import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

import pce.cli.main as cli_main
from pce.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def capsule_env(tmp_path: Path) -> dict:
    return {"PCE_HOME": str(tmp_path / "capsule")}


def _run(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(repo, "init", "-q")
    _run(repo, "config", "user.email", "fixture@example.com")
    _run(repo, "config", "user.name", "Fixture Author")
    (repo / "note.md").write_text("# Repo Note\n\nHello.\n")
    _run(repo, "add", "note.md")
    _run(repo, "commit", "-q", "-m", "initial commit")
    return repo


def test_init_creates_capsule_layout(runner: CliRunner, capsule_env: dict, tmp_path: Path):
    result = runner.invoke(cli, ["init"], env=capsule_env)
    assert result.exit_code == 0, result.output

    home = tmp_path / "capsule"
    for subdir in ["config", "database", "indexes", "sources", "cache", "memory", "logs"]:
        assert (home / subdir).is_dir()
    assert (home / "config" / "config.json").exists()


def test_init_is_idempotent(runner: CliRunner, capsule_env: dict):
    first = runner.invoke(cli, ["init"], env=capsule_env)
    second = runner.invoke(cli, ["init"], env=capsule_env)
    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "already initialized" in second.output


def test_init_with_compartments_registers_them(runner: CliRunner, capsule_env: dict):
    runner.invoke(cli, ["init", "--compartment", "WRITING", "--compartment", "LEGAL"], env=capsule_env)
    result = runner.invoke(cli, ["compartment", "list"], env=capsule_env)
    assert "WRITING" in result.output
    assert "LEGAL" in result.output


def test_commands_require_init_first(runner: CliRunner, capsule_env: dict):
    result = runner.invoke(cli, ["source", "list"], env=capsule_env)
    assert result.exit_code != 0
    assert "pce init" in result.output


def test_doctor_reports_uninitialized_capsule(runner: CliRunner, capsule_env: dict):
    result = runner.invoke(cli, ["doctor"], env=capsule_env)
    assert result.exit_code == 1
    assert "run `pce init`" in result.output


def test_doctor_passes_after_init(runner: CliRunner, capsule_env: dict):
    runner.invoke(cli, ["init"], env=capsule_env)
    result = runner.invoke(cli, ["doctor"], env=capsule_env)
    assert result.exit_code == 0, result.output


def test_source_add_list_inspect_remove(runner: CliRunner, capsule_env: dict, tmp_path: Path):
    runner.invoke(cli, ["init"], env=capsule_env)

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nBody.\n")
    (docs_dir / "b.md").write_text("# B\n\nBody.\n")

    add_result = runner.invoke(cli, ["source", "add", str(docs_dir)], env=capsule_env)
    assert add_result.exit_code == 0, add_result.output
    assert "Ingested 2 document(s)" in add_result.output

    list_result = runner.invoke(cli, ["source", "list"], env=capsule_env)
    assert str(docs_dir.resolve()) in list_result.output
    source_id = list_result.output.split()[0]

    inspect_result = runner.invoke(cli, ["source", "inspect", source_id], env=capsule_env)
    assert "2 document(s)" in inspect_result.output
    assert "A" in inspect_result.output and "B" in inspect_result.output

    remove_result = runner.invoke(cli, ["source", "remove", source_id], env=capsule_env)
    assert "Removed source" in remove_result.output

    empty_list = runner.invoke(cli, ["source", "list"], env=capsule_env)
    assert "No local file sources registered" in empty_list.output


def test_source_inspect_unknown_id_errors(runner: CliRunner, capsule_env: dict):
    runner.invoke(cli, ["init"], env=capsule_env)
    result = runner.invoke(cli, ["source", "inspect", "does-not-exist"], env=capsule_env)
    assert result.exit_code != 0


def test_repo_add_and_list(runner: CliRunner, capsule_env: dict, git_repo: Path):
    runner.invoke(cli, ["init"], env=capsule_env)

    add_result = runner.invoke(cli, ["repo", "add", str(git_repo)], env=capsule_env)
    assert add_result.exit_code == 0, add_result.output
    assert "Ingested 1 document(s)" in add_result.output

    list_result = runner.invoke(cli, ["repo", "list"], env=capsule_env)
    assert str(git_repo.resolve()) in list_result.output


def test_sync_resyncs_all_registered_sources(runner: CliRunner, capsule_env: dict, tmp_path: Path, git_repo: Path):
    runner.invoke(cli, ["init"], env=capsule_env)

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nBody.\n")

    runner.invoke(cli, ["source", "add", str(docs_dir)], env=capsule_env)
    runner.invoke(cli, ["repo", "add", str(git_repo)], env=capsule_env)

    sync_result = runner.invoke(cli, ["sync"], env=capsule_env)
    assert sync_result.exit_code == 0, sync_result.output
    assert "local_file" in sync_result.output
    assert "git" in sync_result.output


def test_compartment_add_and_list(runner: CliRunner, capsule_env: dict):
    runner.invoke(cli, ["init"], env=capsule_env)
    runner.invoke(cli, ["compartment", "add", "PERSONAL"], env=capsule_env)
    result = runner.invoke(cli, ["compartment", "list"], env=capsule_env)
    assert "PERSONAL" in result.output


def test_search_without_index_errors(runner: CliRunner, capsule_env: dict):
    runner.invoke(cli, ["init"], env=capsule_env)
    result = runner.invoke(cli, ["search", "anything"], env=capsule_env)
    assert result.exit_code != 0
    assert "pce index" in result.output


def test_index_and_search_end_to_end(runner: CliRunner, capsule_env: dict, tmp_path: Path):
    runner.invoke(cli, ["init"], env=capsule_env)

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "pricing.md").write_text(
        "# Nightingale Pricing\n\nThe approved price for the Nightingale project is five thousand dollars.\n"
    )
    (docs_dir / "unrelated.md").write_text("# Recipe\n\nHow to bake sourdough bread at home.\n")

    runner.invoke(cli, ["source", "add", str(docs_dir)], env=capsule_env)

    index_result = runner.invoke(cli, ["index"], env=capsule_env)
    assert index_result.exit_code == 0, index_result.output
    assert "Indexed 2 document(s)" in index_result.output

    # Re-indexing with unchanged content should skip both documents.
    reindex_result = runner.invoke(cli, ["index"], env=capsule_env)
    assert "Skipped 2 document(s)" in reindex_result.output

    # Unclassified sources are excluded by default (fail closed).
    default_scope_result = runner.invoke(cli, ["search", "Nightingale pricing"], env=capsule_env)
    assert default_scope_result.exit_code == 0, default_scope_result.output
    assert "No matches" in default_scope_result.output

    search_result = runner.invoke(
        cli, ["search", "Nightingale pricing", "--include-unclassified"], env=capsule_env
    )
    assert search_result.exit_code == 0, search_result.output
    assert "Nightingale Pricing" in search_result.output
    assert "Detected intent:" in search_result.output


def _get_document_id(runner: CliRunner, capsule_env: dict, source_id: str) -> str:
    inspect_result = runner.invoke(cli, ["source", "inspect", source_id], env=capsule_env)
    for line in inspect_result.output.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            return stripped.split()[1]
    raise AssertionError(f"no document line found in: {inspect_result.output}")


def test_classify_sets_sensitivity_and_compartment(runner: CliRunner, capsule_env: dict, tmp_path: Path):
    runner.invoke(cli, ["init"], env=capsule_env)
    runner.invoke(cli, ["compartment", "add", "LEGAL"], env=capsule_env)

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nBody.\n")
    add_result = runner.invoke(cli, ["source", "add", str(docs_dir)], env=capsule_env)
    source_id = add_result.output.splitlines()[0].split()[2]
    document_id = _get_document_id(runner, capsule_env, source_id)

    classify_result = runner.invoke(
        cli,
        ["classify", document_id, "--sensitivity", "public", "--compartment", "LEGAL"],
        env=capsule_env,
    )
    assert classify_result.exit_code == 0, classify_result.output
    assert "sensitivity=public" in classify_result.output
    assert "LEGAL" in classify_result.output


def test_classify_sets_epistemic_role(runner: CliRunner, capsule_env: dict, tmp_path: Path):
    runner.invoke(cli, ["init"], env=capsule_env)

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nBody.\n")
    add_result = runner.invoke(cli, ["source", "add", str(docs_dir)], env=capsule_env)
    source_id = add_result.output.splitlines()[0].split()[2]
    document_id = _get_document_id(runner, capsule_env, source_id)

    result = runner.invoke(cli, ["classify", document_id, "--epistemic-role", "fiction"], env=capsule_env)
    assert result.exit_code == 0, result.output
    assert "epistemic_role=fiction" in result.output

    inspect_result = runner.invoke(cli, ["source", "inspect", source_id], env=capsule_env)
    assert "fiction" in inspect_result.output


def test_classify_rejects_unregistered_compartment(runner: CliRunner, capsule_env: dict, tmp_path: Path):
    runner.invoke(cli, ["init"], env=capsule_env)

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nBody.\n")
    add_result = runner.invoke(cli, ["source", "add", str(docs_dir)], env=capsule_env)
    source_id = add_result.output.splitlines()[0].split()[2]
    document_id = _get_document_id(runner, capsule_env, source_id)

    result = runner.invoke(cli, ["classify", document_id, "--compartment", "NEVER_DEFINED"], env=capsule_env)
    assert result.exit_code != 0
    assert "pce compartment add" in result.output


def test_classify_with_no_options_errors(runner: CliRunner, capsule_env: dict, tmp_path: Path):
    runner.invoke(cli, ["init"], env=capsule_env)
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nBody.\n")
    add_result = runner.invoke(cli, ["source", "add", str(docs_dir)], env=capsule_env)
    source_id = add_result.output.splitlines()[0].split()[2]
    document_id = _get_document_id(runner, capsule_env, source_id)

    result = runner.invoke(cli, ["classify", document_id], env=capsule_env)
    assert result.exit_code != 0


def test_policy_explain_denies_unclassified_document_by_default(
    runner: CliRunner, capsule_env: dict, tmp_path: Path
):
    runner.invoke(cli, ["init"], env=capsule_env)
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nBody.\n")
    add_result = runner.invoke(cli, ["source", "add", str(docs_dir)], env=capsule_env)
    source_id = add_result.output.splitlines()[0].split()[2]
    document_id = _get_document_id(runner, capsule_env, source_id)

    result = runner.invoke(cli, ["policy", "explain", document_id], env=capsule_env)
    assert result.exit_code == 1
    assert "DENIED" in result.output
    assert "UNKNOWN" in result.output


def test_policy_explain_allows_after_classification(runner: CliRunner, capsule_env: dict, tmp_path: Path):
    runner.invoke(cli, ["init"], env=capsule_env)
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nBody.\n")
    add_result = runner.invoke(cli, ["source", "add", str(docs_dir)], env=capsule_env)
    source_id = add_result.output.splitlines()[0].split()[2]
    document_id = _get_document_id(runner, capsule_env, source_id)

    runner.invoke(cli, ["classify", document_id, "--sensitivity", "public"], env=capsule_env)
    result = runner.invoke(cli, ["policy", "explain", document_id], env=capsule_env)
    assert result.exit_code == 0
    assert "ALLOWED" in result.output


def test_serve_mcp_builds_fixed_scope_and_runs_server(runner: CliRunner, capsule_env: dict, monkeypatch):
    runner.invoke(cli, ["init"], env=capsule_env)

    fake_server = MagicMock()
    fake_build_server = MagicMock(return_value=fake_server)
    monkeypatch.setattr(cli_main, "build_mcp_server", fake_build_server)

    result = runner.invoke(
        cli, ["serve-mcp", "--compartment", "PERSONAL", "--include-unclassified"], env=capsule_env
    )

    assert result.exit_code == 0, result.output
    fake_server.run.assert_called_once()

    _, _, access_context = fake_build_server.call_args[0]
    assert access_context.allowed_compartments == frozenset({"PERSONAL"})
    assert access_context.allow_unclassified is True


def test_serve_mcp_defaults_to_unrestricted_compartments(runner: CliRunner, capsule_env: dict, monkeypatch):
    runner.invoke(cli, ["init"], env=capsule_env)

    fake_server = MagicMock()
    fake_build_server = MagicMock(return_value=fake_server)
    monkeypatch.setattr(cli_main, "build_mcp_server", fake_build_server)

    result = runner.invoke(cli, ["serve-mcp"], env=capsule_env)

    assert result.exit_code == 0, result.output
    _, _, access_context = fake_build_server.call_args[0]
    assert access_context.allowed_compartments is None
    assert access_context.allow_unclassified is False


def _first_line_id(output: str) -> str:
    return output.splitlines()[0].split()[1]


def test_assertion_add_list_history_show(runner: CliRunner, capsule_env: dict):
    runner.invoke(cli, ["init"], env=capsule_env)

    add_result = runner.invoke(
        cli,
        ["assertion", "add", "--subject", "project:nightingale", "--predicate", "status", "--value", "proposed"],
        env=capsule_env,
    )
    assert add_result.exit_code == 0, add_result.output
    january_id = _first_line_id(add_result.output)

    supersede_result = runner.invoke(
        cli,
        [
            "assertion",
            "add",
            "--subject",
            "project:nightingale",
            "--predicate",
            "status",
            "--value",
            "approved",
            "--status",
            "approved",
            "--supersedes",
            january_id,
        ],
        env=capsule_env,
    )
    assert supersede_result.exit_code == 0, supersede_result.output
    assert "superseding" in supersede_result.output

    list_result = runner.invoke(cli, ["assertion", "list"], env=capsule_env)
    assert "approved" in list_result.output
    assert january_id not in list_result.output  # superseded, not current

    history_result = runner.invoke(
        cli, ["assertion", "history", "project:nightingale", "status"], env=capsule_env
    )
    assert "proposed" in history_result.output
    assert "approved" in history_result.output

    show_result = runner.invoke(cli, ["assertion", "show", january_id], env=capsule_env)
    assert "superseded" in show_result.output
    assert "superseded_by:" in show_result.output


def test_assertion_add_with_unknown_source_document_errors(runner: CliRunner, capsule_env: dict):
    runner.invoke(cli, ["init"], env=capsule_env)
    result = runner.invoke(
        cli,
        [
            "assertion",
            "add",
            "--subject",
            "a",
            "--predicate",
            "b",
            "--value",
            "c",
            "--source",
            "does-not-exist",
        ],
        env=capsule_env,
    )
    assert result.exit_code != 0


def test_assertion_confirm_approve_reject(runner: CliRunner, capsule_env: dict):
    runner.invoke(cli, ["init"], env=capsule_env)
    add_result = runner.invoke(
        cli, ["assertion", "add", "--subject", "a", "--predicate", "b", "--value", "c"], env=capsule_env
    )
    assertion_id = _first_line_id(add_result.output)

    confirm_result = runner.invoke(cli, ["assertion", "confirm", assertion_id], env=capsule_env)
    assert confirm_result.exit_code == 0
    assert "Confirmed" in confirm_result.output

    approve_result = runner.invoke(cli, ["assertion", "approve", assertion_id], env=capsule_env)
    assert approve_result.exit_code == 0
    assert "Approved" in approve_result.output

    reject_result = runner.invoke(cli, ["assertion", "reject", assertion_id], env=capsule_env)
    assert reject_result.exit_code == 0
    assert "Rejected" in reject_result.output


def test_memory_propose_list_accept(runner: CliRunner, capsule_env: dict):
    runner.invoke(cli, ["init"], env=capsule_env)

    propose_result = runner.invoke(
        cli,
        ["memory", "propose", "--subject", "user:preferences", "--description", "Likes concise answers."],
        env=capsule_env,
    )
    assert propose_result.exit_code == 0, propose_result.output
    observation_id = _first_line_id(propose_result.output)

    list_result = runner.invoke(cli, ["memory", "list"], env=capsule_env)
    assert "Likes concise answers." in list_result.output
    assert "proposed" in list_result.output

    accept_result = runner.invoke(cli, ["memory", "accept", observation_id], env=capsule_env)
    assert accept_result.exit_code == 0, accept_result.output
    assert "Accepted" in accept_result.output

    current = runner.invoke(cli, ["assertion", "list"], env=capsule_env)
    assert "Likes concise answers." in current.output


def test_memory_reject_leaves_no_assertion(runner: CliRunner, capsule_env: dict):
    runner.invoke(cli, ["init"], env=capsule_env)
    propose_result = runner.invoke(
        cli, ["memory", "propose", "--subject", "a", "--description", "some pattern"], env=capsule_env
    )
    observation_id = _first_line_id(propose_result.output)

    reject_result = runner.invoke(cli, ["memory", "reject", observation_id], env=capsule_env)
    assert reject_result.exit_code == 0
    assert "Rejected" in reject_result.output

    current = runner.invoke(cli, ["assertion", "list"], env=capsule_env)
    assert "No assertions recorded" in current.output


def test_memory_edit_before_accepting(runner: CliRunner, capsule_env: dict):
    runner.invoke(cli, ["init"], env=capsule_env)
    propose_result = runner.invoke(
        cli, ["memory", "propose", "--subject", "a", "--description", "rough draft"], env=capsule_env
    )
    observation_id = _first_line_id(propose_result.output)

    edit_result = runner.invoke(cli, ["memory", "edit", observation_id, "polished version"], env=capsule_env)
    assert edit_result.exit_code == 0
    assert "polished version" in edit_result.output

    list_result = runner.invoke(cli, ["memory", "list"], env=capsule_env)
    assert "polished version" in list_result.output
    assert "rough draft" not in list_result.output


def test_memory_accept_twice_errors(runner: CliRunner, capsule_env: dict):
    runner.invoke(cli, ["init"], env=capsule_env)
    propose_result = runner.invoke(
        cli, ["memory", "propose", "--subject", "a", "--description", "x"], env=capsule_env
    )
    observation_id = _first_line_id(propose_result.output)
    runner.invoke(cli, ["memory", "accept", observation_id], env=capsule_env)

    second = runner.invoke(cli, ["memory", "accept", observation_id], env=capsule_env)
    assert second.exit_code != 0


def test_context_review_finds_conflict_and_inbox_shows_it(runner: CliRunner, capsule_env: dict):
    runner.invoke(cli, ["init"], env=capsule_env)
    runner.invoke(
        cli, ["assertion", "add", "--subject", "project:a", "--predicate", "price", "--value", "3000"], env=capsule_env
    )
    runner.invoke(
        cli, ["assertion", "add", "--subject", "project:a", "--predicate", "price", "--value", "5000"], env=capsule_env
    )

    review_result = runner.invoke(cli, ["context", "review"], env=capsule_env)
    assert review_result.exit_code == 0, review_result.output
    assert "new item" in review_result.output
    assert "Context Inbox · 1" in review_result.output

    inbox_result = runner.invoke(cli, ["context", "inbox"], env=capsule_env)
    assert "Context Inbox · 1" in inbox_result.output
    assert "5000" in inbox_result.output  # suggested answer names the more recent value


def test_context_inbox_empty_by_default(runner: CliRunner, capsule_env: dict):
    runner.invoke(cli, ["init"], env=capsule_env)
    result = runner.invoke(cli, ["context", "inbox"], env=capsule_env)
    assert "Context Inbox · 0" in result.output


def test_context_answer_with_reconfirm(runner: CliRunner, capsule_env: dict):
    runner.invoke(cli, ["init"], env=capsule_env)
    add_result = runner.invoke(
        cli, ["assertion", "add", "--subject", "project:a", "--predicate", "status", "--value", "approved"], env=capsule_env
    )
    assertion_id = _first_line_id(add_result.output)

    runner.invoke(cli, ["context", "review", "--staleness-days", "0"], env=capsule_env)
    inbox_result = runner.invoke(cli, ["context", "inbox"], env=capsule_env)
    question_id = inbox_result.output.splitlines()[-1].strip().split()[-1]

    answer_result = runner.invoke(
        cli, ["context", "answer", question_id, "--note", "still true", "--reconfirm"], env=capsule_env
    )
    assert answer_result.exit_code == 0, answer_result.output

    show_result = runner.invoke(cli, ["assertion", "show", assertion_id], env=capsule_env)
    assert "last_confirmed_at: None" not in show_result.output

    empty_inbox = runner.invoke(cli, ["context", "inbox"], env=capsule_env)
    assert "Context Inbox · 0" in empty_inbox.output


def test_context_defer_and_dismiss(runner: CliRunner, capsule_env: dict):
    runner.invoke(cli, ["init"], env=capsule_env)
    runner.invoke(
        cli, ["assertion", "add", "--subject", "project:a", "--predicate", "price", "--value", "3000"], env=capsule_env
    )
    runner.invoke(
        cli, ["assertion", "add", "--subject", "project:a", "--predicate", "price", "--value", "5000"], env=capsule_env
    )
    runner.invoke(cli, ["context", "review"], env=capsule_env)

    inbox_result = runner.invoke(cli, ["context", "inbox"], env=capsule_env)
    question_id = inbox_result.output.splitlines()[-1].strip().split()[-1]

    defer_result = runner.invoke(cli, ["context", "defer", question_id], env=capsule_env)
    assert defer_result.exit_code == 0

    assert "Context Inbox · 0" in runner.invoke(cli, ["context", "inbox"], env=capsule_env).output
    assert "Context Inbox · 1" in runner.invoke(
        cli, ["context", "inbox", "--include-deferred"], env=capsule_env
    ).output

    dismiss_result = runner.invoke(cli, ["context", "dismiss", question_id], env=capsule_env)
    assert dismiss_result.exit_code == 0
    assert "Context Inbox · 0" in runner.invoke(
        cli, ["context", "inbox", "--include-deferred"], env=capsule_env
    ).output


def test_context_stats_counts_by_status(runner: CliRunner, capsule_env: dict):
    runner.invoke(cli, ["init"], env=capsule_env)
    runner.invoke(
        cli, ["assertion", "add", "--subject", "project:a", "--predicate", "price", "--value", "3000"], env=capsule_env
    )
    runner.invoke(
        cli, ["assertion", "add", "--subject", "project:a", "--predicate", "price", "--value", "5000"], env=capsule_env
    )
    runner.invoke(cli, ["context", "review"], env=capsule_env)

    result = runner.invoke(cli, ["context", "stats"], env=capsule_env)
    assert result.exit_code == 0
    assert "open: 1" in result.output
