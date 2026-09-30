"""Open a SQLite connection for each operation and close it afterward."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def default_db() -> Path:
    return Path(os.environ.get("TIMEREACT_DB", str(Path.cwd() / ".timereact" / "state.sqlite3")))


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS timers (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    start_wall REAL NOT NULL,
                    start_steady REAL NOT NULL,
                    clock_instance TEXT NOT NULL,
                    budget_seconds REAL,
                    deadline_wall REAL,
                    stopped_json TEXT
                );
                CREATE INDEX IF NOT EXISTS timers_by_session
                    ON timers(session_id, start_wall);
                CREATE TABLE IF NOT EXISTS observations (
                    session_id TEXT PRIMARY KEY,
                    wall REAL NOT NULL,
                    steady REAL NOT NULL,
                    clock_instance TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversation_events (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    turn_id TEXT,
                    event_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    observed_wall REAL NOT NULL,
                    timezone TEXT NOT NULL,
                    references_json TEXT NOT NULL,
                    UNIQUE(session_id, turn_id, event_name)
                );
                CREATE INDEX IF NOT EXISTS events_by_session
                    ON conversation_events(session_id, observed_wall);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()
