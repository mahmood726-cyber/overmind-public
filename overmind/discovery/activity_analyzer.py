from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from overmind.discovery.analysis_signals import describe_analysis_signals, detect_analysis_signals
from overmind.redaction import redact_text

ACTIVITY_FILENAMES = {
    "development_log.md",
    "session_summary.md",
    "session_january_4_2026.md",
    "latest.log",
    ".rhistory",
    "living-drift-history.json",
}
ACTIVITY_KEYWORDS = (
    "history",
    "transcript",
    "session",
    "nightly",
    "baseline",
    "oracle",
    "validation",
    "drift",
    "monitor",
)
WARNING_KEYWORDS = (
    "warning",
    "not positive definite",
    "coefficient may be infinite",
    "setting lc_",
)


@dataclass(slots=True)
class ActivityScanResult:
    files: list[str] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)
    has_oracle_benchmarks: bool = False
    has_drift_history: bool = False
    has_validation_history: bool = False
    advanced_math_signals: list[str] = field(default_factory=list)


class ActivityLogAnalyzer:
    def __init__(self, ignored_directories: list[str], max_depth: int = 4, max_files: int = 12) -> None:
        self.ignored_directories = set(ignored_directories)
        self.max_depth = max_depth
        self.max_files = max_files

    def signature_files(self, root: Path) -> list[Path]:
        return self._discover_files(root)[:5]

    def analyze(self, root: Path) -> ActivityScanResult:
        result = ActivityScanResult()
        files = self._discover_files(root)
        for path in files[: self.max_files]:
            result.files.append(str(path))
            lowered = str(path).lower()
            if "oracle" in lowered:
                result.has_oracle_benchmarks = True
            if "drift" in lowered:
                result.has_drift_history = True
            if any(token in lowered for token in ("validation", "baseline", "nightly", "selenium", "playwright", "test_")):
                result.has_validation_history = True

            text = self._safe_read(path)
            for signal in detect_analysis_signals(f"{path.name}\n{text}"):
                if signal not in result.advanced_math_signals:
                    result.advanced_math_signals.append(signal)
            if not text:
                continue
            lowered_text = text.lower()
            if any(keyword in lowered_text for keyword in ("[pass]", '"passed"', "100% selenium pass rate")):
                self._append_summary(result.summary, f"stored validation evidence present: {path.name}")
                result.has_validation_history = True
            if any(keyword in lowered_text for keyword in WARNING_KEYWORDS):
                self._append_summary(result.summary, f"warning-bearing activity log present: {path.name}")
            if "oracle benchmark" in lowered_text or "oracle benchmark complete" in lowered_text:
                result.has_oracle_benchmarks = True
                self._append_summary(result.summary, f"oracle parity workflow present: {path.name}")
            if "living-drift-history" in lowered or "benchmarkstatus" in lowered_text:
                result.has_drift_history = True
                self._append_summary(result.summary, f"living drift snapshots present: {path.name}")

        if result.has_validation_history:
            self._append_summary(result.summary, "repeatable validation logs detected")
        if result.has_oracle_benchmarks:
            self._append_summary(result.summary, "oracle benchmark workflow detected")
        if result.has_drift_history:
            self._append_summary(result.summary, "drift history artifacts detected")
        if result.advanced_math_signals:
            labels = ", ".join(describe_analysis_signals(result.advanced_math_signals[:3]))
            self._append_summary(result.summary, f"advanced analytical workflows detected: {labels}")
        return result

    def _discover_files(self, root: Path) -> list[Path]:
        matches: list[Path] = []
        for current_root, dirnames, filenames in os.walk(root):
            current = Path(current_root)
            relative_depth = len(current.relative_to(root).parts)
            if relative_depth > self.max_depth:
                dirnames[:] = []
                continue
            dirnames[:] = [name for name in dirnames if name not in self.ignored_directories]
            for filename in filenames:
                lowered = filename.lower()
                if lowered in ACTIVITY_FILENAMES or any(token in lowered for token in ACTIVITY_KEYWORDS):
                    matches.append(current / filename)
        return sorted(matches, key=lambda path: path.stat().st_mtime, reverse=True)

    def _safe_read(self, path: Path) -> str:
        try:
            return redact_text(path.read_text(encoding="utf-8-sig", errors="ignore")[:12000])
        except OSError:
            return ""

    def _append_summary(self, summary: list[str], line: str) -> None:
        if line not in summary and len(summary) < 10:
            summary.append(line)
