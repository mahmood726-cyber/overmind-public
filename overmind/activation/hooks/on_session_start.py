"""Claude Code SessionStart hook — injects Overmind context into new sessions.

Called by Claude Code via settings.json hook. Stdout is injected as context
that Claude can see. Must be fast (< 2 seconds).
"""
from __future__ import annotations

import os


def main() -> None:
    # Determine project path from CWD or environment
    project_path = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    try:
        from overmind.config import default_db_path
        from overmind.storage.db import StateDatabase
        from overmind.activation.context_injector import ContextInjector
        from overmind.activation.session_tracker import SessionTracker

        db = StateDatabase(default_db_path())
        try:
            # Register this session
            tracker = SessionTracker(db)
            tracker.cleanup_stale()
            session_id = tracker.register("claude", project_path)

            # Build and print context (stdout goes to Claude)
            injector = ContextInjector(db)
            context = injector.build_context(project_path, runner_type="claude")
            if context:
                print(context)
        finally:
            db.close()
    except Exception:
        pass  # Never block Claude Code startup


if __name__ == "__main__":
    main()
