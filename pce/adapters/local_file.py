"""Local Markdown/text file adapter.

Reads only from explicitly approved root directories — see
docs/PRIVACY.md "Local file safety". Any path outside those roots raises
SourceRootViolation rather than being silently read.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from pce.adapters.base import SourceAdapter
from pce.adapters.errors import SourceRootViolation
from pce.adapters.text_utils import SUPPORTED_EXTENSIONS, extract_title, source_type_for_suffix
from pce.context.models import SourceDocument

PARSER_VERSION = "local_file_text_v1"
CHUNKING_VERSION = "none_v1"


class LocalFileAdapter(SourceAdapter):
    source_system = "local_file"

    def __init__(self, approved_roots: list[Path]):
        if not approved_roots:
            raise ValueError("LocalFileAdapter requires at least one approved root")
        self._approved_roots = [root.resolve() for root in approved_roots]

    def _resolve_within_roots(self, ref: str | Path) -> Path:
        resolved = Path(ref).resolve()
        for root in self._approved_roots:
            if resolved == root or root in resolved.parents:
                return resolved
        raise SourceRootViolation(
            f"{resolved} is not inside an approved source root: {self._approved_roots}"
        )

    def discover(self) -> list[str]:
        refs = []
        for root in self._approved_roots:
            for ext in SUPPORTED_EXTENSIONS:
                refs.extend(str(p) for p in root.rglob(f"*{ext}") if p.is_file())
        return sorted(refs)

    def enumerate_documents(self) -> Iterator[str]:
        yield from self.discover()

    def read_document(self, ref: str) -> str:
        path = self._resolve_within_roots(ref)
        return path.read_text(encoding="utf-8")

    def get_metadata(self, ref: str) -> dict:
        path = self._resolve_within_roots(ref)
        content = path.read_text(encoding="utf-8")
        stat = path.stat()
        return {
            "title": extract_title(content, fallback=path.stem),
            "created_at_source": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc),
            "updated_at_source": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            "source_type": source_type_for_suffix(path.suffix),
        }

    def sync(self) -> Iterator[SourceDocument]:
        for ref in self.enumerate_documents():
            content = self.read_document(ref)
            metadata = self.get_metadata(ref)
            yield SourceDocument(
                source_type=metadata["source_type"],
                source_system=self.source_system,
                source_ref=ref,
                title=metadata["title"],
                created_at_source=metadata["created_at_source"],
                updated_at_source=metadata["updated_at_source"],
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                parser_version=PARSER_VERSION,
                chunking_version=CHUNKING_VERSION,
            )
