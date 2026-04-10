"""Compound multi-step judge pipeline.

Inspired by Haize Labs' Verdict: compose multiple LLM judge steps into a
pipeline with weights, veto power, and majority-vote aggregation.

Example pipeline:
    judge = CompoundJudge(steps=[
        JudgeStep("requirements", llm_judge, weight=1.0, veto_power=True),
        JudgeStep("regressions", regression_judge, weight=0.8),
        JudgeStep("code_quality", quality_judge, weight=0.5),
    ])
    verdict = judge.evaluate(task, project, verification_result, transcript)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from overmind.storage.models import ProjectRecord, TaskRecord, VerificationResult, utc_now
from overmind.verification.llm_judge import JudgeVerdict, LLMJudge


@dataclass(slots=True)
class JudgeStep:
    name: str
    judge: LLMJudge
    weight: float = 1.0
    veto_power: bool = False


@dataclass(slots=True)
class CompoundVerdict:
    passed: bool
    confidence: float
    step_verdicts: dict[str, JudgeVerdict] = field(default_factory=dict)
    vetoed_by: str | None = None
    reasoning: str = ""
    created_at: str = field(default_factory=utc_now)


class CompoundJudge:
    """Run multiple judge steps and aggregate into a single verdict."""

    def __init__(self, steps: list[JudgeStep]) -> None:
        if not steps:
            raise ValueError("CompoundJudge requires at least one JudgeStep")
        self.steps = steps

    def evaluate(
        self,
        task: TaskRecord,
        project: ProjectRecord,
        verification_result: VerificationResult,
        transcript_lines: list[str] | None = None,
    ) -> CompoundVerdict:
        step_verdicts: dict[str, JudgeVerdict] = {}

        for step in self.steps:
            verdict = step.judge.judge(
                task=task,
                project=project,
                verification_result=verification_result,
                transcript_lines=transcript_lines,
            )
            step_verdicts[step.name] = verdict

            # Veto: if a veto-power step fails, short-circuit
            if step.veto_power and not verdict.passed:
                return CompoundVerdict(
                    passed=False,
                    confidence=verdict.confidence,
                    step_verdicts=step_verdicts,
                    vetoed_by=step.name,
                    reasoning=f"Vetoed by '{step.name}': {verdict.reasoning}",
                )

        # Weighted aggregation
        passed, confidence, reasoning = self._aggregate(step_verdicts)
        return CompoundVerdict(
            passed=passed,
            confidence=confidence,
            step_verdicts=step_verdicts,
            reasoning=reasoning,
        )

    def _aggregate(
        self, step_verdicts: dict[str, JudgeVerdict]
    ) -> tuple[bool, float, str]:
        """Weighted majority vote with confidence aggregation."""
        total_weight = 0.0
        pass_weight = 0.0
        confidence_sum = 0.0

        for step in self.steps:
            verdict = step_verdicts.get(step.name)
            if verdict is None:
                continue
            total_weight += step.weight
            if verdict.passed:
                pass_weight += step.weight
            confidence_sum += verdict.confidence * step.weight

        if total_weight == 0:
            return True, 0.0, "No judge steps produced verdicts"

        pass_ratio = pass_weight / total_weight
        avg_confidence = confidence_sum / total_weight
        passed = pass_ratio > 0.5

        # Build reasoning summary
        parts: list[str] = []
        for step in self.steps:
            v = step_verdicts.get(step.name)
            if v:
                status = "PASS" if v.passed else "FAIL"
                parts.append(f"{step.name}={status}(conf={v.confidence:.2f})")
        reasoning = f"Aggregate: {'PASS' if passed else 'FAIL'} ({pass_ratio:.0%} pass weight). Steps: {', '.join(parts)}"

        return passed, round(avg_confidence, 3), reasoning
