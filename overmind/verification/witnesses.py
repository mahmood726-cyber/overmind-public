"""Three witness types for TruthCert multi-witness verification."""
from __future__ import annotations

import json
import subprocess
import sys
import time

from overmind.subprocess_utils import split_command, validate_command_prefix
from overmind.verification.scope_lock import WitnessResult

PYTHON_EXE = sys.executable


class SuiteWitness:
    def __init__(self, timeout: int = 120) -> None:
        self.timeout = timeout

    def run(self, command: str, cwd: str) -> WitnessResult:
        start = time.time()
        try:
            proc = subprocess.run(
                split_command(command), cwd=cwd, shell=False,
                capture_output=True, text=True, timeout=self.timeout,
            )
            elapsed = time.time() - start
            verdict = "PASS" if proc.returncode == 0 else "FAIL"
            return WitnessResult(
                witness_type="test_suite", verdict=verdict,
                exit_code=proc.returncode,
                stdout=proc.stdout[-2000:], stderr=proc.stderr[-2000:],
                elapsed=round(elapsed, 2),
            )
        except subprocess.TimeoutExpired:
            return WitnessResult(
                witness_type="test_suite", verdict="FAIL", exit_code=-1,
                stdout="", stderr=f"Timed out after {self.timeout}s",
                elapsed=round(time.time() - start, 2),
            )
        except OSError as exc:
            return WitnessResult(
                witness_type="test_suite", verdict="FAIL", exit_code=-1,
                stdout="", stderr=f"Failed to start: {exc}",
                elapsed=round(time.time() - start, 2),
            )


class SmokeWitness:
    def __init__(self, timeout: int = 10) -> None:
        self.timeout = timeout

    def run(self, modules: list[str], cwd: str) -> WitnessResult:
        if not modules:
            return WitnessResult(
                witness_type="smoke", verdict="SKIP", exit_code=None,
                stdout="", stderr="No modules to check", elapsed=0.0,
            )
        start = time.time()
        failures: list[str] = []
        for module in modules:
            try:
                proc = subprocess.run(
                    [PYTHON_EXE, "-c", f"import {module}"],
                    cwd=cwd, capture_output=True, text=True,
                    timeout=self.timeout,
                )
                if proc.returncode != 0:
                    failures.append(f"{module}: {proc.stderr.strip()[-200:]}")
            except subprocess.TimeoutExpired:
                failures.append(f"{module}: import timed out")
            except OSError as exc:
                failures.append(f"{module}: {exc}")

        elapsed = round(time.time() - start, 2)
        if failures:
            return WitnessResult(
                witness_type="smoke", verdict="FAIL", exit_code=1,
                stdout="", stderr="\n".join(failures), elapsed=elapsed,
            )
        return WitnessResult(
            witness_type="smoke", verdict="PASS", exit_code=0,
            stdout=f"{len(modules)} modules imported OK",
            stderr="", elapsed=elapsed,
        )


class NumericalWitness:
    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout

    def run(self, baseline_path: str, cwd: str) -> WitnessResult:
        from pathlib import Path

        path = Path(baseline_path)
        if not path.exists():
            return WitnessResult(
                witness_type="numerical", verdict="SKIP", exit_code=None,
                stdout="", stderr=f"No baseline at {baseline_path}", elapsed=0.0,
            )

        start = time.time()
        baseline = json.loads(path.read_text(encoding="utf-8"))
        command = baseline["command"]
        expected = baseline["values"]
        tolerance = baseline.get("tolerance", 1e-6)

        if not validate_command_prefix(command):
            return WitnessResult(
                witness_type="numerical", verdict="FAIL", exit_code=-1,
                stdout="", stderr=f"Blocked: command prefix not allowlisted: {command[:80]}",
                elapsed=round(time.time() - start, 2),
            )

        try:
            proc = subprocess.run(
                split_command(command), cwd=cwd, shell=False,
                capture_output=True, text=True, timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return WitnessResult(
                witness_type="numerical", verdict="FAIL", exit_code=-1,
                stdout="", stderr=f"Baseline command timed out after {self.timeout}s",
                elapsed=round(time.time() - start, 2),
            )
        except OSError as exc:
            return WitnessResult(
                witness_type="numerical", verdict="FAIL", exit_code=-1,
                stdout="", stderr=f"Failed to start: {exc}",
                elapsed=round(time.time() - start, 2),
            )

        if proc.returncode != 0:
            return WitnessResult(
                witness_type="numerical", verdict="FAIL",
                exit_code=proc.returncode,
                stdout=proc.stdout[-500:],
                stderr=f"Command failed: {proc.stderr.strip()[-500:]}",
                elapsed=round(time.time() - start, 2),
            )

        try:
            actual = json.loads(proc.stdout.strip())
        except (json.JSONDecodeError, ValueError):
            return WitnessResult(
                witness_type="numerical", verdict="FAIL", exit_code=0,
                stdout=proc.stdout[-500:],
                stderr="Could not parse output as JSON",
                elapsed=round(time.time() - start, 2),
            )

        drifts: list[str] = []
        for key, expected_val in expected.items():
            actual_val = actual.get(key)
            if actual_val is None:
                drifts.append(f"{key}: missing in output")
            elif isinstance(expected_val, (int, float)) and isinstance(actual_val, (int, float)):
                # Relative tolerance for large values, absolute for near-zero
                effective_tol = max(tolerance, tolerance * abs(expected_val))
                if abs(actual_val - expected_val) > effective_tol:
                    drifts.append(f"{key}: {expected_val} -> {actual_val} (delta={abs(actual_val - expected_val):.2e}, tol={effective_tol:.2e})")
            elif actual_val != expected_val:
                drifts.append(f"{key}: {expected_val!r} -> {actual_val!r}")

        elapsed = round(time.time() - start, 2)
        if drifts:
            return WitnessResult(
                witness_type="numerical", verdict="FAIL", exit_code=0,
                stdout=proc.stdout[-500:],
                stderr="Numerical drift: " + "; ".join(drifts),
                elapsed=elapsed,
            )
        return WitnessResult(
            witness_type="numerical", verdict="PASS", exit_code=0,
            stdout=f"{len(expected)} values within tolerance",
            stderr="", elapsed=elapsed,
        )
