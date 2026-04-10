from __future__ import annotations

import re


SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "google_api_key": re.compile(r"AIza[0-9A-Za-z\-_]{20,}"),
    "openai_like_key": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "bearer_token": re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\._\-]{20,}"),
}


def redact_text(text: str) -> str:
    redacted = text
    for kind, pattern in SECRET_PATTERNS.items():
        redacted = pattern.sub(f"[REDACTED:{kind}]", redacted)
    return redacted


def detect_secret_kinds(text: str) -> list[str]:
    found: list[str] = []
    for kind, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            found.append(kind)
    return found

