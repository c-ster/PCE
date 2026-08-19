"""Compartment registry (PRD section 28).

Just the data model for now: a persisted set of user-defined compartment
names. Enforcing compartment scope against it (section 29, "policy before
ranking") is future work that depends on retrieval existing.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


class CompartmentRegistry:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def add(self, name: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO compartments (name, created_at) VALUES (?, ?)",
            (name, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def list(self) -> list[str]:
        rows = self._conn.execute("SELECT name FROM compartments ORDER BY name").fetchall()
        return [row["name"] for row in rows]
