from __future__ import annotations

from collections import Counter
import hashlib
import re


class LoopDetector:
    _divider_pattern = re.compile(r"^[=\-_*#~]{4,}$")

    def _is_substantive(self, line: str) -> bool:
        stripped = line.strip().lower()
        if not stripped:
            return False
        if self._divider_pattern.fullmatch(stripped):
            return False
        return any(character.isalnum() for character in stripped)

    def _normalize_for_fingerprint(self, line: str) -> str:
        """Strip timestamps, digits, whitespace for content-based comparison."""
        normalized = line.strip().lower()
        normalized = re.sub(r'\d{4}-\d{2}-\d{2}', '', normalized)
        normalized = re.sub(r'\d{1,2}:\d{2}(:\d{2})?', '', normalized)
        normalized = re.sub(r'\d+', '#', normalized)
        return normalized.strip()

    def _fingerprint(self, line: str) -> str:
        return hashlib.md5(self._normalize_for_fingerprint(line).encode()).hexdigest()[:12]

    def detect_by_fingerprint(self, lines: list[str], window: int = 20, threshold: int = 3) -> bool:
        substantive = [line for line in lines if self._is_substantive(line)]
        if len(substantive) < threshold:
            return False
        recent = substantive[-window:]
        fingerprints = [self._fingerprint(line) for line in recent]
        counts = Counter(fingerprints)
        return any(count >= threshold for count in counts.values())

    def detect(self, lines: list[str], threshold: int = 3) -> bool:
        # Fast path: exact line matching
        normalized = [line.strip().lower() for line in lines if self._is_substantive(line)]
        if len(normalized) < threshold:
            return False
        counts = Counter(normalized)
        if any(count >= threshold for count in counts.values()):
            return True
        trailing = normalized[-threshold:]
        if len(set(trailing)) == 1:
            return True
        # Fallback: fingerprint-based detection
        return self.detect_by_fingerprint(lines, threshold=threshold)
