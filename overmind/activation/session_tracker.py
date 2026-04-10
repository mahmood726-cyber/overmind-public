from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from overmind.storage.db import StateDatabase
from overmind.storage.models import MemoryRecord, utc_now


class SessionTracker:
    """Tracks active CLI agent sessions across all terminal windows via shared SQLite."""

    def __init__(self, db: StateDatabase) -> None:
        self.db = db
        self._ensure_sessions_table()

    def _ensure_sessions_table(self) -> None:
        self.db.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS active_sessions (
                session_id TEXT PRIMARY KEY,
                runner_type TEXT NOT NULL,
                project_path TEXT,
                pid INTEGER,
                started_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                status TEXT DEFAULT 'active'
            )
            """
        )
        self.db.connection.commit()

    def register(self, runner_type: str, project_path: str | None = None) -> str:
        """Register a new CLI session. Returns session_id."""
        session_id = f"sess_{uuid.uuid4().hex[:8]}"
        now = utc_now()
        pid = os.getpid()
        self.db.connection.execute(
            """
            INSERT INTO active_sessions (session_id, runner_type, project_path, pid, started_at, last_seen_at, status)
            VALUES (?, ?, ?, ?, ?, ?, 'active')
            """,
            (session_id, runner_type, project_path, pid, now, now),
        )
        self.db.connection.commit()
        return session_id

    def heartbeat(self, session_id: str) -> None:
        """Update last_seen_at for a session."""
        self.db.connection.execute(
            "UPDATE active_sessions SET last_seen_at = ? WHERE session_id = ?",
            (utc_now(), session_id),
        )
        self.db.connection.commit()

    def close_session(self, session_id: str) -> None:
        """Mark session as closed."""
        self.db.connection.execute(
            "UPDATE active_sessions SET status = 'closed', last_seen_at = ? WHERE session_id = ?",
            (utc_now(), session_id),
        )
        self.db.connection.commit()

    def active_sessions(self) -> list[dict[str, object]]:
        """List all active sessions."""
        rows = self.db.connection.execute(
            "SELECT * FROM active_sessions WHERE status = 'active' ORDER BY started_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    def active_project_paths(self) -> set[str]:
        """Get paths of projects with active sessions."""
        rows = self.db.connection.execute(
            "SELECT DISTINCT project_path FROM active_sessions WHERE status = 'active' AND project_path IS NOT NULL"
        ).fetchall()
        return {row["project_path"] for row in rows}

    def cleanup_stale(self, max_age_minutes: int = 60) -> int:
        """Close sessions that haven't had a heartbeat in max_age_minutes."""
        import psutil
        rows = self.db.connection.execute(
            "SELECT session_id, pid FROM active_sessions WHERE status = 'active'"
        ).fetchall()
        closed = 0
        for row in rows:
            pid = row["pid"]
            if pid and not psutil.pid_exists(pid):
                self.close_session(row["session_id"])
                closed += 1
        return closed
