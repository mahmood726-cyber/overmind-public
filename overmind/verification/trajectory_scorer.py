"""Trajectory scoring for session completion probability.

Inspired by SWE-RM: estimates whether a coding agent's session likely succeeded,
without running expensive verification.  Currently rule-based using extracted
evidence signals; designed so the scoring function can be swapped for an LLM
call when a public SWE-RM model becomes available.

Usage:
    scorer = TrajectoryScorer()
    score = scorer.score(evidence, transcript_lines)
    if score.recommendation == "skip_verify":
        # don't waste time running test suite
    elif score.recommendation == "verify":
        # proceed with VerificationEngine
"""

from __future__ import annotations

from dataclasses import dataclass, field

from overmind.storage.models import SessionEvidence


@dataclass(slots=True)
class TrajectoryScore:
    completion_probability: float  # 0.0–1.0
    signals: dict[str, float] = field(default_factory=dict)
    recommendation: str = "verify"  # "verify" | "skip_verify" | "retry"


# Thresholds
VERIFY_THRESHOLD = 0.4
SKIP_THRESHOLD = 0.85


class TrajectoryScorer:
    """Score a session trajectory for completion probability using evidence signals."""

    def __init__(
        self,
        verify_threshold: float = VERIFY_THRESHOLD,
        skip_threshold: float = SKIP_THRESHOLD,
    ) -> None:
        self.verify_threshold = verify_threshold
        self.skip_threshold = skip_threshold

    def score(
        self,
        evidence: SessionEvidence,
        transcript_lines: list[str] | None = None,
    ) -> TrajectoryScore:
        """Compute completion probability from evidence signals.

        Returns a TrajectoryScore with recommendation:
        - "retry":       probability < verify_threshold  → don't bother verifying
        - "verify":      verify_threshold ≤ p < skip_threshold → run verification
        - "skip_verify": probability ≥ skip_threshold → high confidence, fast-path
        """
        signals: dict[str, float] = {}

        # Signal: clean exit
        if evidence.exited and evidence.exit_code == 0:
            signals["clean_exit"] = 0.3
        elif evidence.exited and evidence.exit_code is not None:
            signals["error_exit"] = -0.4
        else:
            signals["still_running"] = -0.1

        # Signal: test evidence
        test_pass_events = [e for e in evidence.events if e.kind.endswith("passed")]
        test_fail_events = [e for e in evidence.events if e.kind.endswith("failed")]
        if test_pass_events and not test_fail_events:
            signals["tests_passed"] = 0.35
        elif test_fail_events:
            signals["tests_failed"] = -0.3
        elif test_pass_events and test_fail_events:
            signals["mixed_test_results"] = 0.05

        # Signal: no loop
        if evidence.loop_detected:
            signals["loop_detected"] = -0.3
        else:
            signals["no_loop"] = 0.05

        # Signal: proof gap
        if evidence.proof_gap:
            signals["proof_gap"] = -0.2
        else:
            signals["proof_present"] = 0.1

        # Signal: rate limiting
        if any(e.kind == "rate_limited" for e in evidence.events):
            signals["rate_limited"] = -0.15

        # Signal: build evidence
        build_pass = any(e.kind == "build_passed" for e in evidence.events)
        build_fail = any(e.kind == "build_failed" for e in evidence.events)
        if build_pass and not build_fail:
            signals["build_passed"] = 0.1
        elif build_fail:
            signals["build_failed"] = -0.2

        # Signal: transcript length (if provided)
        if transcript_lines is not None:
            line_count = len(transcript_lines)
            if line_count < 5:
                signals["very_short_transcript"] = -0.15
            elif line_count > 500:
                signals["long_transcript"] = -0.05  # may indicate struggle
            else:
                signals["normal_transcript_length"] = 0.05

        # Signal: risk count
        risk_count = len(evidence.risks)
        if risk_count == 0:
            signals["no_risks"] = 0.1
        elif risk_count >= 3:
            signals["high_risk_count"] = -0.15

        # Aggregate: clamp to [0, 1]
        base = 0.5
        raw = base + sum(signals.values())
        probability = max(0.0, min(1.0, raw))

        # Recommendation
        if probability < self.verify_threshold:
            recommendation = "retry"
        elif probability >= self.skip_threshold:
            recommendation = "skip_verify"
        else:
            recommendation = "verify"

        return TrajectoryScore(
            completion_probability=round(probability, 3),
            signals=signals,
            recommendation=recommendation,
        )
