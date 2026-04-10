from __future__ import annotations

from overmind.review.finding import (
    PersonaReviewResult,
    ReviewFinding,
    compute_consensus,
    parse_review_output,
)
from overmind.review.multi_persona import MultiPersonaReviewer
from overmind.review.personas import PERSONAS, personas_for_project
from overmind.storage.db import StateDatabase
from overmind.storage.models import ProjectRecord, TaskRecord


def test_personas_for_high_risk_math_project():
    personas = personas_for_project(has_advanced_math=True, risk_profile="high")
    names = [p.name for p in personas]
    assert "correctness" in names
    assert "statistical_rigor" in names
    assert "security" in names
    assert "robustness" in names
    assert "efficiency" in names


def test_personas_for_low_risk_simple_project():
    personas = personas_for_project(has_advanced_math=False, risk_profile="medium")
    names = [p.name for p in personas]
    assert "correctness" in names
    assert "efficiency" in names
    assert "statistical_rigor" not in names
    assert "security" not in names


def test_parse_review_output_extracts_findings():
    raw = """PERSONA: correctness
FINDINGS:
- [P0] Division by zero possible in tau2 computation (stats.py:42)
- [P1] Edge case: empty study list not handled
- [P2] Variable name unclear
VERDICT: BLOCK"""

    result = parse_review_output("correctness", raw)
    assert result.verdict == "BLOCK"
    assert len(result.findings) == 3
    assert result.findings[0].severity == "P0"
    assert result.findings[0].file_location == "stats.py:42"
    assert result.findings[1].severity == "P1"
    assert result.findings[2].severity == "P2"


def test_parse_review_output_handles_pass():
    raw = """PERSONA: security
FINDINGS:
VERDICT: PASS"""

    result = parse_review_output("security", raw)
    assert result.verdict == "PASS"
    assert len(result.findings) == 0


def test_consensus_blocks_on_p0():
    results = [
        PersonaReviewResult(
            persona="correctness",
            verdict="BLOCK",
            findings=[ReviewFinding("correctness", "P0", "Critical bug")],
        ),
        PersonaReviewResult(
            persona="security",
            verdict="PASS",
            findings=[],
        ),
    ]
    consensus = compute_consensus(results)
    assert consensus.overall_verdict == "BLOCK"
    assert consensus.p0_count == 1


def test_consensus_boosts_severity_on_agreement():
    results = [
        PersonaReviewResult(
            persona="correctness",
            verdict="CONCERNS",
            findings=[ReviewFinding("correctness", "P1", "missing error handling for empty input")],
        ),
        PersonaReviewResult(
            persona="robustness",
            verdict="CONCERNS",
            findings=[ReviewFinding("robustness", "P1", "no error handling for empty input")],
        ),
    ]
    consensus = compute_consensus(results)
    # Two personas agreed on similar finding → should boost from P1 to P0
    assert consensus.consensus_findings[0]["agreed_by"] >= 2
    assert consensus.consensus_findings[0]["severity"] == "P0"


def test_consensus_passes_when_all_pass():
    results = [
        PersonaReviewResult(persona="correctness", verdict="PASS", findings=[]),
        PersonaReviewResult(persona="efficiency", verdict="PASS", findings=[]),
    ]
    consensus = compute_consensus(results)
    assert consensus.overall_verdict == "PASS"
    assert consensus.p0_count == 0
    assert consensus.p1_count == 0


def test_cross_model_dispatch_avoids_same_runner():
    reviewer = MultiPersonaReviewer.__new__(MultiPersonaReviewer)
    persona = PERSONAS[0]  # correctness, prefers claude

    # If writer was claude, reviewer should NOT be claude
    runner = reviewer.preferred_runner_for(persona, writer_runner_type="claude")
    assert runner != "claude"

    # If writer was codex, claude is fine
    runner = reviewer.preferred_runner_for(persona, writer_runner_type="codex")
    assert runner == "claude"


def test_build_review_prompt_renders_template(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    try:
        reviewer = MultiPersonaReviewer(db)
        project = ProjectRecord(
            project_id="test-proj",
            name="Test Project",
            root_path="C:\\test",
            project_type="python_tool",
            stack=["python"],
            has_advanced_math=True,
            advanced_math_signals=["meta_analysis", "bayesian_modeling"],
        )
        task = TaskRecord(
            task_id="t1",
            project_id="test-proj",
            title="Fix bootstrap convergence",
            task_type="focused_fix",
            source="test",
            priority=0.9,
            risk="high",
            expected_runtime_min=5,
            expected_context_cost="medium",
            required_verification=["relevant_tests"],
        )
        prompt = reviewer.build_review_prompt(
            PERSONAS[1],  # statistical_rigor
            project,
            task,
            changes_summary="Modified bootstrap CI computation",
        )
        assert "STATISTICAL RIGOR" in prompt
        assert "Test Project" in prompt
        assert "meta_analysis" in prompt
    finally:
        db.close()


def test_store_review_memory(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    reviewer = MultiPersonaReviewer(db)
    try:
        consensus = compute_consensus([
            PersonaReviewResult(
                persona="correctness",
                verdict="CONCERNS",
                findings=[ReviewFinding("correctness", "P1", "Edge case missing")],
            ),
        ])
        reviewer.store_review_memory("proj-1", "task-1", consensus, tick=5)

        memories = db.list_memories(scope="proj-1", memory_type="decision")
        assert len(memories) == 1
        assert "Review:" in memories[0].title
        assert "CONCERNS" in memories[0].title
    finally:
        db.close()
