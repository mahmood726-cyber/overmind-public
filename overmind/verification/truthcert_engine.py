"""TruthCertEngine: multi-witness verification orchestrator."""
from __future__ import annotations

import hashlib
from pathlib import Path

from overmind.storage.models import ProjectRecord, utc_now
from overmind.verification.cert_bundle import Arbitrator, CertBundle
from overmind.verification.scope_lock import ScopeLock, WitnessResult, compute_tier
from overmind.verification.witnesses import (
    NumericalWitness,
    SmokeWitness,
    SuiteWitness,
)


class TruthCertEngine:
    def __init__(
        self,
        baselines_dir: Path,
        test_timeout: int = 120,
        smoke_timeout: int = 10,
        numerical_timeout: int = 30,
    ) -> None:
        self.baselines_dir = baselines_dir
        self.baselines_dir.mkdir(parents=True, exist_ok=True)
        self.test_suite_witness = SuiteWitness(timeout=test_timeout)
        self.smoke_witness = SmokeWitness(timeout=smoke_timeout)
        self.numerical_witness = NumericalWitness(timeout=numerical_timeout)
        self.arbitrator = Arbitrator()

    def build_scope_lock(self, project: ProjectRecord) -> ScopeLock:
        tier = compute_tier(project.risk_profile, project.advanced_math_score)
        test_command = project.test_commands[0] if project.test_commands else ""
        smoke_modules = self._discover_modules(project.root_path) if tier >= 2 else ()
        baseline_path = self._find_baseline(project.project_id) if tier >= 3 else None
        source_hash = self._hash_source_files(project.root_path)

        return ScopeLock(
            project_id=project.project_id,
            project_path=project.root_path,
            risk_profile=project.risk_profile,
            witness_count=tier,
            test_command=test_command,
            smoke_modules=tuple(smoke_modules),
            baseline_path=baseline_path,
            expected_outcome="pass",
            source_hash=source_hash,
            created_at=utc_now(),
        )

    def verify(self, project: ProjectRecord) -> CertBundle:
        lock = self.build_scope_lock(project)
        results: list[WitnessResult] = []

        # Witness 1: always run test suite
        if lock.test_command:
            results.append(self.test_suite_witness.run(lock.test_command, lock.project_path))
        else:
            results.append(WitnessResult(
                witness_type="test_suite", verdict="SKIP", exit_code=None,
                stdout="", stderr="No test command", elapsed=0.0,
            ))

        # Witness 2: smoke check (tier 2+)
        # Always call smoke_witness.run so mocks can intercept; it handles empty list internally.
        if lock.witness_count >= 2:
            results.append(self.smoke_witness.run(
                list(lock.smoke_modules), lock.project_path,
            ))

        # Witness 3: numerical regression (tier 3)
        if lock.witness_count >= 3:
            if lock.baseline_path:
                results.append(self.numerical_witness.run(
                    lock.baseline_path, lock.project_path,
                ))
            else:
                results.append(WitnessResult(
                    witness_type="numerical", verdict="SKIP", exit_code=None,
                    stdout="", stderr="No baseline file", elapsed=0.0,
                ))

        verdict, reason = self.arbitrator.arbitrate(results)

        # Single retry for REJECT: re-run failing witness once to filter transient flakes
        if verdict == "REJECT":
            failed_indices = [i for i, r in enumerate(results) if r.verdict == "FAIL"]
            for idx in failed_indices:
                orig = results[idx]
                if orig.witness_type == "test_suite" and lock.test_command:
                    retry = self.test_suite_witness.run(lock.test_command, lock.project_path)
                elif orig.witness_type == "smoke":
                    retry = self.smoke_witness.run(list(lock.smoke_modules), lock.project_path)
                elif orig.witness_type == "numerical" and lock.baseline_path:
                    retry = self.numerical_witness.run(lock.baseline_path, lock.project_path)
                else:
                    continue
                if retry.verdict == "PASS":
                    results[idx] = retry  # Transient flake — use retry result
            verdict, reason = self.arbitrator.arbitrate(results)
            if verdict != "REJECT":
                reason = f"{reason} (upgraded after retry)"

        return CertBundle(
            project_id=project.project_id,
            scope_lock=lock,
            witness_results=results,
            verdict=verdict,
            arbitration_reason=reason,
            timestamp=utc_now(),
        )

    # Directories containing scripts/examples/dev tools — not importable modules
    _SKIP_DIRS = {".", "_", "test", "tests", "node_modules", "scripts", "examples",
                  "dev", "docs", "data", "fixtures", "migrations", "backup", "archive"}
    # Root-level files that are scripts, not importable modules
    _SKIP_FILES = {"setup", "conftest", "manage", "run", "main", "cli", "app",
                   "noxfile", "fabfile", "tasks"}

    def _discover_modules(self, root_path: str) -> list[str]:
        modules: list[str] = []
        root = Path(root_path)
        for py_file in sorted(root.glob("*.py")):
            name = py_file.stem
            if name.startswith("_") or name in self._SKIP_FILES:
                continue
            modules.append(name)
        for py_file in sorted(root.glob("*/*.py")):
            if any(py_file.parent.name.startswith(s) for s in self._SKIP_DIRS):
                continue
            name = py_file.stem
            if name.startswith("_"):
                continue
            modules.append(f"{py_file.parent.name}.{name}")
        return modules[:20]

    def _find_baseline(self, project_id: str) -> str | None:
        path = self.baselines_dir / f"{project_id}.json"
        return str(path) if path.exists() else None

    def _hash_source_files(self, root_path: str) -> str:
        """Hash source, test, and HTML files to detect any code change."""
        hasher = hashlib.sha256()
        root = Path(root_path)
        source_files = sorted(root.glob("*.py"))
        source_files += sorted(root.glob("*/*.py"))
        # Include HTML dashboards — formula changes in 50K-line HTML files must invalidate cache
        html_files = sorted(root.glob("*.html"))
        test_files = sorted(
            list(root.glob("**/test_*.py")) + list(root.glob("**/*_test.py"))
        )
        all_files = sorted(set(source_files + test_files + html_files), key=lambda p: str(p))
        for f in all_files[:100]:
            if any(part.startswith((".", "node_modules", "__pycache__", ".git")) for part in f.parts):
                continue
            try:
                hasher.update(f.read_bytes())
            except OSError:
                continue
        return hasher.hexdigest()[:16]
