from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value)
    parts = [part for part in cleaned.split("-") if part]
    return "-".join(parts) or "project"


def _serialize(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _serialize(item) for key, item in asdict(value).items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


@dataclass(slots=True)
class SerializableModel:
    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


@dataclass(slots=True)
class ProjectRecord(SerializableModel):
    project_id: str
    name: str
    root_path: str
    platform: str = "windows"
    is_git_repo: bool = False
    project_type: str = "unknown"
    stack: list[str] = field(default_factory=list)
    has_numeric_logic: bool = False
    has_advanced_math: bool = False
    advanced_math_signals: list[str] = field(default_factory=list)
    advanced_math_score: int = 0
    advanced_math_rigor: str = "none"
    analysis_focus_areas: list[str] = field(default_factory=list)
    analysis_risk_factors: list[str] = field(default_factory=list)
    guidance_files: list[str] = field(default_factory=list)
    guidance_summary: list[str] = field(default_factory=list)
    guidance_commands: list[str] = field(default_factory=list)
    activity_files: list[str] = field(default_factory=list)
    activity_summary: list[str] = field(default_factory=list)
    has_oracle_benchmarks: bool = False
    has_drift_history: bool = False
    has_validation_history: bool = False
    verification_profiles: list[str] = field(default_factory=list)
    recommended_verification: list[str] = field(default_factory=list)
    build_commands: list[str] = field(default_factory=list)
    test_commands: list[str] = field(default_factory=list)
    browser_test_commands: list[str] = field(default_factory=list)
    perf_commands: list[str] = field(default_factory=list)
    risk_profile: str = "medium"
    manifest_hash: str = ""
    package_manager: str = "npm"
    last_active_at: str | None = None
    last_indexed_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class RunnerRecord(SerializableModel):
    runner_id: str
    runner_type: str
    environment: str
    command: str
    status: str = "AVAILABLE"
    health: str = "good"
    current_task_id: str | None = None
    avg_latency_sec: float = 0.0
    success_rate_7d: float = 0.5
    failure_rate_7d: float = 0.0
    quota_state: str = "normal"
    preferred_tasks: list[str] = field(default_factory=list)
    last_seen_at: str = field(default_factory=utc_now)
    optional: bool = False
    available: bool = True
    unavailability_reason: str | None = None


@dataclass(slots=True)
class TaskRecord(SerializableModel):
    task_id: str
    project_id: str
    title: str
    task_type: str
    source: str
    priority: float
    risk: str
    expected_runtime_min: int
    expected_context_cost: str
    required_verification: list[str]
    status: str = "QUEUED"
    assigned_runner_id: str | None = None
    attempt_count: int = 0
    last_error: str | None = None
    verification_summary: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    verify_command: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class InsightRecord(SerializableModel):
    insight_id: str
    scope: str
    pattern: str
    recommendation: str
    confidence: float
    created_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class MachineHealthSnapshot(SerializableModel):
    cpu_percent: float
    ram_percent: float
    swap_used_mb: float
    active_sessions: int
    load_state: str
    captured_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class Assignment(SerializableModel):
    runner_id: str
    task_id: str
    project_id: str
    prompt: str


@dataclass(slots=True)
class EvidenceEvent(SerializableModel):
    kind: str
    line: str
    severity: str = "info"
    created_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class SessionObservation(SerializableModel):
    session_id: str
    runner_id: str
    task_id: str
    lines: list[str]
    total_line_count: int
    exit_code: int | None
    idle_seconds: float
    runtime_seconds: float
    started_at: str
    last_output_at: str
    command: str


@dataclass(slots=True)
class SessionEvidence(SerializableModel):
    task_id: str
    runner_id: str
    state: str
    risks: list[str]
    next_action: str
    required_proof: list[str]
    events: list[EvidenceEvent] = field(default_factory=list)
    last_commands: list[str] = field(default_factory=list)
    output_excerpt: list[str] = field(default_factory=list)
    loop_detected: bool = False
    proof_gap: bool = False
    exited: bool = False
    exit_code: int | None = None


@dataclass(slots=True)
class VerificationResult(SerializableModel):
    task_id: str
    success: bool
    required_checks: list[str]
    completed_checks: list[str]
    skipped_checks: list[str]
    details: list[str]
    created_at: str = field(default_factory=utc_now)


MEMORY_TYPES = {
    "project_learning",
    "runner_learning",
    "task_pattern",
    "decision",
    "regression",
    "heuristic",
}

MEMORY_STATUSES = {"active", "archived", "merged", "expired"}


@dataclass(slots=True)
class MemoryRecord(SerializableModel):
    memory_id: str
    memory_type: str
    scope: str
    title: str
    content: str
    source_task_id: str | None = None
    source_tick: int = 0
    relevance: float = 1.0
    confidence: float = 0.5
    tags: list[str] = field(default_factory=list)
    linked_memories: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    status: str = "active"
    valid_from: str | None = None
    valid_until: str | None = None
    embedding: list[float] | None = None
