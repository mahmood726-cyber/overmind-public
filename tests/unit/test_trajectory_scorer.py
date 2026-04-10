"""Tests for TrajectoryScorer completion probability estimation."""

from __future__ import annotations

from overmind.storage.models import EvidenceEvent, SessionEvidence
from overmind.verification.trajectory_scorer import TrajectoryScorer


def _make_evidence(**kwargs) -> SessionEvidence:
    defaults = {
        "task_id": "task-1",
        "runner_id": "claude_main",
        "state": "VERIFYING",
        "risks": [],
        "next_action": "verify",
        "required_proof": [],
        "events": [],
        "last_commands": [],
        "output_excerpt": [],
        "loop_detected": False,
        "proof_gap": False,
        "exited": True,
        "exit_code": 0,
    }
    defaults.update(kwargs)
    return SessionEvidence(**defaults)


def test_clean_exit_with_tests_passed_scores_high():
    scorer = TrajectoryScorer()
    evidence = _make_evidence(
        events=[EvidenceEvent(kind="tests_passed", line="42 tests passed")],
    )
    score = scorer.score(evidence)
    assert score.completion_probability >= 0.8
    assert score.recommendation in ("verify", "skip_verify")
    assert "tests_passed" in score.signals
    assert "clean_exit" in score.signals


def test_error_exit_scores_low():
    scorer = TrajectoryScorer()
    evidence = _make_evidence(exit_code=1)
    score = scorer.score(evidence)
    assert score.completion_probability < 0.4
    assert score.recommendation == "retry"


def test_loop_detected_reduces_score():
    scorer = TrajectoryScorer()
    evidence = _make_evidence(loop_detected=True)
    score = scorer.score(evidence)
    assert score.signals.get("loop_detected", 0) < 0
    assert score.completion_probability <= 0.7


def test_proof_gap_reduces_score():
    scorer = TrajectoryScorer()
    evidence = _make_evidence(proof_gap=True)
    score = scorer.score(evidence)
    assert score.signals.get("proof_gap", 0) < 0


def test_rate_limited_reduces_score():
    scorer = TrajectoryScorer()
    evidence = _make_evidence(
        events=[EvidenceEvent(kind="rate_limited", line="Rate limit exceeded")],
    )
    score = scorer.score(evidence)
    assert score.signals.get("rate_limited", 0) < 0


def test_build_passed_boosts_score():
    scorer = TrajectoryScorer()
    evidence = _make_evidence(
        events=[EvidenceEvent(kind="build_passed", line="Build succeeded")],
    )
    score = scorer.score(evidence)
    assert score.signals.get("build_passed", 0) > 0


def test_many_risks_reduces_score():
    scorer = TrajectoryScorer()
    evidence = _make_evidence(
        risks=["risk1", "risk2", "risk3"],
    )
    score = scorer.score(evidence)
    assert score.signals.get("high_risk_count", 0) < 0


def test_short_transcript_reduces_score():
    scorer = TrajectoryScorer()
    evidence = _make_evidence()
    score = scorer.score(evidence, transcript_lines=["line1", "line2"])
    assert score.signals.get("very_short_transcript", 0) < 0


def test_skip_verify_recommendation():
    """Perfect session should recommend skip_verify."""
    scorer = TrajectoryScorer()
    evidence = _make_evidence(
        events=[
            EvidenceEvent(kind="build_passed", line="Build ok"),
            EvidenceEvent(kind="tests_passed", line="All 100 tests passed"),
        ],
    )
    score = scorer.score(evidence, transcript_lines=["line"] * 50)
    assert score.completion_probability >= 0.85
    assert score.recommendation == "skip_verify"


def test_probability_clamped_to_0_1():
    scorer = TrajectoryScorer()
    # Worst case: everything negative
    evidence = _make_evidence(
        exit_code=1,
        loop_detected=True,
        proof_gap=True,
        risks=["a", "b", "c"],
        events=[
            EvidenceEvent(kind="tests_failed", line="FAILED"),
            EvidenceEvent(kind="build_failed", line="Build error"),
            EvidenceEvent(kind="rate_limited", line="Rate limit"),
        ],
    )
    score = scorer.score(evidence, transcript_lines=["x"])
    assert 0.0 <= score.completion_probability <= 1.0


def test_custom_thresholds():
    """Custom thresholds change recommendation boundaries."""
    # With very high skip_threshold, even good sessions stay at "verify"
    scorer = TrajectoryScorer(verify_threshold=0.6, skip_threshold=1.1)
    evidence = _make_evidence()
    score = scorer.score(evidence)
    assert score.recommendation == "verify"  # can't reach 1.1

    # With high verify_threshold, error-exit sessions get "retry"
    scorer2 = TrajectoryScorer(verify_threshold=0.5, skip_threshold=0.95)
    evidence2 = _make_evidence(exit_code=1)  # error exit → ~0.35
    score2 = scorer2.score(evidence2)
    assert score2.recommendation == "retry"  # 0.35 < 0.5
