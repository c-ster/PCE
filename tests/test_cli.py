import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

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


@pytest.mark.parametrize(
    "args",
    [
        ["index"],
        ["search", "anything"],
        ["memory", "list"],
        ["context", "inbox"],
        ["context", "review"],
        ["context", "stats"],
        ["policy", "explain"],
        ["serve-mcp"],
    ],
)
def test_unimplemented_commands_fail_honestly(runner: CliRunner, capsule_env: dict, args: list):
    result = runner.invoke(cli, args, env=capsule_env)
    assert result.exit_code == 1
    assert "not implemented yet" in result.output
