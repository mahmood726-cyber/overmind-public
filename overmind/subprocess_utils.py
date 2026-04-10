"""Shared subprocess utilities for safe command execution."""
from __future__ import annotations

import shlex
import logging

logger = logging.getLogger(__name__)

# Allowlisted command prefixes for baseline execution
ALLOWED_COMMAND_PREFIXES = (
    "python", "python3", "py",
    "Rscript", "Rscript.exe",
    "node", "npm", "npx",
    "pytest", "unittest",
)


def split_command(command: str) -> list[str]:
    """Split a shell command string into a list for shell=False execution.

    Uses posix=True (default) which correctly strips quotes from arguments.
    Falls back to basic split with a warning if shlex fails.
    """
    try:
        return shlex.split(command)
    except ValueError as exc:
        logger.warning("shlex.split failed for %r: %s — using basic split", command[:80], exc)
        return command.split()


def validate_command_prefix(command: str) -> bool:
    """Check that a command starts with an allowlisted executable."""
    # Use posix=False for validation so Windows backslash paths are preserved
    try:
        parts = shlex.split(command, posix=False)
    except ValueError:
        parts = command.split()
    if not parts:
        return False
    executable = parts[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
    # Strip quotes that posix=False preserves
    executable = executable.strip("'\"")

    # Strip .exe suffix for comparison
    if executable.endswith(".exe"):
        executable = executable[:-4]
    return any(executable == prefix.lower() for prefix in ALLOWED_COMMAND_PREFIXES)
