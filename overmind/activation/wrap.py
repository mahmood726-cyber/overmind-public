"""Shell wrapper: `overmind wrap <claude|codex|gemini> [args...]`

Wraps a CLI agent invocation with Overmind context injection and session tracking.
Usage: overmind wrap codex exec "Fix the bug in parser.py"
       overmind wrap gemini "Review the test suite"
       overmind wrap claude  # just opens claude with context
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from overmind.activation.context_injector import ContextInjector
from overmind.activation.session_tracker import SessionTracker
from overmind.storage.db import StateDatabase


RUNNER_COMMANDS = {
    "claude": "claude",
    "codex": "codex",
    "gemini": "gemini",
}


def wrap(runner_type: str, extra_args: list[str], db_path: Path | None = None) -> int:
    """Wrap a CLI agent with Overmind context and session tracking."""
    db_path = db_path or Path(
        os.environ.get("OVERMIND_DB_PATH", "C:\\overmind\\data\\state\\overmind.db")
    )
    project_path = os.getcwd()

    db = StateDatabase(db_path)
    try:
        # Register session
        tracker = SessionTracker(db)
        tracker.cleanup_stale()
        session_id = tracker.register(runner_type, project_path)

        # Build context
        injector = ContextInjector(db)
        context = injector.build_context(project_path, runner_type=runner_type)

        # Print context to user
        if context:
            print(f"[OVERMIND] Session {session_id} registered ({runner_type} on {project_path})")
            print(context)
            print()
    finally:
        db.close()

    # Build command
    base_command = RUNNER_COMMANDS.get(runner_type, runner_type)
    cmd = [base_command] + extra_args

    # Run the agent
    try:
        result = subprocess.run(cmd, shell=False)
        exit_code = result.returncode
    except KeyboardInterrupt:
        exit_code = 130

    # Close session
    db = StateDatabase(db_path)
    try:
        tracker = SessionTracker(db)
        tracker.close_session(session_id)

        # Trigger dream check
        from overmind.memory.dream_engine import DreamEngine
        active_count = len(db.list_memories(status="active", limit=10000))
        dream_engine = DreamEngine(db)
        if dream_engine.should_dream(5, active_count):
            print("[OVERMIND] Dreaming (consolidating memories)...")
            summary = dream_engine.dream()
            print(f"[OVERMIND] Dream complete: {summary.get('merges', 0)} merges, "
                  f"{summary.get('heuristics_generated', 0)} heuristics")
    finally:
        db.close()

    return exit_code
