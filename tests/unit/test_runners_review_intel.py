"""Tests for runners, review, and intelligence modules.

20 tests covering:
- Runner Registry: adapter_for, _command_name
- Base Runner Adapter: build_record, preferred_tasks
- Review Finding: parse_review_output, compute_consensus, _similar
- Review Personas: personas_for_project, sorting
- Daily Report: _portfolio_summary, _priority_queue, _daily_targets, _benchmark_tracking
- Session Miner: JSONL parsing, message counting, error detection
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from overmind.config import AppConfig, RunnerDefinition, PoliciesConfig, RootsConfig
from overmind.review.finding import (
    PersonaReviewResult,
    ReviewFinding,
    _similar,
    compute_consensus,
    parse_review_output,
)
from overmind.review.personas import personas_for_project
from overmind.runners.base import BaseRunnerAdapter
from overmind.runners.claude_runner import ClaudeRunnerAdapter
from overmind.runners.codex_runner import CodexRunnerAdapter
from overmind.runners.gemini_runner import GeminiRunnerAdapter
from overmind.runners.runner_registry import RunnerRegistry, _command_name
from overmind.intelligence.daily_report import DailyReport
from overmind.intelligence.session_miner import SessionMiner
from overmind.storage.db import StateDatabase
from overmind.storage.models import MemoryRecord, ProjectRecord, RunnerRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(tmp_path, runner_defs=None):
    """Build a minimal AppConfig with optional runner definitions."""
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    runners = runner_defs or []
    return AppConfig(
        config_dir=config_dir,
        data_dir=data_dir,
        db_path=data_dir / "state.db",
        roots=RootsConfig(),
        runners=runners,
        policies=PoliciesConfig(),
        ignored_directories=[],
        ignored_file_suffixes=[],
        verification_profiles={},
        verification_rules=[],
    )


def _make_definition(runner_id="claude_a", runner_type="claude", command="claude -p"):
    return RunnerDefinition(
        runner_id=runner_id,
        type=runner_type,
        mode="interactive",
        command=command,
        environment="windows",
    )


def _make_project(project_id="p1", name="TestProj", risk="medium", math=False,
                   math_score=0, test_cmds=None, oracle=False, validation=False):
    return ProjectRecord(
        project_id=project_id,
        name=name,
        root_path=f"C:\\{name}",
        risk_profile=risk,
        has_advanced_math=math,
        advanced_math_score=math_score,
        test_commands=test_cmds or [],
        has_oracle_benchmarks=oracle,
        has_validation_history=validation,
    )


# ===========================================================================
# 1. Runner Registry — adapter_for returns correct adapter type
# ===========================================================================

def test_adapter_for_returns_correct_adapter_type(tmp_path):
    defs = [
        _make_definition("claude_a", "claude", "claude -p"),
        _make_definition("codex_b", "codex", "codex -p"),
        _make_definition("gemini_c", "gemini", "gemini -p"),
    ]
    config = _make_config(tmp_path, runner_defs=defs)
    config.ensure_directories()
    db = StateDatabase(config.db_path)
    try:
        registry = RunnerRegistry(config=config, db=db)
        assert isinstance(registry.adapter_for("claude_a"), ClaudeRunnerAdapter)
        assert isinstance(registry.adapter_for("codex_b"), CodexRunnerAdapter)
        assert isinstance(registry.adapter_for("gemini_c"), GeminiRunnerAdapter)
    finally:
        db.close()


# ===========================================================================
# 2. Runner Registry — adapter_for returns None for unknown runner_id
# ===========================================================================

def test_adapter_for_returns_none_for_unknown(tmp_path):
    config = _make_config(tmp_path, runner_defs=[_make_definition()])
    config.ensure_directories()
    db = StateDatabase(config.db_path)
    try:
        registry = RunnerRegistry(config=config, db=db)
        assert registry.adapter_for("nonexistent_runner") is None
    finally:
        db.close()


# ===========================================================================
# 3. Runner Registry — _command_name extracts executable from quoted path
# ===========================================================================

def test_command_name_extracts_from_quoted_path():
    result = _command_name('"C:\\Program Files\\tool.exe" --flag')
    assert result == "C:\\Program Files\\tool.exe"


# ===========================================================================
# 4. Runner Registry — _command_name extracts from simple command
# ===========================================================================

def test_command_name_extracts_from_simple_command():
    assert _command_name("python -m pytest") == "python"
    assert _command_name("claude") == "claude"
    assert _command_name("  npm run test") == "npm"


# ===========================================================================
# 5. Base Runner Adapter — build_record creates RunnerRecord when no previous
# ===========================================================================

def test_build_record_creates_record_without_previous():
    defn = _make_definition("runner1", "claude", "claude -p")
    adapter = BaseRunnerAdapter(definition=defn)
    record = adapter.build_record(previous=None, available=True, reason=None)

    assert isinstance(record, RunnerRecord)
    assert record.runner_id == "runner1"
    assert record.runner_type == "claude"
    assert record.available is True
    assert record.unavailability_reason is None
    assert record.preferred_tasks == []
    assert record.avg_latency_sec == 0.0
    assert record.success_rate_7d == 0.5


# ===========================================================================
# 6. Base Runner Adapter — build_record preserves stats from previous record
# ===========================================================================

def test_build_record_preserves_previous_stats():
    defn = _make_definition("runner1", "claude", "claude -p")
    adapter = BaseRunnerAdapter(definition=defn)

    previous = RunnerRecord(
        runner_id="runner1",
        runner_type="claude",
        environment="windows",
        command="claude -p",
        status="BUSY",
        health="degraded",
        avg_latency_sec=3.5,
        success_rate_7d=0.85,
        failure_rate_7d=0.15,
        quota_state="limited",
        preferred_tasks=["focused_fix", "verification"],
    )
    record = adapter.build_record(previous=previous, available=True, reason=None)

    assert record.avg_latency_sec == 3.5
    assert record.success_rate_7d == 0.85
    assert record.failure_rate_7d == 0.15
    assert record.quota_state == "limited"
    assert record.preferred_tasks == ["focused_fix", "verification"]
    assert record.status == "BUSY"  # preserved from previous


# ===========================================================================
# 7. Base Runner Adapter — preferred_tasks returns routing strengths
# ===========================================================================

def test_preferred_tasks_returns_routing_strengths():
    defn = _make_definition()
    adapter = BaseRunnerAdapter(definition=defn)
    strengths = ["verification", "focused_fix", "review"]
    result = adapter.preferred_tasks(strengths)
    assert result == ["verification", "focused_fix", "review"]


# ===========================================================================
# 8. Review Finding — parse_review_output extracts P0 finding with file loc
# ===========================================================================

def test_parse_extracts_p0_with_file_location():
    raw = (
        "FINDINGS:\n"
        "- [P0] Buffer overflow in parser (main.py:99)\n"
        "VERDICT: BLOCK"
    )
    result = parse_review_output("security", raw)
    assert len(result.findings) == 1
    f = result.findings[0]
    assert f.severity == "P0"
    assert f.description == "Buffer overflow in parser"
    assert f.file_location == "main.py:99"
    assert f.persona == "security"


# ===========================================================================
# 9. Review Finding — parse_review_output extracts PASS verdict
# ===========================================================================

def test_parse_extracts_pass_verdict():
    raw = "All good.\nVERDICT: PASS"
    result = parse_review_output("efficiency", raw)
    assert result.verdict == "PASS"
    assert result.findings == []


# ===========================================================================
# 10. Review Finding — defaults to CONCERNS when no verdict
# ===========================================================================

def test_parse_defaults_to_concerns_when_no_verdict():
    raw = "- [P1] Minor issue in logging\nNo explicit verdict here."
    result = parse_review_output("robustness", raw)
    assert result.verdict == "CONCERNS"
    assert len(result.findings) == 1


# ===========================================================================
# 11. Review Finding — compute_consensus PASS when all pass
# ===========================================================================

def test_consensus_pass_when_all_pass():
    results = [
        PersonaReviewResult(persona="correctness", verdict="PASS", findings=[]),
        PersonaReviewResult(persona="efficiency", verdict="PASS", findings=[]),
        PersonaReviewResult(persona="security", verdict="PASS", findings=[]),
    ]
    consensus = compute_consensus(results)
    assert consensus.overall_verdict == "PASS"
    assert consensus.p0_count == 0
    assert consensus.p1_count == 0
    assert consensus.p2_count == 0


# ===========================================================================
# 12. Review Finding — compute_consensus BLOCK when any BLOCK
# ===========================================================================

def test_consensus_block_when_any_block():
    results = [
        PersonaReviewResult(persona="correctness", verdict="PASS", findings=[]),
        PersonaReviewResult(
            persona="security",
            verdict="BLOCK",
            findings=[ReviewFinding("security", "P0", "SQL injection")],
        ),
    ]
    consensus = compute_consensus(results)
    assert consensus.overall_verdict == "BLOCK"


# ===========================================================================
# 13. Review Finding — _similar returns True for similar descriptions
# ===========================================================================

def test_similar_returns_true_for_overlapping_descriptions():
    assert _similar("missing error handling for empty input", "no error handling for empty input") is True
    assert _similar("division by zero in parser", "division by zero in the parser module") is True


# ===========================================================================
# 14. Review Finding — _similar returns False for different descriptions
# ===========================================================================

def test_similar_returns_false_for_different_descriptions():
    assert _similar("missing error handling for empty input", "SQL injection in login form") is False
    assert _similar("buffer overflow", "incorrect rounding behavior") is False


# ===========================================================================
# 15. Review Personas — returns correctness + efficiency for low-risk
# ===========================================================================

def test_personas_low_risk_returns_correctness_and_efficiency():
    personas = personas_for_project(has_advanced_math=False, risk_profile="low")
    names = [p.name for p in personas]
    assert names == ["correctness", "efficiency"]


# ===========================================================================
# 16. Review Personas — returns all 5 for high-risk math
# ===========================================================================

def test_personas_high_risk_math_returns_all_five():
    personas = personas_for_project(has_advanced_math=True, risk_profile="high")
    names = [p.name for p in personas]
    assert len(personas) == 5
    assert "correctness" in names
    assert "statistical_rigor" in names
    assert "security" in names
    assert "robustness" in names
    assert "efficiency" in names


# ===========================================================================
# 17. Review Personas — sorted by priority
# ===========================================================================

def test_personas_sorted_by_priority():
    personas = personas_for_project(has_advanced_math=True, risk_profile="high")
    priorities = [p.priority for p in personas]
    assert priorities == sorted(priorities)
    assert personas[0].name == "correctness"   # priority 1
    assert personas[-1].name == "efficiency"    # priority 5


# ===========================================================================
# 18. Daily Report — _portfolio_summary counts projects correctly
# ===========================================================================

def test_portfolio_summary_counts_projects(tmp_path):
    config = _make_config(tmp_path)
    config.ensure_directories()
    db = StateDatabase(config.db_path)
    try:
        report = DailyReport(db=db, artifacts_dir=tmp_path / "artifacts")
        projects = [
            _make_project("p1", "Proj1", risk="high", math=True, test_cmds=["pytest"]),
            _make_project("p2", "Proj2", risk="medium", math=False, test_cmds=["npm test"]),
            _make_project("p3", "Proj3", risk="low", math=True),
        ]
        summary = report._portfolio_summary(projects, [])

        assert summary["total_projects"] == 3
        assert summary["with_advanced_math"] == 2
        assert summary["with_test_commands"] == 2
        assert summary["by_risk"]["high"] == 1
        assert summary["by_risk"]["medium"] == 1
        assert summary["by_risk"]["low"] == 1
    finally:
        db.close()


# ===========================================================================
# 19. Daily Report — _priority_queue sorts by priority score
# ===========================================================================

def test_priority_queue_sorts_by_score(tmp_path):
    config = _make_config(tmp_path)
    config.ensure_directories()
    db = StateDatabase(config.db_path)
    try:
        report = DailyReport(db=db, artifacts_dir=tmp_path / "artifacts")
        projects = [
            _make_project("p1", "LowPriority", risk="low", math_score=1, test_cmds=["pytest"]),
            _make_project("p2", "HighPriority", risk="high", math_score=8, test_cmds=["pytest"],
                          oracle=True, validation=True),
            _make_project("p3", "MedPriority", risk="medium_high", math_score=5, test_cmds=["pytest"]),
        ]
        queue = report._priority_queue(projects, [])

        assert len(queue) == 3
        assert queue[0]["name"] == "HighPriority"
        assert queue[-1]["name"] == "LowPriority"
        # Verify descending priority scores
        scores = [item["priority_score"] for item in queue]
        assert scores == sorted(scores, reverse=True)
    finally:
        db.close()


# ===========================================================================
# 20. Daily Report — _daily_targets suggests fixing regressions first
# ===========================================================================

def test_daily_targets_fixes_regressions_first(tmp_path):
    config = _make_config(tmp_path)
    config.ensure_directories()
    db = StateDatabase(config.db_path)
    try:
        report = DailyReport(db=db, artifacts_dir=tmp_path / "artifacts")
        fake_report = {
            "verification_coverage": {
                "coverage_percent": 25.0,
                "verified_count": 5,
                "total_testable": 20,
            },
            "regressions": {"active_regressions": 3},
            "priority_queue": [{"name": "ProjA", "priority_score": 15}],
        }
        targets = report._daily_targets(fake_report)

        assert any("FIX 3 active regression" in a for a in targets["actions"])
        # Regressions come before other suggestions
        assert targets["actions"][0].startswith("FIX")
    finally:
        db.close()


# ===========================================================================
# 21. Daily Report — _benchmark_tracking computes coverage percent
# ===========================================================================

def test_benchmark_tracking_coverage_percent(tmp_path):
    config = _make_config(tmp_path)
    config.ensure_directories()
    db = StateDatabase(config.db_path)
    try:
        report = DailyReport(db=db, artifacts_dir=tmp_path / "artifacts")
        projects = [
            _make_project("p1", "A", test_cmds=["pytest"]),
            _make_project("p2", "B", test_cmds=["pytest"]),
            _make_project("p3", "C", test_cmds=["pytest"]),
            _make_project("p4", "D"),  # no test commands
        ]
        # 1 out of 3 testable verified
        memories = [
            MemoryRecord(memory_id="m1", memory_type="project_learning", scope="p1",
                         title="learned", content="content"),
        ]
        scores = []
        bm = report._benchmark_tracking(projects, memories, scores)

        # 1 verified / 3 testable = 33.3%
        assert bm["coverage_percent"] == 33.3
        assert bm["projects_verified"] == 1
        assert bm["projects_testable"] == 3
    finally:
        db.close()


# ===========================================================================
# 22. Session Miner — parses a simple JSONL session file
# ===========================================================================

def test_session_miner_parses_jsonl(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()

    lines = [
        json.dumps({"type": "user", "message": {"content": "Hello"}}),
        json.dumps({"type": "assistant", "message": {"role": "assistant", "content": "Hi there"}}),
        json.dumps({"type": "user", "message": {"content": "Run tests"}}),
    ]
    (sessions_dir / "session1.jsonl").write_text("\n".join(lines), encoding="utf-8")

    db = StateDatabase(tmp_path / "miner.db")
    try:
        miner = SessionMiner(db=db, sessions_dir=sessions_dir)
        results = miner.mine_all(max_sessions=10)
        assert results["sessions_analyzed"] == 1
        assert results["total_messages"] == 3
    finally:
        db.close()


# ===========================================================================
# 23. Session Miner — counts user vs assistant messages
# ===========================================================================

def test_session_miner_counts_message_types(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()

    lines = [
        json.dumps({"type": "user", "message": {"content": "First"}}),
        json.dumps({"type": "user", "message": {"content": "Second"}}),
        json.dumps({"type": "assistant", "message": {"role": "assistant", "content": "Reply"}}),
    ]
    (sessions_dir / "s.jsonl").write_text("\n".join(lines), encoding="utf-8")

    db = StateDatabase(tmp_path / "miner.db")
    try:
        miner = SessionMiner(db=db, sessions_dir=sessions_dir)
        results = miner.mine_all(max_sessions=5)
        assert results["user_messages"] == 2
        assert results["assistant_messages"] == 1
    finally:
        db.close()


# ===========================================================================
# 24. Session Miner — detects error patterns in content
# ===========================================================================

def test_session_miner_detects_errors(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()

    lines = [
        json.dumps({"type": "user", "message": {"content": "got a TypeError in my code"}}),
        json.dumps({"type": "assistant", "message": {"role": "assistant",
                    "content": "That ModuleNotFoundError means you need to install the package"}}),
        json.dumps({"type": "user", "message": {"content": "all good now, 5 passed"}}),
    ]
    (sessions_dir / "errs.jsonl").write_text("\n".join(lines), encoding="utf-8")

    db = StateDatabase(tmp_path / "miner.db")
    try:
        miner = SessionMiner(db=db, sessions_dir=sessions_dir)
        results = miner.mine_all(max_sessions=5)

        assert results["failure_lines"] >= 2  # TypeError + ModuleNotFoundError lines
        assert results["success_lines"] >= 1  # "5 passed"
        assert "TypeError" in results["top_errors"] or "ModuleNotFoundError" in results["top_errors"]
    finally:
        db.close()
