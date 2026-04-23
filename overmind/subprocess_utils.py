"""Shared subprocess utilities for safe command execution."""
from __future__ import annotations

import logging
import os
import re
import shlex
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Direct executables that Overmind will launch for verification work.
ALLOWED_COMMAND_PREFIXES = (
    "python",
    "python3",
    "py",
    "rscript",
    "node",
    "npm",
    "npx",
    "pytest",
    "unittest",
    "uv",
    "poetry",
    "tox",
    "hatch",
    "make",
)
SCRIPT_WRAPPERS = {"bash", "sh"}
POWERSHELL_WRAPPERS = {"powershell", "pwsh"}
CMD_WRAPPERS = {"cmd"}
WINDOWS_ABSOLUTE_EXECUTABLE_RE = r'^\s*"?[A-Za-z]:\\'
SHELL_CONTROL_TOKENS = {"&&", "||", ";", "|", "<", ">", ">>", "&", "2>", "2>>"}
WINDOWS_EXECUTABLE_CANDIDATES = {
    "rscript": [
        Path(r"C:\Program Files\R\R-4.5.2\bin\Rscript.exe"),
        Path(r"C:\Program Files\R\R-4.5.1\bin\Rscript.exe"),
    ],
    "python": [Path(sys.executable)],
    "python3": [Path(sys.executable)],
}


def _strip_matching_quotes(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in {'"', "'"}:
        return token[1:-1]
    return token


def _should_use_windows_split(command: str) -> bool:
    return os.name == "nt" and bool(re.match(WINDOWS_ABSOLUTE_EXECUTABLE_RE, command))


def _split_for_validation(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=False)
    except ValueError:
        return command.split()


def _resolve_windows_executable(parts: list[str]) -> list[str]:
    if os.name != "nt" or not parts:
        return parts

    parts[0] = _strip_matching_quotes(parts[0])
    if re.match(WINDOWS_ABSOLUTE_EXECUTABLE_RE, parts[0]):
        return parts

    resolved = shutil.which(parts[0])
    if resolved:
        parts[0] = resolved
        return parts

    executable = _normalized_executable(parts[0])
    for candidate in WINDOWS_EXECUTABLE_CANDIDATES.get(executable, []):
        if candidate.exists():
            parts[0] = str(candidate)
            break
    return parts


def split_command(command: str) -> list[str]:
    """Split a shell command string into a list for shell=False execution."""
    try:
        if _should_use_windows_split(command):
            parts = [_strip_matching_quotes(part) for part in shlex.split(command, posix=False)]
            return _resolve_windows_executable(parts)
        return _resolve_windows_executable(shlex.split(command))
    except ValueError as exc:
        logger.warning("shlex.split failed for %r: %s; using basic split", command[:80], exc)
        return _resolve_windows_executable(command.split())


def _normalized_executable(token: str) -> str:
    executable = token.replace("\\", "/").rsplit("/", 1)[-1].lower()
    executable = executable.strip("'\"")
    for suffix in (".exe", ".cmd", ".bat"):
        if executable.endswith(suffix):
            return executable[: -len(suffix)]
    return executable


def _resolve_wrapper_target(
    target: str,
    *,
    cwd: str | Path | None,
) -> Path | None:
    normalized = _strip_matching_quotes(target)
    path = Path(normalized)
    if not path.is_absolute():
        if cwd is None:
            return None
        path = Path(cwd) / path
    try:
        return path.resolve()
    except OSError:
        return None


def _is_repo_local_script(
    target: str,
    *,
    cwd: str | Path | None,
    suffixes: tuple[str, ...],
) -> bool:
    normalized = _strip_matching_quotes(target)
    lowered = normalized.lower()
    if not lowered.endswith(suffixes):
        return False
    if cwd is None:
        return True
    root = Path(cwd).resolve()
    resolved = _resolve_wrapper_target(target, cwd=cwd)
    if resolved is None or not resolved.exists():
        return False
    try:
        resolved.relative_to(root)
    except ValueError:
        return False
    return True


def validate_command_prefix_with_detail(
    command: str,
    *,
    cwd: str | Path | None = None,
) -> tuple[bool, str | None]:
    """Check that a command starts with an allowlisted executable."""
    parts = _split_for_validation(command)
    if not parts:
        return False, "Blocked: empty command"

    executable = _normalized_executable(parts[0])
    if executable in ALLOWED_COMMAND_PREFIXES:
        return True, None

    if executable in SCRIPT_WRAPPERS:
        if len(parts) < 2 or parts[1].startswith("-"):
            return False, "Blocked: bash/sh wrapper must target a repo-local .sh script"
        control = next((part for part in parts[2:] if part in SHELL_CONTROL_TOKENS), None)
        if control:
            return False, f"Blocked: unsafe shell control operator {control!r} in wrapper command"
        if not _is_repo_local_script(parts[1], cwd=cwd, suffixes=(".sh",)):
            return False, "Blocked: bash/sh wrapper must target a repo-local .sh script"
        return True, None

    if executable in POWERSHELL_WRAPPERS:
        lowered_parts = [part.lower() for part in parts[1:]]
        if any(part in {"-command", "-encodedcommand", "-c"} for part in lowered_parts):
            return False, "Blocked: PowerShell verification must use -File with a repo-local .ps1 script"
        for index, part in enumerate(parts[1:-1], start=1):
            if part.lower() == "-file":
                control = next((token for token in parts[index + 2 :] if token in SHELL_CONTROL_TOKENS), None)
                if control:
                    return False, f"Blocked: unsafe shell control operator {control!r} in wrapper command"
                if _is_repo_local_script(parts[index + 1], cwd=cwd, suffixes=(".ps1",)):
                    return True, None
                return False, "Blocked: PowerShell verification must use a repo-local .ps1 script"
        return False, "Blocked: PowerShell verification must use -File with a repo-local .ps1 script"

    if executable in CMD_WRAPPERS:
        if len(parts) < 3 or parts[1].lower() != "/c":
            return False, "Blocked: cmd verification must use /c with a repo-local .cmd or .bat script"
        control = next((token for token in parts[3:] if token in SHELL_CONTROL_TOKENS), None)
        if control:
            return False, f"Blocked: unsafe shell control operator {control!r} in wrapper command"
        if _is_repo_local_script(parts[2], cwd=cwd, suffixes=(".bat", ".cmd")):
            return True, None
        return False, "Blocked: cmd verification must use a repo-local .cmd or .bat script"

    return False, f"Blocked: command prefix not allowlisted: {command[:200]}"


def validate_command_prefix(command: str, *, cwd: str | Path | None = None) -> bool:
    """Check that a command starts with an allowlisted executable."""
    valid, _detail = validate_command_prefix_with_detail(command, cwd=cwd)
    return valid
