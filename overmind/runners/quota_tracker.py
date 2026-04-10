from __future__ import annotations

from datetime import UTC, datetime, timedelta

RATE_LIMIT_HINTS = (
    "rate limit",
    "too many requests",
    "quota",
    "try again later",
    "usage limit",
    "too many people",
    "at capacity",
    "overloaded",
    "temporarily unavailable",
)


class QuotaTracker:
    def __init__(self, cooldown_minutes: int = 30) -> None:
        self.cooldown_minutes = cooldown_minutes

    def detect_rate_limit(self, lines: list[str]) -> bool:
        return any(hint in line.lower() for line in lines for hint in RATE_LIMIT_HINTS)

    def cooldown_active(self, quota_state: str, last_seen_at: str | None) -> bool:
        if quota_state != "limited" or not last_seen_at:
            return False
        try:
            timestamp = datetime.fromisoformat(last_seen_at)
        except ValueError:
            return False
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return datetime.now(UTC) - timestamp < timedelta(minutes=self.cooldown_minutes)
