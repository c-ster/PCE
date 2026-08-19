"""SourceAdapter interface. See docs/ADAPTER_SDK.md."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from pce.context.models import SourceDocument


class SourceAdapter(ABC):
    """Base interface every source adapter implements.

    `source_system` identifies this adapter's kind of source (e.g.
    "local_file", "git") and is stored on every SourceDocument it produces.
    """

    source_system: str

    @abstractmethod
    def discover(self) -> list[str]:
        """Return the source refs this adapter currently considers in scope."""

    @abstractmethod
    def enumerate_documents(self) -> Iterator[str]:
        """Yield a source ref for each document currently in scope."""

    @abstractmethod
    def read_document(self, ref: str) -> str:
        """Return the raw text content for a source ref."""

    @abstractmethod
    def get_metadata(self, ref: str) -> dict:
        """Return adapter-specific metadata (title, timestamps, ...) for a ref."""

    @abstractmethod
    def sync(self) -> Iterator[SourceDocument]:
        """Discover, read, and yield a SourceDocument for each document in scope."""
