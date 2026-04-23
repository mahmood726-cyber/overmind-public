"""Claude Code Stop hook — triggers memory extraction and dreaming on session end.

Called by Claude Code via settings.json hook when a session ends.
"""
from __future__ import annotations

import os


def main() -> None:
    project_path = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    try:
        from overmind.config import default_db_path
        from overmind.storage.db import StateDatabase
        from overmind.activation.session_tracker import SessionTracker
        from overmind.memory.dream_engine import DreamEngine

        db = StateDatabase(default_db_path())
        try:
            # Close any sessions for this process
            tracker = SessionTracker(db)
            for session in tracker.active_sessions():
                if session.get("pid") == os.getpid():
                    tracker.close_session(session["session_id"])

            # Check if dreaming is warranted
            active_count = len(db.list_memories(status="active", limit=10000))
            dream_engine = DreamEngine(db)
            checkpoint = db.latest_checkpoint("dream")
            ticks_estimate = 5  # approximate — triggers dream if enough memories
            if dream_engine.should_dream(ticks_estimate, active_count):
                dream_engine.dream()
        finally:
            db.close()
    except Exception:
        pass  # Never block Claude Code shutdown


if __name__ == "__main__":
    main()
