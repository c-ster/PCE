"""SQLite connection management and an explicit, file-based migration runner.

Deliberately not Alembic/SQLAlchemy: migrations are just numbered .sql files
applied in order and tracked in a schema_migrations table. Boring and
inspectable — see docs/ARCHITECTURE.md "Dependency Philosophy".
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection at db_path and apply any pending migrations."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn)
    return conn


def run_migrations(conn: sqlite3.Connection, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply any migration files in migrations_dir not yet recorded as applied.

    Returns the names of migrations applied during this call.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )

    applied = {row["name"] for row in conn.execute("SELECT name FROM schema_migrations")}
    pending = sorted(
        p for p in migrations_dir.glob("*.sql") if p.name not in applied
    )

    newly_applied = []
    for migration_path in pending:
        conn.executescript(migration_path.read_text())
        conn.execute(
            "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
            (migration_path.name, datetime.now(timezone.utc).isoformat()),
        )
        newly_applied.append(migration_path.name)

    conn.commit()
    return newly_applied
