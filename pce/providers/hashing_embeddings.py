"""A dependency-free, fully offline default EmbeddingProvider.

This is a placeholder, not a quality embedding model: it hashes tokens into
a fixed-size bag-of-words vector, so texts sharing vocabulary score as
similar and texts that don't, don't. It exists so retrieval works out of the
box with zero ML dependencies. Swap in a real local model (e.g. an
OpenAI-compatible /v1/embeddings endpoint served by Jan/Ollama/LM Studio) by
implementing pce.providers.base.EmbeddingProvider — see docs/MODEL_PROVIDERS.md.
"""

from __future__ import annotations

import hashlib
import math
import re

from pce.providers.base import EmbeddingProvider

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _stable_bucket(token: str, dimensions: int) -> int:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % dimensions


class HashingEmbeddingProvider(EmbeddingProvider):
    name = "hashing_v1"

    def __init__(self, dimensions: int = 256):
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _tokenize(text):
            vector[_stable_bucket(token, self.dimensions)] += 1.0

        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector
