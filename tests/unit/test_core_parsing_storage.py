"""25 tests for core (state_machine, policy_engine, scheduler), parsing (evidence_extractor,
failure_classifier), redaction, and storage models."""

from __future__ import annotations

from overmind.config import PoliciesConfig
from overmind.core.policy_engine import PolicyEngine
from overmind.core.scheduler import Scheduler
from overmind.core.state_machine import TASK_TRANSITIONS, assert_valid_task_transition
from overmind.parsing.evidence_extractor import EvidenceExtractor
from overmind.parsing.failure_classifier import FailureClassifier
from overmind.redaction import detect_secret_kinds, redact_text
from overmind.storage.models import (
    EvidenceEvent,
    MachineHealthSnapshot,
    MemoryRecord,
    ProjectRecord,
    RunnerRecord,
    TaskRecord,
    slugify,
    utc_now,
)


# ---------------------------------------------------------------------------
# 1. State Machine (5 tests)
# ---------------------------------------------------------------------------


def test_valid_transition_queued_to_assigned():
    assert_valid_task_transition("QUEUED", "ASSIGNED")


def test_invalid_transition_queued_to_completed():
    try:
        assert_valid_task_transition("QUEUED", "COMPLETED")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "QUEUED" in str(exc) and "COMPLETED" in str(exc)


def test_same_state_transition_running():
    assert_valid_task_transition("RUNNING", "RUNNING")


def test_archived_has_no_transitions():
    assert TASK_TRANSITIONS["ARCHIVED"] == set()


def test_completed_to_archived_is_valid():
    assert_valid_task_transition("COMPLETED", "ARCHIVED")


# ---------------------------------------------------------------------------
# 2. Policy Engine (2 tests)
# ---------------------------------------------------------------------------


def _make_policies(**overrides) -> PoliciesConfig:
    concurrency = {
        "default_active_sessions": 3,
        "max_active_sessions": 5,
        "degraded_sessions": 1,
        "scale_down_cpu_above": 88,
        "scale_down_ram_above": 85,
        "scale_down_swap_above_mb": 1024,
        "scale_up_cpu_below": 70,
    }
    concurrency.update(overrides)
    return PoliciesConfig(concurrency=concurrency)


def _make_health(cpu: float = 50.0, ram: float = 50.0, swap: float = 0.0,
                 load_state: str = "healthy") -> MachineHealthSnapshot:
    return MachineHealthSnapshot(
        cpu_percent=cpu, ram_percent=ram, swap_used_mb=swap,
        active_sessions=0, load_state=load_state,
    )


def test_policy_concurrency_by_cpu_level():
    """High CPU -> degraded, low CPU -> max, normal CPU -> default."""
    engine = PolicyEngine(_make_policies())
    assert engine.compute_concurrency(_make_health(cpu=95), available_runners=10) == 1
    assert engine.compute_concurrency(_make_health(cpu=30), available_runners=10) == 5
    assert engine.compute_concurrency(_make_health(cpu=75, load_state="moderate"), available_runners=10) == 3


def test_required_proof_falls_back_to_task_verification():
    engine = PolicyEngine(PoliciesConfig(risk_policy={}))
    task = TaskRecord(
        task_id="t1", project_id="p1", title="fix bug", task_type="bugfix",
        source="manual", priority=5.0, risk="low", expected_runtime_min=10,
        expected_context_cost="small", required_verification=["relevant_tests"],
    )
    assert engine.required_proof_for(task) == ["relevant_tests"]


# ---------------------------------------------------------------------------
# 3. Scheduler (4 tests)
# ---------------------------------------------------------------------------


def _make_runner(runner_id: str, runner_type: str = "claude",
                 status: str = "AVAILABLE", available: bool = True,
                 success_rate: float = 0.8, failure_rate: float = 0.1,
                 avg_latency: float = 5.0) -> RunnerRecord:
    return RunnerRecord(
        runner_id=runner_id, runner_type=runner_type, environment="local",
        command="echo test", status=status, available=available,
        success_rate_7d=success_rate, failure_rate_7d=failure_rate,
        avg_latency_sec=avg_latency,
    )


def _make_task(task_id: str, project_id: str = "proj-1", priority: float = 5.0,
               task_type: str = "bugfix") -> TaskRecord:
    return TaskRecord(
        task_id=task_id, project_id=project_id, title="a task",
        task_type=task_type, source="manual", priority=priority,
        risk="low", expected_runtime_min=10, expected_context_cost="small",
        required_verification=["relevant_tests"],
    )


def _make_project(project_id: str = "proj-1") -> ProjectRecord:
    return ProjectRecord(project_id=project_id, name="Test", root_path="/tmp/test")


def _prompt_builder(project, task):
    return f"do {task.task_id}"


def test_scheduler_assigns_up_to_capacity():
    policies = PoliciesConfig(routing={"claude": {"strengths": []}})
    scheduler = Scheduler(policies)
    tasks = [_make_task("t1"), _make_task("t2"), _make_task("t3")]
    runners = [_make_runner("r1"), _make_runner("r2")]
    projects = {"proj-1": _make_project()}
    assignments = scheduler.assign(tasks, runners, projects, capacity=5, prompt_builder=_prompt_builder)
    assert len(assignments) == 2


def test_scheduler_empty_when_no_runners_or_zero_capacity():
    """Returns empty when no runners available OR when capacity is 0."""
    policies = PoliciesConfig(routing={"claude": {"strengths": []}})
    scheduler = Scheduler(policies)
    tasks = [_make_task("t1")]
    projects = {"proj-1": _make_project()}
    assert scheduler.assign(tasks, [], projects, capacity=5, prompt_builder=_prompt_builder) == []
    runners = [_make_runner("r1")]
    assert scheduler.assign(tasks, runners, projects, capacity=0, prompt_builder=_prompt_builder) == []


def test_scheduler_higher_priority_first():
    policies = PoliciesConfig(routing={"claude": {"strengths": []}})
    scheduler = Scheduler(policies)
    low = _make_task("t-low", priority=1.0)
    high = _make_task("t-high", priority=10.0)
    runners = [_make_runner("r1")]
    projects = {"proj-1": _make_project()}
    assignments = scheduler.assign([low, high], runners, projects, capacity=1, prompt_builder=_prompt_builder)
    assert len(assignments) == 1
    assert assignments[0].task_id == "t-high"


def test_scheduler_test_strength_boosts_verification_tasks():
    policies = PoliciesConfig(routing={"claude": {"strengths": ["tests"]}})
    scheduler = Scheduler(policies)
    runner_strong = _make_runner("r-strong", runner_type="claude", success_rate=0.5, failure_rate=0.1)
    runner_weak = _make_runner("r-weak", runner_type="codex", success_rate=0.5, failure_rate=0.1)
    task = _make_task("t-verify", task_type="verification")
    projects = {"proj-1": _make_project()}
    assignments = scheduler.assign([task], [runner_strong, runner_weak], projects, capacity=1, prompt_builder=_prompt_builder)
    assert assignments[0].runner_id == "r-strong"


# ---------------------------------------------------------------------------
# 4. Evidence Extractor (5 tests)
# ---------------------------------------------------------------------------


def test_extractor_detects_tests_passed():
    events, _, _ = EvidenceExtractor().extract(["All 25 tests passed successfully"])
    assert any(e.kind == "tests_passed" for e in events)


def test_extractor_detects_build_failed():
    events, _, _ = EvidenceExtractor().extract(["build failed with error"])
    assert any(e.kind == "build_failed" for e in events)


def test_extractor_detects_rate_limit():
    events, _, _ = EvidenceExtractor().extract(["Error: rate limit exceeded, try again at 3pm"])
    assert any(e.kind == "rate_limited" for e in events)


def test_extractor_claim_pattern_detects_keywords():
    ext = EvidenceExtractor()
    assert ext.extract(["I fixed the bug"])[2] is True
    assert ext.extract(["Task is done"])[2] is True
    assert ext.extract(["Implementation complete"])[2] is True


def test_extractor_failed_zero_does_not_trigger_tests_failed():
    events, _, _ = EvidenceExtractor().extract(["FAILED: 0"])
    assert not any(e.kind == "tests_failed" for e in events)


