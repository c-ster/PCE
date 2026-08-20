"""Model provider interfaces (PRD section 34).

PCE never assumes a specific LLM or embedding model — retrieval and future
generation code depend only on these interfaces. Initial focus is local
OpenAI-compatible endpoints (Jan, Open WebUI, LM Studio, llama.cpp, Ollama)
plus simple provider adapters where a service doesn't speak that protocol.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, messages: list[dict[str, Any]]) -> str: ...


class EmbeddingProvider(ABC):
    """`name` and `dimensions` are recorded on every chunk so index
    generations are never silently mixed (section 35)."""

    name: str
    dimensions: int

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class Reranker(ABC):
    @abstractmethod
    def rank(self, query: str, candidates: list[str]) -> list[int]:
        """Return candidate indices ordered best-first."""
