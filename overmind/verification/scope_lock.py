"""Immutable scope lock and witness result models for TruthCert verification."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScopeLock:
    project_id: str
    project_path: str
    risk_profile: str
    witness_count: int
    test_command: str
    smoke_modules: tuple[str, ...]
    baseline_path: str | None
    expected_outcome: str
    source_hash: str
    created_at: str


@dataclass(frozen=True, slots=True)
class WitnessResult:
    witness_type: str       # "test_suite" | "smoke" | "numerical"
    verdict: str            # "PASS" | "FAIL" | "SKIP"
    exit_code: int | None
    stdout: str
    stderr: str
    elapsed: float


def compute_tier(risk_profile: str, advanced_math_score: int) -> int:
    """Determine witness count from project risk and math score."""
    if risk_profile == "high" and advanced_math_score >= 10:
        return 3
    if risk_profile in ("high", "medium_high"):
        return 2
    return 1
