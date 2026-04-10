from __future__ import annotations


class SessionMetrics:
    def __init__(self) -> None:
        self.lines_processed = 0

    def record_lines(self, count: int) -> None:
        self.lines_processed += count

