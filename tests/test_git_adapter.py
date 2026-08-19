import subprocess
from pathlib import Path

import pytest

from pce.adapters.errors import SourceRootViolation
from pce.adapters.git import GitAdapter


def _run(repo: Path, *args: str, env: dict | None = None) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env=env)


def _commit(repo: Path, message: str, iso_date: str) -> None:
    import os

    env = {**os.environ, "GIT_AUTHOR_DATE": iso_date, "GIT_COMMITTER_DATE": iso_date}
    _run(repo, "commit", "-q", "-m", message, env=env)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(repo, "init", "-q")
    _run(repo, "config", "user.email", "fixture@example.com")
    _run(repo, "config", "user.name", "Fixture Author")

    (repo / "README.md").write_text("# Repo Title\n\nFirst version.\n")
    (repo / "notes.txt").write_text("plain notes\n")
    (repo / ".gitignore").write_text("ignored.md\n")
    (repo / "ignored.md").write_text("# Should not appear\n")

    _run(repo, "add", "README.md", "notes.txt", ".gitignore")
    _commit(repo, "initial commit", "2026-01-01T09:00:00-08:00")

    (repo / "README.md").write_text("# Repo Title\n\nSecond version.\n")
    _run(repo, "add", "README.md")
    _commit(repo, "update readme", "2026-03-01T09:00:00-08:00")

    return repo


def test_rejects_non_git_directory(tmp_path: Path):
    with pytest.raises(ValueError):
        GitAdapter(repo_path=tmp_path)


def test_discover_only_returns_tracked_supported_files(git_repo: Path):
    adapter = GitAdapter(repo_path=git_repo)
    names = {Path(ref).name for ref in adapter.discover()}
    assert names == {"README.md", "notes.txt"}
    assert "ignored.md" not in names


def test_read_document_returns_head_content(git_repo: Path):
    adapter = GitAdapter(repo_path=git_repo)
    ref = str(git_repo / "README.md")
    assert "Second version." in adapter.read_document(ref)


def test_get_metadata_includes_commit_provenance(git_repo: Path):
    adapter = GitAdapter(repo_path=git_repo)
    metadata = adapter.get_metadata(str(git_repo / "README.md"))

    assert metadata["title"] == "Repo Title"
    assert metadata["author"] == "Fixture Author"
    assert metadata["source_version"]
    assert metadata["created_at_source"] < metadata["updated_at_source"]


def test_sync_yields_source_documents_with_commit_hash_as_source_version(git_repo: Path):
    adapter = GitAdapter(repo_path=git_repo)
    docs = list(adapter.sync())

    assert len(docs) == 2
    head_commit = adapter._git("rev-parse", "HEAD")
    assert all(doc.source_system == "git" for doc in docs)
    assert all(doc.source_version == head_commit for doc in docs)


def test_read_document_outside_repo_raises(git_repo: Path, tmp_path: Path):
    adapter = GitAdapter(repo_path=git_repo)
    outside = tmp_path / "outside.md"
    outside.write_text("nope")

    with pytest.raises(SourceRootViolation):
        adapter.read_document(str(outside))
