"""AutoFixer: orchestrates safe auto-remediation after nightly diagnosis.

Safety rules:
1. NEVER modify source code (.py, .html, .js)
2. Only environmental fixes: pip install, baseline regen, git restore
3. Re-verify after every fix
4. NEVER auto-commit — fixes are logged, human reviews before pushing
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from overmind.diagnosis.judge import Diagnosis
from overmind.remediation.strategies import (
    BaselineDriftFix,
    DependencyRotFix,
    FixResult,
    MissingFixtureFix,
)


@dataclass
class RemediationResult:
    project_id: str
    diagnosis_type: str
    fix_attempted: bool
    fix_result: FixResult | None
    reverified: bool
    reverify_passed: bool
    committed: bool
    detail: str


# Failure types that are NEVER auto-fixable
NEVER_AUTO_FIX = {
    "FORMULA_ERROR",      # Needs human judgment
    "FLOAT_PRECISION",    # Needs human judgment
    "UNKNOWN",            # Can't diagnose → can't fix
}


class AutoFixer:
    def __init__(
        self,
        baselines_dir: Path,
        probes_dir: Path,
        dry_run: bool = False,
    ) -> None:
        self.dry_run = dry_run
        self.strategies = [
            DependencyRotFix(),
            BaselineDriftFix(baselines_dir, probes_dir),
            MissingFixtureFix(),
        ]

    def attempt_fix(
        self,
        diagnosis: Diagnosis,
        project_path: str,
        verify_fn=None,
    ) -> RemediationResult:
        """Attempt to auto-fix a diagnosed failure.

        Args:
            diagnosis: The Judge's diagnosis
            project_path: Path to the project root
            verify_fn: Optional callable(project_path) -> bool for re-verification
        """
        # Safety gate: never auto-fix certain types
        if diagnosis.failure_type in NEVER_AUTO_FIX:
            return RemediationResult(
                project_id=diagnosis.project_id,
                diagnosis_type=diagnosis.failure_type,
                fix_attempted=False,
                fix_result=None,
                reverified=False,
                reverify_passed=False,
                committed=False,
                detail=f"Auto-fix blocked: {diagnosis.failure_type} requires human review",
            )

        # Find a strategy that can handle this
        for strategy in self.strategies:
            if not strategy.can_fix(diagnosis):
                continue

            if self.dry_run:
                return RemediationResult(
                    project_id=diagnosis.project_id,
                    diagnosis_type=diagnosis.failure_type,
                    fix_attempted=False,
                    fix_result=None,
                    reverified=False,
                    reverify_passed=False,
                    committed=False,
                    detail=f"Dry run: would attempt {strategy.__class__.__name__}",
                )

            # Apply the fix
            fix_result = strategy.apply(diagnosis, project_path)

            if not fix_result.success:
                return RemediationResult(
                    project_id=diagnosis.project_id,
                    diagnosis_type=diagnosis.failure_type,
                    fix_attempted=True,
                    fix_result=fix_result,
                    reverified=False,
                    reverify_passed=False,
                    committed=False,
                    detail=f"Fix failed: {fix_result.detail}",
                )

            # Re-verify if we have a verify function
            reverified = False
            reverify_passed = False
            if verify_fn:
                reverified = True
                reverify_passed = verify_fn(project_path)

            return RemediationResult(
                project_id=diagnosis.project_id,
                diagnosis_type=diagnosis.failure_type,
                fix_attempted=True,
                fix_result=fix_result,
                reverified=reverified,
                reverify_passed=reverify_passed,
                committed=False,  # Never auto-commit — human reviews
                detail=f"Fixed: {fix_result.action_taken}" + (
                    f" | reverify={'PASS' if reverify_passed else 'FAIL'}" if reverified else ""
                ),
            )

        # No strategy matched
        return RemediationResult(
            project_id=diagnosis.project_id,
            diagnosis_type=diagnosis.failure_type,
            fix_attempted=False,
            fix_result=None,
            reverified=False,
            reverify_passed=False,
            committed=False,
            detail=f"No auto-fix strategy for {diagnosis.failure_type}",
        )

