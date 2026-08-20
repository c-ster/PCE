"""Simple, inspectable chunking: split on paragraph breaks, pack greedily up
to max_chars, and hard-split any single paragraph that's too long on its own.
No sentence/token-boundary modeling — good enough for short personal
documents, easy to reason about. See docs/ARCHITECTURE.md.
"""

from __future__ import annotations


def chunk_text(text: str, max_chars: int = 800) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    def flush() -> None:
        if current:
            chunks.append("\n\n".join(current))

    for paragraph in paragraphs:
        pieces = [paragraph] if len(paragraph) <= max_chars else _hard_split(paragraph, max_chars)
        for piece in pieces:
            if current and current_len + len(piece) + 2 > max_chars:
                flush()
                current = []
                current_len = 0
            current.append(piece)
            current_len += len(piece) + 2

    flush()
    return chunks


def _hard_split(text: str, max_chars: int) -> list[str]:
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]
