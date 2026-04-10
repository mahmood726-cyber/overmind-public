"""Install Overmind hooks and aliases.

Usage: python -m overmind.activation.install

This script:
1. Adds Claude Code hooks to ~/.claude/settings.json (SessionStart + Stop)
2. Adds shell aliases to ~/.bashrc (overmind wrap claude/codex/gemini)
3. Verifies the installation
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def install_claude_hooks() -> bool:
    """Add Overmind hooks to Claude Code settings.json."""
    settings_path = Path.home() / ".claude" / "settings.json"
    if not settings_path.exists():
        print(f"  SKIP: {settings_path} not found")
        return False

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    hooks = settings.setdefault("hooks", {})

    python = sys.executable.replace("\\", "/")
    start_script = "C:/overmind/overmind/activation/hooks/on_session_start.py"
    stop_script = "C:/overmind/overmind/activation/hooks/on_session_stop.py"

    start_cmd = f'"{python}" "{start_script}"'
    stop_cmd = f'"{python}" "{stop_script}"'

    # Add SessionStart hook
    session_start_hooks = hooks.setdefault("SessionStart", [])
    already_installed = any(
        start_script in json.dumps(h) for h in session_start_hooks
    )
    if not already_installed:
        session_start_hooks.append({
            "hooks": [{"type": "command", "command": start_cmd}]
        })
        print(f"  ADDED: SessionStart hook -> {start_script}")
    else:
        print(f"  EXISTS: SessionStart hook already installed")

    # Add Stop hook
    stop_hooks = hooks.setdefault("Stop", [])
    already_installed = any(
        stop_script in json.dumps(h) for h in stop_hooks
    )
    if not already_installed:
        stop_hooks.append({
            "hooks": [{"type": "command", "command": stop_cmd}]
        })
        print(f"  ADDED: Stop hook -> {stop_script}")
    else:
        print(f"  EXISTS: Stop hook already installed")

    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    return True


def install_shell_aliases() -> bool:
    """Add Overmind wrapper aliases to ~/.bashrc."""
    bashrc = Path.home() / ".bashrc"

    marker = "# >>> OVERMIND ACTIVATION >>>"
    end_marker = "# <<< OVERMIND ACTIVATION <<<"

    aliases = f"""\n{marker}
# Auto-activate Overmind for all AI agent sessions
alias om='python -c "from overmind.cli import main; main()" '
alias om-claude='python -c "from overmind.activation.wrap import wrap; wrap(\\"claude\\", [])"'
alias om-codex='python -c "from overmind.activation.wrap import wrap; wrap(\\"codex\\", [])"'
alias om-gemini='python -c "from overmind.activation.wrap import wrap; wrap(\\"gemini\\", [])"'
alias om-sessions='python -c "from overmind.cli import main; main([\\"sessions\\"])"'
alias om-memories='python -c "from overmind.cli import main; main([\\"memories\\", \\"--stats\\"])"'
alias om-watch='python -c "from overmind.activation.watchdog import watch; watch(__import__(\\"pathlib\\").Path(\\"C:/overmind/data/state/overmind.db\\"))"'
{end_marker}\n"""

    if bashrc.exists():
        content = bashrc.read_text(encoding="utf-8")
        if marker in content:
            print("  EXISTS: Shell aliases already installed in .bashrc")
            return True
        content += aliases
    else:
        content = aliases

    bashrc.write_text(content, encoding="utf-8")
    print("  ADDED: Shell aliases to ~/.bashrc")
    print("  Aliases: om-claude, om-codex, om-gemini, om-sessions, om-memories, om-watch")
    return True


def verify() -> None:
    """Verify installation."""
    print("\nVerification:")

    settings_path = Path.home() / ".claude" / "settings.json"
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        hooks = settings.get("hooks", {})
        has_start = any("on_session_start" in json.dumps(h) for h in hooks.get("SessionStart", []))
        has_stop = any("on_session_stop" in json.dumps(h) for h in hooks.get("Stop", []))
        print(f"  Claude SessionStart hook: {'OK' if has_start else 'MISSING'}")
        print(f"  Claude Stop hook: {'OK' if has_stop else 'MISSING'}")

    bashrc = Path.home() / ".bashrc"
    if bashrc.exists():
        has_aliases = "OVERMIND ACTIVATION" in bashrc.read_text(encoding="utf-8")
        print(f"  Shell aliases: {'OK' if has_aliases else 'MISSING'}")

    print(f"  Overmind DB: C:\\overmind\\data\\state\\overmind.db")
    print(f"  Python: {sys.executable}")


def main() -> None:
    print("=== OVERMIND Installation ===\n")
    print("1. Claude Code hooks:")
    install_claude_hooks()
    print("\n2. Shell aliases:")
    install_shell_aliases()
    verify()
    print("\nDone. Restart your terminal for aliases to take effect.")
    print("Claude Code hooks activate immediately on next session.")


if __name__ == "__main__":
    main()
