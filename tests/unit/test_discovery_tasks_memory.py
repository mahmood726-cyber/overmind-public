"""Tests for discovery (analysis_signals, activity_analyzer), tasks (prioritizer, task_models),
memory (insights, heuristic_engine), and runners (quota_tracker).

25 unit tests covering 7 modules.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from overmind.discovery.activity_analyzer import ActivityLogAnalyzer, ActivityScanResult
from overmind.discovery.analysis_signals import (
    analysis_rigor_level,
    compute_analysis_score,
    detect_analysis_signals,
)
from overmind.memory.heuristic_engine import HeuristicEngine
from overmind.memory.insights import InsightEngine
from overmind.runners.quota_tracker import QuotaTracker
from overmind.storage.db import StateDatabase
from overmind.storage.models import (
    MemoryRecord,
    ProjectRecord,
    SessionEvidence,
    TaskRecord,
    VerificationResult,
)
from overmind.tasks.prioritizer import Prioritizer
from overmind.tasks.task_models import build_baseline_task, build_test_first_tasks


# ---------------------------------------------------------------------------
# 1. Analysis Signals (4 tests)
# ---------------------------------------------------------------------------

def test_detect_analysis_signals_finds_known_patterns():
    """Detects meta-analysis, bayesian, and returns empty for unrelated text."""
    assert "meta_analysis" in detect_analysis_signals("This study uses meta-analysis to combine 12 RCTs.")
    assert "bayesian_modeling" in detect_analysis_signals("We fitted a Bayesian hierarchical model with MCMC.")
    assert detect_analysis_signals("The weather today is sunny and warm.") == []


def test_compute_analysis_score_adds_weights():
    # meta_analysis=3, bayesian_modeling=4 => 7
    score = compute_analysis_score(["meta_analysis", "bayesian_modeling"])
    assert score == 7


def test_compute_analysis_score_caps_at_20():
    all_signals = [
        "meta_analysis", "network_meta_analysis", "bayesian_modeling",
        "survival_analysis", "competing_risks_multistate", "causal_inference",
        "diagnostic_accuracy", "hierarchical_modeling",
    ]
    score = compute_analysis_score(
        all_signals,
        has_validation_history=True,
        has_oracle_benchmarks=True,
        has_drift_history=True,
    )
    assert score == 20


def test_analysis_rigor_level_thresholds():
    assert analysis_rigor_level(0) == "none"
    assert analysis_rigor_level(3) == "moderate"
    assert analysis_rigor_level(6) == "high"
    assert analysis_rigor_level(10) == "extreme"


# ---------------------------------------------------------------------------
# 2. Activity Analyzer (4 tests)
# ---------------------------------------------------------------------------

def test_activity_analyzer_discovers_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "oracle_benchmark.log").write_text("data", encoding="utf-8")
        Path(tmpdir, "session_summary.md").write_text("notes", encoding="utf-8")
        Path(tmpdir, "unrelated.txt").write_text("nothing", encoding="utf-8")

        analyzer = ActivityLogAnalyzer(ignored_directories=[])
        result = analyzer.analyze(Path(tmpdir))
        basenames = [os.path.basename(f) for f in result.files]
        assert "oracle_benchmark.log" in basenames
        assert "session_summary.md" in basenames
        assert "unrelated.txt" not in basenames


def test_activity_analyzer_detects_oracle_benchmarks():
    with tempfile.TemporaryDirectory() as tmpdir:
        log = Path(tmpdir, "oracle_run.log")
        log.write_text("oracle benchmark complete with 99% match", encoding="utf-8")

        analyzer = ActivityLogAnalyzer(ignored_directories=[])
        result = analyzer.analyze(Path(tmpdir))
        assert result.has_oracle_benchmarks is True


def test_activity_analyzer_detects_validation_history():
    with tempfile.TemporaryDirectory() as tmpdir:
        log = Path(tmpdir, "validation_results.log")
        log.write_text('[PASS] all 42 tests green', encoding="utf-8")

        analyzer = ActivityLogAnalyzer(ignored_directories=[])
        result = analyzer.analyze(Path(tmpdir))
        assert result.has_validation_history is True


def test_activity_analyzer_summary_capped_at_10():
    result = ActivityScanResult()
    analyzer = ActivityLogAnalyzer(ignored_directories=[])
    for i in range(15):
        analyzer._append_summary(result.summary, f"line {i}")
    assert len(result.summary) == 10


# ---------------------------------------------------------------------------
# 3. Prioritizer (4 tests)
# ---------------------------------------------------------------------------

def _make_task(project_id: str, priority: float = 0.5) -> TaskRecord:
    return TaskRecord(
        task_id=f"t_{project_id}",
        project_id=project_id,
        title="test",
        task_type="verification",
        source="test",
        priority=priority,
        risk="medium",
        expected_runtime_min=5,
        expected_context_cost="low",
        required_verification=["build"],
    )


def _make_project(project_id: str, **kwargs) -> ProjectRecord:
    defaults = dict(
        project_id=project_id,
        name=project_id,
        root_path=f"C:\\test\\{project_id}",
    )
    defaults.update(kwargs)
    return ProjectRecord(**defaults)


def test_prioritizer_browser_and_numeric_bonus():
    """Browser project gets +0.15, numeric project gets +0.2."""
    t1 = _make_task("browser")
    p1 = _make_project("browser", browser_test_commands=["npx playwright test"])
    Prioritizer().reprioritize([t1], {"browser": p1})
    assert t1.priority >= 0.65  # base 0.5 + 0.15

    t2 = _make_task("numeric")
    p2 = _make_project("numeric", has_numeric_logic=True)
    Prioritizer().reprioritize([t2], {"numeric": p2})
    assert t2.priority >= 0.70  # base 0.5 + 0.2


def test_prioritizer_math_bonus():
    task = _make_task("p1")
    project = _make_project("p1", has_advanced_math=True, advanced_math_score=8)
    Prioritizer().reprioritize([task], {"p1": project})
    # math bonus = min(8/40, 0.2) = 0.2; base 0.5 + 0.2 = 0.7
    assert task.priority >= 0.70


def test_prioritizer_caps_at_099():
    task = _make_task("p1")
    project = _make_project(
        "p1",
        browser_test_commands=["x"],
        has_numeric_logic=True,
        has_advanced_math=True,
        advanced_math_score=40,
        analysis_risk_factors=["a"] * 40,
    )
    Prioritizer().reprioritize([task], {"p1": project})
    assert task.priority <= 0.99


def test_prioritizer_returns_sorted_descending():
    t1 = _make_task("p1")
    t2 = _make_task("p2")
    p1 = _make_project("p1")
    p2 = _make_project("p2", has_numeric_logic=True, browser_test_commands=["x"])
    result = Prioritizer().reprioritize([t1, t2], {"p1": p1, "p2": p2})
    assert result[0].priority >= result[1].priority


# ---------------------------------------------------------------------------
# 4. Task Models (4 tests)
# ---------------------------------------------------------------------------

def test_build_baseline_task_includes_test_check():
    project = _make_project("p1", test_commands=["pytest tests/ -q"])
    task = build_baseline_task(project)
    assert "relevant_tests" in task.required_verification


def test_build_baseline_task_sets_risk():
    project = _make_project("p1", risk_profile="high")
    task = build_baseline_task(project)
    assert task.risk == "high"


def test_build_test_first_tasks_returns_two_with_chain():
    project = _make_project("p1", test_commands=["pytest"])
    tasks = build_test_first_tasks(project)
    assert len(tasks) == 2
    assert tasks[1].blocked_by == [tasks[0].task_id]


def test_build_test_first_tasks_first_is_test_writing():
    project = _make_project("p1")
    tasks = build_test_first_tasks(project)
    assert tasks[0].task_type == "test_writing"


# ---------------------------------------------------------------------------
# 5. Memory Insights (3 tests)
# ---------------------------------------------------------------------------

def test_loop_detected_creates_orchestration_insight():
    evidence = SessionEvidence(
        task_id="t1", runner_id="r1", state="running",
        risks=[], next_action="wait", required_proof=[],
        loop_detected=True,
    )
    insights = InsightEngine().extract([evidence], [])
    assert len(insights) == 1
    assert insights[0].scope == "orchestration"


def test_proof_gap_and_verification_failure_create_verification_insights():
    """Both proof_gap evidence and failed verification produce verification-scope insights."""
    evidence = SessionEvidence(
        task_id="t1", runner_id="r1", state="running",
        risks=[], next_action="wait", required_proof=[],
        proof_gap=True,
    )
    gap_insights = InsightEngine().extract([evidence], [])
    assert len(gap_insights) == 1
    assert gap_insights[0].scope == "verification"

    vr = VerificationResult(
        task_id="t2", success=False,
        required_checks=["build"], completed_checks=[], skipped_checks=[],
        details=["build failed"],
    )
    fail_insights = InsightEngine().extract([], [vr])
    assert len(fail_insights) == 1
    assert fail_insights[0].scope == "verification"


def test_insight_confidence_values_reasonable():
    evidence = SessionEvidence(
        task_id="t1", runner_id="r1", state="running",
        risks=[], next_action="wait", required_proof=[],
        loop_detected=True, proof_gap=True,
    )
    vr = VerificationResult(
        task_id="t1", success=False,
        required_checks=["build"], completed_checks=[], skipped_checks=[],
        details=["failed"],
    )
    insights = InsightEngine().extract([evidence], [vr])
    for ins in insights:
        assert 0.5 <= ins.confidence <= 1.0


# ---------------------------------------------------------------------------
# 6. Heuristic Engine (3 tests)
# ---------------------------------------------------------------------------

def _make_memory(mid: str, scope: str, mtype: str, tags: list[str]) -> MemoryRecord:
    return MemoryRecord(
        memory_id=mid, memory_type=mtype, scope=scope,
        title=f"mem {mid}", content="content",
        tags=tags, confidence=0.6,
    )


def test_heuristic_engine_generates_from_3_same_scope():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = StateDatabase(Path(tmpdir) / "test.db")
        for i in range(4):
            db.upsert_memory(_make_memory(
                f"m{i}", "projectA", "task_pattern", ["flaky_test"]
            ))
        engine = HeuristicEngine(db)
        heuristics = engine.generate()
        assert len(heuristics) >= 1
        assert heuristics[0].memory_type == "heuristic"
        db.close()


def test_heuristic_engine_requires_min_count_and_no_duplicates():
    """Does NOT generate with only 2 memories; does NOT duplicate existing heuristics."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = StateDatabase(Path(tmpdir) / "test.db")
        # Only 2 memories -> should not generate
        for i in range(2):
            db.upsert_memory(_make_memory(
                f"m{i}", "projectB", "task_pattern", ["rare_tag"]
            ))
        engine = HeuristicEngine(db)
        assert engine.generate() == []

        # Now add enough for a different scope and generate once
        for i in range(4):
            db.upsert_memory(_make_memory(
                f"dup{i}", "projectC", "task_pattern", ["dup_tag"]
            ))
        first = engine.generate()
        assert len(first) >= 1
        # Second call should not duplicate
        second = engine.generate()
        assert len(second) == 0
        db.close()


