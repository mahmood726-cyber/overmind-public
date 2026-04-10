from __future__ import annotations


class TokenMetrics:
    def __init__(self) -> None:
        self.estimated_tokens = 0

    def add_text(self, text: str) -> None:
        self.estimated_tokens += max(1, len(text) // 4)

