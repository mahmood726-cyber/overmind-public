"""Judge agent: diagnoses failures from CertBundle witness results."""
from __future__ import annotations

import re
from dataclasses import dataclass

from overmind.storage.models import utc_now
from overmind.verification.cert_bundle import CertBundle
from overmind.verification.scope_lock import WitnessResult
from overmind.diagnosis.taxonomy import FAILURE_TYPES


@dataclass
class Diagnosis:
    project_id: str
    failure_type: str
    confidence: float
    summary: str
    evidence: list[str]
    recommended_action: str
    witness_type: str
    created_at: str


class PatternMatcher:
    """Matches witness stderr/stdout against failure taxonomy patterns."""

    def __init__(self) -> None:
        self._compiled: dict[str, dict[str, list[re.Pattern]]] = {}
        for ftype, info in FAILURE_TYPES.items():
            self._compiled[ftype] = {
                "stderr": [re.compile(p) for p in info.get("patterns_stderr", [])],
                "stdout": [re.compile(p) for p in info.get("patterns_stdout", [])],
            }

    def match(self, witness: WitnessResult) -> tuple[str, float, list[str]]:
        """Returns (failure_type, confidence, evidence_excerpts)."""
        # Priority order: check each type
        for ftype in ["DEPENDENCY_ROT", "NUMERICAL_DRIFT", "FLOAT_PRECISION",
                       "FORMULA_ERROR", "PLATFORM_COMPAT", "TIMEOUT",
                       "SYNTAX_ERROR", "MISSING_FIXTURE", "TEST_FAILURE"]:
            patterns = self._compiled[ftype]
            # Check stderr patterns
            for pattern in patterns["stderr"]:
                m = pattern.search(witness.stderr)
                if m:
                    excerpt = witness.stderr[max(0, m.start() - 20):m.end() + 80][:200]
                    return ftype, 0.9, [excerpt]
            # Check stdout patterns
            for pattern in patterns["stdout"]:
                m = pattern.search(witness.stdout)
                if m:
                    excerpt = witness.stdout[max(0, m.start() - 20):m.end() + 80][:200]
                    return ftype, 0.9, [excerpt]

        # Check for timeout by exit code
        if witness.exit_code == -1:
            return "TIMEOUT", 0.8, [witness.stderr[:200] or "exit code -1"]

        return "UNKNOWN", 0.3, [witness.stderr[:200] or witness.stdout[:200] or "no output"]


class Judge:
    """Diagnoses failures from CertBundle witness results."""

    def __init__(self) -> None:
        self.matcher = PatternMatcher()

    def diagnose(self, bundle: CertBundle) -> Diagnosis | None:
        """Diagnose a REJECT or FAIL bundle. Returns None for CERTIFIED/PASS."""
        if bundle.verdict in ("CERTIFIED", "PASS", "SKIP"):
            return None

        # Find the failing witness(es)
        failed_witnesses = [w for w in bundle.witness_results if w.verdict == "FAIL"]
        if not failed_witnesses:
            return None

        # Diagnose the first (most important) failing witness
        witness = failed_witnesses[0]
        failure_type, confidence, evidence = self.matcher.match(witness)

        # Check for FLAKY pattern in history (if provided)
        # For now, we detect flaky from witness results within this bundle
        # Full flaky detection requires wiki history — deferred

        info = FAILURE_TYPES.get(failure_type, FAILURE_TYPES["UNKNOWN"])

        # Build action string
        action = info["action_template"]
        # Try to extract module name for DEPENDENCY_ROT
        if failure_type == "DEPENDENCY_ROT":
            mod_match = re.search(r"No module named ['\"]?(\w[\w.]*)", witness.stderr)
            if mod_match:
                action = action.format(module=mod_match.group(1))
            else:
                action = action.replace("{module}", "the missing module")
        elif failure_type == "MISSING_FIXTURE":
            path_match = re.search(r"['\"]([^'\"]+)['\"]", witness.stderr)
            if path_match:
                action = action.format(path=path_match.group(1))
            else:
                action = action.replace("{path}", "the missing file")

        return Diagnosis(
            project_id=bundle.project_id,
            failure_type=failure_type,
            confidence=confidence,
            summary=f"{info['description']}: {evidence[0][:80]}",
            evidence=evidence,
            recommended_action=action,
            witness_type=witness.witness_type,
            created_at=utc_now(),
        )

    def diagnose_with_history(self, bundle: CertBundle, history: list[str]) -> Diagnosis | None:
        """Diagnose with flaky detection from verification history."""
        diag = self.diagnose(bundle)
        if diag is None:
            return None

        # Check for flaky pattern: alternating PASS/FAIL in recent history
        if len(history) >= 3:
            recent = history[-3:]
            passing = [v for v in recent if v in ("CERTIFIED", "PASS")]
            failing = [v for v in recent if v in ("REJECT", "FAIL")]
            if passing and failing:  # Mixed results = flaky
                diag = Diagnosis(
                    project_id=diag.project_id,
                    failure_type="FLAKY",
                    confidence=0.7,
                    summary=f"Intermittent: {', '.join(recent)} in last 3 runs",
                    evidence=diag.evidence,
                    recommended_action="Mark as flaky, increase timeout, or investigate race condition",
                    witness_type=diag.witness_type,
                    created_at=diag.created_at,
                )
        return diag
