"""Capsule location and layout (PRD section 39).

Defaults to ~/.pce/, overridable via the PCE_HOME environment variable
(mainly so tests, and anyone running multiple capsules, don't have to touch
the real ~/.pce/ on the machine).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

CAPSULE_SUBDIRS = ["config", "database", "indexes", "sources", "cache", "memory", "logs"]
CONFIG_FILENAME = "config.json"
DB_FILENAME = "pce.sqlite3"


class CapsuleNotInitialized(Exception):
    """Raised when a command needs an initialized capsule but none exists yet."""


def capsule_home() -> Path:
    override = os.environ.get("PCE_HOME")
    return Path(override).expanduser().resolve() if override else Path.home() / ".pce"


def config_path(home: Path) -> Path:
    return home / "config" / CONFIG_FILENAME


def db_path(home: Path) -> Path:
    return home / "database" / DB_FILENAME


def is_initialized(home: Path) -> bool:
    return config_path(home).exists()


def require_initialized(home: Path) -> None:
    if not is_initialized(home):
        raise CapsuleNotInitialized(f"No PCE capsule found at {home}. Run `pce init` first.")


def init_capsule(home: Path) -> dict:
    """Create the capsule directory layout and config file. Safe to call
    again on an already-initialized capsule (directories are idempotent;
    the config file is left untouched if it already exists)."""
    for subdir in CAPSULE_SUBDIRS:
        (home / subdir).mkdir(parents=True, exist_ok=True)

    if not is_initialized(home):
        config = {
            "home": str(home),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        config_path(home).write_text(json.dumps(config, indent=2))

    return load_config(home)


def load_config(home: Path) -> dict:
    return json.loads(config_path(home).read_text())
