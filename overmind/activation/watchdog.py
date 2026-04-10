"""Lightweight watchdog: `overmind watch`

Monitors active agent sessions by pid. No AI, no API calls — just psutil checks.
Cleans up stale sessions and logs status.
"""
from __future__ import annotations

import time
from pathlib import Path

from overmind.activation.session_tracker import SessionTracker
from overmind.storage.db import StateDatabase


def watch(db_path: Path, interval: int = 30, iterations: int | None = None) -> None:
    """Poll active sessions and clean up stale ones."""
    db = StateDatabase(db_path)
    tracker = SessionTracker(db)
    iteration = 0
    try:
        while iterations is None or iteration < iterations:
            cleaned = tracker.cleanup_stale()
            active = tracker.active_sessions()
            if active or cleaned:
                print(f"[OVERMIND WATCH] Active: {len(active)} sessions, Cleaned: {cleaned} stale")
                for session in active:
                    print(f"  - {session['runner_type']} pid={session['pid']} "
                          f"project={session.get('project_path', '?')}")
            iteration += 1
            if iterations is not None and iteration >= iterations:
                break
            time.sleep(interval)
    finally:
        db.close()
