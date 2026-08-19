"""Shared helpers for adapters that read Markdown/text content."""

from __future__ import annotations

SUPPORTED_EXTENSIONS = {".md": "markdown", ".markdown": "markdown", ".txt": "text"}


def source_type_for_suffix(suffix: str) -> str:
    return SUPPORTED_EXTENSIONS.get(suffix.lower(), "text")


def extract_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        return stripped.lstrip("#").strip() if stripped.startswith("#") else fallback
    return fallback
