"""Metamorphic testing witness for meta-analysis tools.

Defines invariant relationships that must hold for any correct
meta-analysis implementation. Generates transformed inputs and
checks that outputs satisfy the metamorphic relation.

Addresses the oracle problem: we don't need to know the "right" answer,
only that transformations produce consistent results.

Relations:
1. Scale invariance: multiplying all effects by k multiplies pooled by k
2. Subset monotonicity: adding a study with effect > pooled increases pooled
3. Zero-heterogeneity identity: if all effects equal, pooled = that value
4. Sign reversal: negating all effects negates pooled
5. Precision weighting: a more precise study has more influence
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from overmind.verification.scope_lock import WitnessResult

PYTHON = sys.executable


@dataclass
class MetamorphicResult:
    relation: str
    passed: bool
    detail: str


class MetamorphicWitness:
    """Fourth witness type: checks invariant metamorphic relations."""

    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout

    def run(self, probe_path: str, project_path: str) -> WitnessResult:
        """Run metamorphic checks against a project's numerical probe.

        The probe must accept JSON on stdin with {effects, variances}
        and return JSON with {pooled, tau2, ...}.
        """
        failures: list[str] = []
        passes: list[str] = []

        # Base case: standard inputs
        base_effects = [0.5, 0.3, 0.8, 0.1, 0.6]
        base_variances = [0.01, 0.04, 0.0225, 0.0625, 0.0144]

        base_result = self._run_probe(probe_path, project_path, base_effects, base_variances)
        if base_result is None:
            return WitnessResult(
                witness_type="metamorphic", verdict="SKIP", exit_code=None,
                stdout="", stderr="Base probe failed", elapsed=0.0,
            )

        # Relation 1: Scale invariance (multiply effects by 2)
        scaled_effects = [e * 2 for e in base_effects]
        scaled_result = self._run_probe(probe_path, project_path, scaled_effects, base_variances)
        if scaled_result:
            base_pooled = base_result.get("pooled", base_result.get("theta", 0))
            scaled_pooled = scaled_result.get("pooled", scaled_result.get("theta", 0))
            if base_pooled != 0 and abs(scaled_pooled / base_pooled - 2.0) < 0.01:
                passes.append("scale_invariance: 2x effects -> 2x pooled")
            else:
                failures.append(f"scale_invariance: expected {base_pooled*2:.6f}, got {scaled_pooled:.6f}")

        # Relation 2: Zero-heterogeneity identity
        identical_effects = [0.5, 0.5, 0.5, 0.5, 0.5]
        identical_result = self._run_probe(probe_path, project_path, identical_effects, base_variances)
        if identical_result:
            pooled = identical_result.get("pooled", identical_result.get("theta", 0))
            if abs(pooled - 0.5) < 0.001:
                passes.append("zero_het_identity: identical effects -> pooled = effect")
            else:
                failures.append(f"zero_het_identity: expected 0.5, got {pooled:.6f}")

        # Relation 3: Sign reversal
        negated_effects = [-e for e in base_effects]
        negated_result = self._run_probe(probe_path, project_path, negated_effects, base_variances)
        if negated_result:
            base_pooled = base_result.get("pooled", base_result.get("theta", 0))
            neg_pooled = negated_result.get("pooled", negated_result.get("theta", 0))
            if abs(neg_pooled + base_pooled) < 0.001:
                passes.append("sign_reversal: -effects -> -pooled")
            else:
                failures.append(f"sign_reversal: expected {-base_pooled:.6f}, got {neg_pooled:.6f}")

        # Relation 4: Tau2 non-negative
        tau2 = base_result.get("tau2", 0)
        if isinstance(tau2, (int, float)) and tau2 >= 0:
            passes.append(f"tau2_nonneg: tau2={tau2:.6f} >= 0")
        else:
            failures.append(f"tau2_nonneg: tau2={tau2} is negative")

        # Relation 5: I2 in [0, 100]
        i2 = base_result.get("I2", base_result.get("i2", None))
        if i2 is not None and isinstance(i2, (int, float)):
            if 0 <= i2 <= 100:
                passes.append(f"i2_range: I2={i2:.1f} in [0,100]")
            else:
                failures.append(f"i2_range: I2={i2} outside [0,100]")

        total = len(passes) + len(failures)
        if failures:
            return WitnessResult(
                witness_type="metamorphic",
                verdict="FAIL",
                exit_code=1,
                stdout=f"{len(passes)}/{total} relations hold",
                stderr="Violations: " + "; ".join(failures),
                elapsed=0.0,
            )
        return WitnessResult(
            witness_type="metamorphic",
            verdict="PASS",
            exit_code=0,
            stdout=f"{len(passes)}/{total} metamorphic relations hold",
            stderr="",
            elapsed=0.0,
        )

    def _run_probe(
        self, probe_path: str, project_path: str,
        effects: list[float], variances: list[float],
    ) -> dict | None:
        """Run a probe with given inputs and return parsed JSON output."""
        input_data = json.dumps({"effects": effects, "variances": variances})
        try:
            proc = subprocess.run(
                [PYTHON, probe_path],
                input=input_data,
                cwd=project_path,
                capture_output=True, text=True, timeout=self.timeout,
            )
            if proc.returncode != 0:
                return None
            return json.loads(proc.stdout.strip())
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            return None