# ---------------------------------------------------------------------------
# 5. Failure Classifier (3 tests)
# ---------------------------------------------------------------------------


def test_classifier_loop_and_rate_limit_return_needs_intervention():
    """Loop detected -> NEEDS_INTERVENTION; rate limit + nonzero exit -> pause action."""
    classifier = FailureClassifier()
    state, risks, _ = classifier.classify(
        events=[], loop_detected=True, proof_gap=False,
        exit_code=None, idle_seconds=0, idle_timeout_seconds=600,
    )
    assert state == "NEEDS_INTERVENTION"
    assert "repeated retry loop detected" in risks

    state2, _, action2 = classifier.classify(
        events=[EvidenceEvent(kind="rate_limited", line="quota hit")],
        loop_detected=False, proof_gap=False,
        exit_code=1, idle_seconds=0, idle_timeout_seconds=600,
    )
    assert state2 == "NEEDS_INTERVENTION"
    assert "pause" in action2


def test_classifier_clean_exit_no_issues():
    state, _, _ = FailureClassifier().classify(
        events=[], loop_detected=False, proof_gap=False,
        exit_code=0, idle_seconds=0, idle_timeout_seconds=600,
    )
    assert state == "VERIFYING"


def test_classifier_idle_timeout_adds_risk():
    _, risks, _ = FailureClassifier().classify(
        events=[], loop_detected=False, proof_gap=False,
        exit_code=None, idle_seconds=700, idle_timeout_seconds=600,
    )
    assert "session idle beyond limit" in risks


# ---------------------------------------------------------------------------
# 6. Redaction (2 tests)
# ---------------------------------------------------------------------------


def test_redact_secret_types():
    """Redacts Google API keys (AIza...), OpenAI-like keys (sk-...), GitHub tokens (ghp_...)."""
    google = redact_text("key=AIzaSyA1234567890abcdefXYZ")
    assert "AIza" not in google and "[REDACTED:google_api_key]" in google

    openai = redact_text("Authorization: sk-abcdefghijklmnopqrstuvwxyz1234")
    assert "sk-" not in openai and "[REDACTED:openai_like_key]" in openai

    github = redact_text("token ghp_abcdefghijklmnopqrstuvwxyz1234")
    assert "ghp_" not in github and "[REDACTED:github_token]" in github


def test_detect_secret_kinds_and_clean_passthrough():
    """detect_secret_kinds returns list of found types; clean text passes through unchanged."""
    text = "key=AIzaSyA1234567890abcdefXYZ and sk-abcdefghijklmnopqrstuvwxyz1234"
    kinds = detect_secret_kinds(text)
    assert "google_api_key" in kinds
    assert "openai_like_key" in kinds

    clean = "This is perfectly safe text with no secrets."
    assert redact_text(clean) == clean


# ---------------------------------------------------------------------------
# 7. Storage Models (4 tests)
# ---------------------------------------------------------------------------


def test_slugify_converts_project_name():
    assert slugify("My Project!") == "my-project"


def test_utc_now_returns_iso_format():
    ts = utc_now()
    assert "T" in ts
    assert len(ts) >= 19


def test_memory_record_to_dict():
    record = MemoryRecord(
        memory_id="m1", memory_type="project_learning", scope="proj-a",
        title="Learning", content="content here",
    )
    d = record.to_dict()
    assert d["memory_id"] == "m1"
    assert d["memory_type"] == "project_learning"
    assert d["content"] == "content here"
    assert "created_at" in d


def test_project_record_to_dict_includes_all_fields():
    record = ProjectRecord(
        project_id="p1", name="Test Project", root_path="/tmp/test",
        platform="linux", is_git_repo=True, stack=["python"],
    )
    d = record.to_dict()
    assert d["project_id"] == "p1"
    assert d["name"] == "Test Project"
    assert d["root_path"] == "/tmp/test"
    assert d["platform"] == "linux"
    assert d["is_git_repo"] is True
    assert d["stack"] == ["python"]
    assert "last_indexed_at" in d
    assert "risk_profile" in d
