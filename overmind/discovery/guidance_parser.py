from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from overmind.redaction import redact_text

COMMAND_PREFIXES = (
    "python ",
    "python -m",
    "pytest",
    "node ",
    "npm ",
    "npx ",
    "pnpm ",
    "yarn ",
    "rscript",
    "powershell ",
    "cmd /c",
)


@dataclass(slots=True)
class GuidanceScanResult:
    found: list[str] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)


class GuidanceParser:
    def __init__(self, max_bytes: int = 65536) -> None:
        self.max_bytes = max_bytes

    def load(self, root: Path, filenames: list[str]) -> GuidanceScanResult:
        result = GuidanceScanResult()
        for filename in self._ordered_filenames(filenames):
            path = root / filename
            if not path.exists() or not path.is_file():
                continue
            result.found.append(path.name)
            text = redact_text(path.read_text(encoding="utf-8-sig", errors="ignore")[: self.max_bytes])
            for line in self._extract_lines(text):
                if line not in result.summary:
                    result.summary.append(line)
                if len(result.summary) >= 8:
                    break
            for command in self._extract_commands(text):
                if command not in result.commands:
                    result.commands.append(command)
        return result

    def _ordered_filenames(self, filenames: list[str]) -> list[str]:
        priority = {"claude.md": 0, "agents.md": 1, "readme.md": 2, "contributing.md": 3}
        return sorted(filenames, key=lambda name: (priority.get(name.lower(), 9), name.lower()))

    def _extract_lines(self, text: str) -> list[str]:
        lines: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if raw_line.startswith(("#", "-", "*")) or len(lines) < 3:
                cleaned = line.lstrip("#-* ").strip()
                if cleaned:
                    lines.append(cleaned[:160])
            if len(lines) >= 8:
                break
        return lines

    def _extract_commands(self, text: str) -> list[str]:
        commands: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip().strip("`")
            lowered = line.lower()
            if not line:
                continue
            if lowered.startswith(COMMAND_PREFIXES):
                commands.append(line)
        return commands
