"""Safe auto-fix strategies per failure type.

Safety rule: NEVER modify .py/.html/.js source files.
Only environmental fixes (installs, paths, baselines, configs).
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PYTHON = sys.executable


@dataclass
class FixResult:
    success: bool
    action_taken: str
    detail: str


class DependencyRotFix:
    """Fix missing Python modules via pip install."""

    # Modules that are local project code, not pip-installable.
    # Generic names that exist on PyPI but are almost always local-package collisions.
    # Add your own project-specific local module names to this list.
    LOCAL_MODULE_PATTERNS = re.compile(
        r"^(pipeline|lib|src|engine|sim|shared|scripts|examples|dev|tests|"
        r"evaluation|sensitivity_analysis|statistical_framework|overmind|"
        r"utils|helpers|config|common|core|app|main|run|setup|tool|tools"
        r")\b"
    )

    def can_fix(self, diagnosis) -> bool:
        return diagnosis.failure_type == "DEPENDENCY_ROT"

    def apply(self, diagnosis, project_path: str) -> FixResult:
        # Extract module name from evidence
        module = None
        for ev in diagnosis.evidence:
            m = re.search(r"No module named ['\"]?(\w[\w.]*)", ev)
            if m:
                module = m.group(1).split(".")[0]  # Top-level package
                break

        if not module:
            return FixResult(False, "skip", "Could not extract module name from evidence")

        # Strict validation: only alphanumeric + hyphen + underscore
        if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]*', module):
            return FixResult(False, "skip", f"Module name '{module}' failed validation")

        # Don't try to pip install local project modules
        if self.LOCAL_MODULE_PATTERNS.match(module):
            return FixResult(False, "skip", f"'{module}' is a local module, not pip-installable")

        # Try pip install
        try:
            proc = subprocess.run(
                [PYTHON, "-m", "pip", "install", module, "--quiet"],
                capture_output=True, text=True, timeout=60,
            )
            if proc.returncode == 0:
                return FixResult(True, f"pip install {module}", "Installed successfully")
            return FixResult(False, f"pip install {module}", proc.stderr.strip()[-200:])
        except subprocess.TimeoutExpired:
            return FixResult(False, f"pip install {module}", "Timed out after 60s")
        except OSError as exc:
            return FixResult(False, f"pip install {module}", str(exc))


class BaselineDriftFix:
    """Regenerate numerical baselines when code is correct but values drifted."""

    def __init__(self, baselines_dir: Path, probes_dir: Path) -> None:
        self.baselines_dir = baselines_dir
        self.probes_dir = probes_dir

    def can_fix(self, diagnosis) -> bool:
        if diagnosis.failure_type != "NUMERICAL_DRIFT":
            return False
        # Only fix if we have a probe for this project
        return self._find_probe(diagnosis.project_id) is not None

    def apply(self, diagnosis, project_path: str) -> FixResult:
        probe_path = self._find_probe(diagnosis.project_id)
        if not probe_path:
            return FixResult(False, "skip", "No probe script found")

        baseline_path = self._find_baseline(diagnosis.project_id)
        if not baseline_path:
            return FixResult(False, "skip", "No baseline file found")

        # Load existing baseline
        try:
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            old_values = baseline.get("values", {})
        except (json.JSONDecodeError, OSError) as exc:
            return FixResult(False, "regenerate baseline", f"Corrupt baseline file: {exc}")

        # Run the probe to get current values
        try:
            proc = subprocess.run(
                [PYTHON, str(probe_path)],
                cwd=project_path, capture_output=True, text=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            return FixResult(False, "regenerate baseline", "Probe timed out")

        if proc.returncode != 0:
            return FixResult(False, "regenerate baseline", f"Probe failed: {proc.stderr[-200:]}")

        import json
        try:
            new_values = json.loads(proc.stdout.strip())
        except (json.JSONDecodeError, ValueError):
            return FixResult(False, "regenerate baseline", "Probe output not valid JSON")

        # Delta bounds-checking: reject if any numeric value changes by >50%
        # (likely a real bug, not a minor drift from code refactoring)
        large_deltas = []
        for key in old_values:
            old_val = old_values.get(key)
            new_val = new_values.get(key)
            if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
                if old_val != 0:
                    pct_change = abs(new_val - old_val) / abs(old_val)
                    if pct_change > 0.5:
                        large_deltas.append(f"{key}: {old_val}->{new_val} ({pct_change:.0%})")
        if large_deltas:
            return FixResult(
                False, "regenerate baseline",
                f"Blocked: {len(large_deltas)} values changed >50% — likely a real bug: {'; '.join(large_deltas[:3])}"
            )

        # Update the baseline
        baseline["values"] = new_values
        baseline_path.write_text(json.dumps(baseline, indent=2), encoding="utf-8")

        # Report what changed
        changes = []
        for key in set(list(old_values.keys()) + list(new_values.keys())):
            old = old_values.get(key)
            new = new_values.get(key)
            if old != new:
                changes.append(f"{key}: {old} -> {new}")

        return FixResult(True, "regenerate baseline", f"Updated {len(changes)} values: {'; '.join(changes[:5])}")

    def _find_probe(self, project_id: str) -> Path | None:
        prefix = project_id.split("-")[0]
        for probe in self.probes_dir.glob("probe_*.py"):
            if prefix in probe.stem:
                return probe
        return None

    def _find_baseline(self, project_id: str) -> Path | None:
        for bl in self.baselines_dir.glob("*.json"):
            if bl.stem.startswith(project_id[:20]):
                return bl
        return None


class MissingFixtureFix:
    """Restore missing files from git."""

    def can_fix(self, diagnosis) -> bool:
        return diagnosis.failure_type == "MISSING_FIXTURE"

    def apply(self, diagnosis, project_path: str) -> FixResult:
        # Extract file path from evidence
        path = None
        for ev in diagnosis.evidence:
            m = re.search(r"['\"]([^'\"]+\.\w+)['\"]", ev)
            if m:
                path = m.group(1)
                break

        if not path:
            return FixResult(False, "skip", "Could not extract file path from evidence")

        # Path traversal protection: resolve and verify within project root
        resolved = (Path(project_path) / path).resolve()
        if not str(resolved).startswith(str(Path(project_path).resolve())):
            return FixResult(False, "skip", f"Path traversal blocked: {path}")

        # Try git checkout
        try:
            proc = subprocess.run(
                ["git", "checkout", "HEAD", "--", path],
                cwd=project_path, capture_output=True, text=True, timeout=10,
            )
            if proc.returncode == 0:
                return FixResult(True, f"git checkout -- {path}", "Restored from git")
            return FixResult(False, f"git checkout -- {path}", proc.stderr.strip()[-200:])
        except (subprocess.TimeoutExpired, OSError) as exc:
            return FixResult(False, f"git checkout -- {path}", str(exc))