def test_heuristic_has_linked_memories():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = StateDatabase(Path(tmpdir) / "test.db")
        for i in range(4):
            db.upsert_memory(_make_memory(
                f"m{i}", "projectD", "task_pattern", ["link_tag"]
            ))
        engine = HeuristicEngine(db)
        heuristics = engine.generate()
        assert len(heuristics) >= 1
        assert len(heuristics[0].linked_memories) > 0
        db.close()


# ---------------------------------------------------------------------------
# 7. Quota Tracker (3 tests)
# ---------------------------------------------------------------------------

def test_quota_tracker_detects_known_rate_limit_patterns():
    """Detects 'rate limit', 'usage limit', and 'too many people' (Gemini)."""
    qt = QuotaTracker()
    assert qt.detect_rate_limit(["Error: rate limit exceeded"]) is True
    assert qt.detect_rate_limit(["usage limit reached, try later"]) is True
    assert qt.detect_rate_limit(["too many people using this model right now"]) is True


def test_quota_tracker_ignores_normal_output():
    qt = QuotaTracker()
    assert qt.detect_rate_limit(["All 42 tests passed", "Build complete"]) is False


def test_quota_tracker_cooldown_active():
    qt = QuotaTracker(cooldown_minutes=30)
    recent = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    assert qt.cooldown_active("limited", recent) is True
    old = (datetime.now(UTC) - timedelta(minutes=60)).isoformat()
    assert qt.cooldown_active("limited", old) is False
    assert qt.cooldown_active("normal", recent) is False
