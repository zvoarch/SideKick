from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
from datetime import datetime, timedelta, timezone

APP_DATA_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
APP_DATA_DIR = APP_DATA_ROOT / "Desktop-Companion-App"
# Normal app data stays under Windows local app data; tests can override this with COMPANION_DB_PATH.
DEFAULT_DATABASE_PATH = APP_DATA_DIR / "companion.sqlite3"
DATABASE_PATH = Path(os.environ.get("COMPANION_DB_PATH", DEFAULT_DATABASE_PATH))
SCHEMA_VERSION = 2
ACTIVITY_RETENTION_DAYS = 365

SCHEMA = """
CREATE TABLE IF NOT EXISTS approved_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    path TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS approved_folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    path TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workspaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS one_active_workspace
ON workspaces (is_active) WHERE is_active = 1;

CREATE TABLE IF NOT EXISTS workspace_applications (
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    application_id INTEGER NOT NULL REFERENCES approved_applications(id) ON DELETE RESTRICT,
    PRIMARY KEY (workspace_id, application_id)
);

CREATE TABLE IF NOT EXISTS workspace_folders (
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    folder_id INTEGER NOT NULL REFERENCES approved_folders(id) ON DELETE RESTRICT,
    PRIMARY KEY (workspace_id, folder_id)
);

CREATE TABLE IF NOT EXISTS workspace_websites (
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    PRIMARY KEY (workspace_id, url)
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_type TEXT NOT NULL CHECK (
        activity_type IN ('application_opened', 'workspace_opened')
    ),
    subject TEXT NOT NULL CHECK (length(subject) BETWEEN 1 AND 200),
    occurred_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS activity_log_occurred_at
ON activity_log (occurred_at DESC);
"""


@contextmanager
def database_connection():
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    """Create the local database and initial tables once when the app starts."""
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with database_connection() as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema version {version} is newer than this app supports."
            )
        connection.executescript(SCHEMA)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.execute("UPDATE workspaces SET is_active = 0")
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=ACTIVITY_RETENTION_DAYS)
        ).isoformat(timespec="seconds")
        connection.execute("DELETE FROM activity_log WHERE occurred_at < ?", (cutoff,))



