"""Git repository adapter.

Operates on a local working tree that is already a git repository (cloning a
remote is a separate, network-touching concern left to the CLI layer — see
docs/ADAPTER_SDK.md). Reads committed content at HEAD via `git show` rather
than the working tree, so content_hash and source_version reflect an actual
commit, not uncommitted edits. Only files git already tracks are considered,
so .gitignore is respected for free.
"""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from pce.adapters.base import SourceAdapter
from pce.adapters.errors import SourceRootViolation
from pce.adapters.text_utils import SUPPORTED_EXTENSIONS, extract_title, source_type_for_suffix
from pce.context.models import SourceDocument

PARSER_VERSION = "git_text_v1"
CHUNKING_VERSION = "none_v1"

_FIELD_SEP = "\x1f"


class GitAdapter(SourceAdapter):
    source_system = "git"

    # No adapter-initiated network activity: this adapter reads an already
    # cloned local working tree. See docs/PRIVACY.md.
    network_required = False

    def __init__(self, repo_path: Path):
        self._repo_path = repo_path.resolve()
        if not (self._repo_path / ".git").exists():
            raise ValueError(f"{self._repo_path} is not a git repository (no .git directory)")

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self._repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def _relative_ref(self, ref: str | Path) -> str:
        resolved = Path(ref).resolve()
        if resolved != self._repo_path and self._repo_path not in resolved.parents:
            raise SourceRootViolation(
                f"{resolved} is not inside git repo root: {self._repo_path}"
            )
        return str(resolved.relative_to(self._repo_path))

    def discover(self) -> list[str]:
        tracked = self._git("ls-files").splitlines()
        refs = [
            str(self._repo_path / rel)
            for rel in tracked
            if Path(rel).suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        return sorted(refs)

    def enumerate_documents(self) -> Iterator[str]:
        yield from self.discover()

    def read_document(self, ref: str) -> str:
        rel = self._relative_ref(ref)
        return self._git("show", f"HEAD:{rel}")

    def get_metadata(self, ref: str) -> dict:
        rel = self._relative_ref(ref)
        content = self.read_document(ref)

        commit_hash = self._git("rev-parse", "HEAD")

        last_log = self._git("log", "-1", f"--format=%aI{_FIELD_SEP}%an", "--", rel)
        updated_at_iso, _, author = last_log.partition(_FIELD_SEP)

        first_log_lines = self._git("log", "--follow", "--format=%aI", "--", rel).splitlines()
        created_at_iso = first_log_lines[-1] if first_log_lines else updated_at_iso

        return {
            "title": extract_title(content, fallback=Path(rel).stem),
            "author": author or None,
            "created_at_source": datetime.fromisoformat(created_at_iso) if created_at_iso else None,
            "updated_at_source": datetime.fromisoformat(updated_at_iso) if updated_at_iso else None,
            "source_type": source_type_for_suffix(Path(rel).suffix),
            "source_version": commit_hash,
        }

    def sync(self) -> Iterator[SourceDocument]:
        for ref in self.enumerate_documents():
            content = self.read_document(ref)
            metadata = self.get_metadata(ref)
            yield SourceDocument(
                source_type=metadata["source_type"],
                source_system=self.source_system,
                source_ref=ref,
                source_version=metadata["source_version"],
                title=metadata["title"],
                author=metadata["author"],
                created_at_source=metadata["created_at_source"],
                updated_at_source=metadata["updated_at_source"],
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                parser_version=PARSER_VERSION,
                chunking_version=CHUNKING_VERSION,
            )
