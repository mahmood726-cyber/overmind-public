from __future__ import annotations

from pathlib import Path

from overmind.redaction import redact_text
from overmind.storage.models import utc_now


class TranscriptStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, session_id: str, runner_id: str, task_id: str) -> Path:
        return self.base_dir / f"{session_id}_{runner_id}_{task_id}.log"

    def append_event(self, path: Path, message: str) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{utc_now()}] {redact_text(message)}\n")

    def append_line(self, path: Path, line: str) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{utc_now()}] {redact_text(line)}\n")
