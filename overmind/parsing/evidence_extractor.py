from __future__ import annotations

import re

from overmind.storage.models import EvidenceEvent


COMMAND_PATTERNS = (
    re.compile(r"^\$\s+"),
    re.compile(r"^COMMAND:\s*", re.IGNORECASE),
)
PASS_PATTERNS = {
    "build_passed": re.compile(r"\b(build|compiled).*\b(passed|success(?:ful(?:ly)?)?|ok)\b", re.IGNORECASE),
    "tests_passed": re.compile(r"\b(test|tests).*\b(passed|success(?:ful(?:ly)?)?)\b", re.IGNORECASE),
    "playwright_passed": re.compile(r"\b(playwright|browser).*\b(passed|success(?:ful(?:ly)?)?)\b", re.IGNORECASE),
}
FAIL_PATTERNS = {
    "build_failed": re.compile(r"\b(build|compile).*\b(failed|failure|error)\b", re.IGNORECASE),
    "tests_failed": re.compile(r"(?:^FAILED(?!:\s*0\b)\b|\btests?\s+failed\b|\bpytest\b.*\berror\b)", re.IGNORECASE),
    "timeout": re.compile(r"\b(?:timed out|timeout\b(?!-\d))", re.IGNORECASE),
    "memory_warning": re.compile(r"\b(out of memory|memory warning|heap)\b", re.IGNORECASE),
    "rate_limited": re.compile(r"\b(rate limit|too many requests|quota|usage limit|try again at)\b", re.IGNORECASE),
    "numeric_warning": re.compile(r"\b(not positive definite|coefficient may be infinite|experimental)\b", re.IGNORECASE),
    "locale_warning": re.compile(r"\bsetting lc_[a-z_]+=?.*failed\b", re.IGNORECASE),
}
CLAIM_PATTERN = re.compile(r"\b(fixed|resolved|complete|done)\b", re.IGNORECASE)


class EvidenceExtractor:
    def extract(self, lines: list[str]) -> tuple[list[EvidenceEvent], list[str], bool]:
        events: list[EvidenceEvent] = []
        commands: list[str] = []
        unsupported_claim = False

        for line in lines:
            lowered_line = line.lower()
            if any(pattern.search(line) for pattern in COMMAND_PATTERNS):
                commands.append(line.strip())
            if CLAIM_PATTERN.search(line):
                unsupported_claim = True
            for name, pattern in PASS_PATTERNS.items():
                if pattern.search(line):
                    events.append(EvidenceEvent(kind=name, line=line, severity="info"))
            for name, pattern in FAIL_PATTERNS.items():
                if pattern.search(line):
                    if name.endswith("failed") and "passed" in lowered_line:
                        continue
                    events.append(EvidenceEvent(kind=name, line=line, severity="warning"))
        return events, commands, unsupported_claim
