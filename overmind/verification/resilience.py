"""Cross-domain resilience patterns for portfolio verification.

Inspired by: nuclear engineering (common-cause failures), immunology
(systemic fever response), financial trading (pre-fix risk checks),
pharmaceutical manufacturing (stability tracking), ecology (canary species).
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path


# ─── 1. Systemic Alert Detector (Immunology: fever response) ───────────────

@dataclass
class SystemicAlert:
    triggered: bool
    failure_rate: float
    dominant_pattern: str
    affected_count: int
    total_count: int
    recommendation: str


class SystemicAlertDetector:
    """Detects infrastructure-level failures (>30% same pattern = fever).

    When >30% of projects share the same failure root cause, the problem
    is systemic (Python update, disk full, network down), not per-project.
    """

    def __init__(self, threshold: float = 0.30) -> None:
        self.threshold = threshold

    def check(self, verdicts: list[dict]) -> SystemicAlert:
        """Check if failure pattern is systemic.

        Args:
            verdicts: list of {"project_id": str, "verdict": str, "reason": str}
        """
        total = len(verdicts)
        if total == 0:
            return SystemicAlert(False, 0.0, "", 0, 0, "")

        failures = [v for v in verdicts if v["verdict"] in ("FAIL", "REJECT")]
        failure_rate = len(failures) / total

        if failure_rate < self.threshold:
            return SystemicAlert(False, failure_rate, "", len(failures), total, "")

        # Find dominant failure pattern
        patterns: dict[str, int] = {}
        for f in failures:
            reason = f.get("reason", "")
            # Extract key phrases
            for keyword in ["timeout", "import", "WinError", "permission",
                            "disk", "memory", "network", "scipy", "WMI"]:
                if keyword.lower() in reason.lower():
                    patterns[keyword] = patterns.get(keyword, 0) + 1

        if not patterns:
            patterns["unknown"] = len(failures)

        dominant = max(patterns, key=patterns.get)
        dominant_count = patterns[dominant]
        dominant_pct = dominant_count / total

        recommendation = {
            "timeout": "Check for WMI deadlock or system resource exhaustion",
            "import": "Check Python environment — possible broken package update",
            "WinError": "Check filesystem permissions or antivirus interference",
            "permission": "Check file permissions — possible security policy change",
            "disk": "Check disk space",
            "memory": "Check available RAM — too many concurrent processes?",
            "network": "Check network connectivity",
            "scipy": "Apply WMI deadlock patch (usercustomize.py)",
            "WMI": "Apply WMI deadlock patch (usercustomize.py)",
            "unknown": "Manual investigation — unrecognized systemic pattern",
        }.get(dominant, f"Investigate dominant pattern: {dominant}")

        return SystemicAlert(
            triggered=dominant_pct >= self.threshold,
            failure_rate=failure_rate,
            dominant_pattern=dominant,
            affected_count=dominant_count,
            total_count=total,
            recommendation=recommendation,
        )


# ─── 2. Pre-Fix Risk Checks (Finance: pre-trade controls) ─────────────────

@dataclass
class PreFixRisk:
    safe: bool
    reason: str


class PreFixRiskChecker:
    """Check if it's safe to apply a fix to a project.

    Like pre-trade risk checks in finance: verify conditions before acting.
    """

    def __init__(self, recent_hours: int = 24) -> None:
        self.recent_hours = recent_hours

    def check(self, project_path: str) -> PreFixRisk:
        """Returns PreFixRisk(safe=True) if it's OK to apply fixes."""
        path = Path(project_path)

        if not path.exists():
            return PreFixRisk(False, "Project path does not exist")

        # Check 1: uncommitted changes (dirty working tree)
        try:
            proc = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=project_path, capture_output=True, text=True, timeout=10,
            )
            if proc.stdout.strip():
                return PreFixRisk(False, "Dirty working tree — human has uncommitted changes")
        except (subprocess.TimeoutExpired, OSError):
            pass  # Not a git repo or git unavailable — allow

        # Check 2: recent human edits (modified in last N hours)
        try:
            proc = subprocess.run(
                ["git", "log", "-1", "--format=%ci"],
                cwd=project_path, capture_output=True, text=True, timeout=10,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                from datetime import timezone
                last_commit = proc.stdout.strip()
                # Parse git date format: "2026-04-09 01:23:45 +0000"
                try:
                    dt = datetime.strptime(last_commit[:19], "%Y-%m-%d %H:%M:%S")
                    age_hours = (datetime.now() - dt).total_seconds() / 3600
                    if age_hours < self.recent_hours:
                        return PreFixRisk(False, f"Last commit {age_hours:.0f}h ago — human may be working on it")
                except (ValueError, TypeError):
                    pass
        except (subprocess.TimeoutExpired, OSError):
            pass

        return PreFixRisk(True, "OK")


# ─── 3. Common-Cause Failure Detector (Nuclear: shared-mode analysis) ──────

@dataclass
class CommonCauseResult:
    is_common_cause: bool
    shared_root: str
    affected_projects: list[str]
    recommendation: str


class CommonCauseDetector:
    """Detects when multiple projects fail from the same root cause.

    In nuclear engineering, common-cause failures bypass redundancy because
    all barriers fail from the same mechanism. Tag these for infrastructure fix.
    """

    def detect(self, failures: list[dict]) -> list[CommonCauseResult]:
        """Group failures by shared root cause.

        Args:
            failures: list of {"project": str, "witnesses": list[str], "evidence": str}
        """
        # Group by evidence keywords
        keyword_groups: dict[str, list[str]] = {}
        keywords_to_check = [
            ("WMI", "Python 3.13 WMI deadlock"),
            ("scipy", "scipy import failure"),
            ("ModuleNotFoundError", "missing module"),
            ("TimeoutExpired", "subprocess timeout"),
            ("WinError 2", "executable not found"),
            ("cp1252", "Windows encoding issue"),
            ("permission", "filesystem permission"),
            ("disk", "disk space"),
        ]

        for f in failures:
            evidence = f.get("evidence", "").lower()
            for keyword, label in keywords_to_check:
                if keyword.lower() in evidence:
                    if label not in keyword_groups:
                        keyword_groups[label] = []
                    keyword_groups[label].append(f["project"])

        results = []
        for root_cause, projects in keyword_groups.items():
            if len(projects) >= 2:  # At least 2 projects share the same cause
                results.append(CommonCauseResult(
                    is_common_cause=True,
                    shared_root=root_cause,
                    affected_projects=projects,
                    recommendation=f"Fix infrastructure: {root_cause} affects {len(projects)} projects",
                ))

        return results


# ─── 4. Stability Tracker (Pharma: batch stability testing) ───────────────

@dataclass
class ProjectStability:
    project_id: str
    certified_streak: int  # Consecutive CERTIFIED/PASS nights
    total_runs: int
    last_verdict: str
    stability_class: str  # "stable", "recovering", "flaky", "degrading"
    alert: bool  # True if a stable project just broke


class StabilityTracker:
    """Tracks CERTIFIED streaks and detects stability breaks.

    Like pharmaceutical stability testing: a product that's been stable
    for 30 batches and then fails is a higher severity event than one
    that's always been flaky.
    """

    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.states: dict[str, dict] = {}
        self._load()

    def update(self, project_id: str, verdict: str) -> ProjectStability:
        """Record a verdict and return stability assessment."""
        state = self.states.get(project_id, {
            "streak": 0, "max_streak": 0, "total": 0,
            "history": [], "last_verdict": ""
        })

        passing = verdict in ("CERTIFIED", "PASS")
        state["total"] += 1
        state["history"].append(verdict)
        state["history"] = state["history"][-30:]  # Keep 30 days

        was_stable = state["streak"] >= 5
        if passing:
            state["streak"] += 1
            state["max_streak"] = max(state["max_streak"], state["streak"])
        else:
            state["streak"] = 0

        state["last_verdict"] = verdict

        # Classify stability
        recent = state["history"][-7:] if len(state["history"]) >= 7 else state["history"]
        pass_rate = sum(1 for v in recent if v in ("CERTIFIED", "PASS")) / max(len(recent), 1)

        if pass_rate >= 0.85:
            stability_class = "stable"
        elif pass_rate >= 0.5 and state["streak"] > 0:
            stability_class = "recovering"
        elif 0.3 <= pass_rate < 0.7:
            stability_class = "flaky"
        else:
            stability_class = "degrading"

        # Alert if a stable project just broke
        alert = was_stable and not passing

        self.states[project_id] = state
        self._save()

        return ProjectStability(
            project_id=project_id,
            certified_streak=state["streak"],
            total_runs=state["total"],
            last_verdict=verdict,
            stability_class=stability_class,
            alert=alert,
        )

    def get_alerts(self) -> list[ProjectStability]:
        """Get all projects with active stability alerts."""
        alerts = []
        for pid, state in self.states.items():
            if state.get("streak", 0) == 0 and state.get("max_streak", 0) >= 5:
                recent = state.get("history", [])[-1:]
                if recent and recent[0] not in ("CERTIFIED", "PASS"):
                    alerts.append(ProjectStability(
                        project_id=pid,
                        certified_streak=0,
                        total_runs=state["total"],
                        last_verdict=state["last_verdict"],
                        stability_class="degrading",
                        alert=True,
                    ))
        return alerts

    def _load(self) -> None:
        if self.state_path.exists():
            try:
                self.states = json.loads(self.state_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.states = {}

    def _save(self) -> None:
        self.state_path.write_text(json.dumps(self.states, indent=2), encoding="utf-8")


# ─── 5. Canary Project Detector (Ecology: ecosystem canaries) ─────────────

@dataclass
class CanaryAlert:
    project_id: str
    project_name: str
    reason: str


class CanaryDetector:
    """Identifies and monitors canary projects — sensitive indicators.

    Low-dependency, pure-Python projects that rarely fail. If they fail,
    something fundamental is wrong with the environment.
    """

    # Projects with minimal dependencies — if these fail, infrastructure is broken
    CANARY_INDICATORS = {
        "no_external_deps",   # Pure stdlib
        "always_passes",      # Has never failed in history
        "fast_test",          # Tests complete in <5s
    }

    def identify_canaries(self, projects: list[dict]) -> list[str]:
        """Identify canary projects from the portfolio.

        Args:
            projects: list of {"project_id", "name", "risk_profile", "math_score",
                              "test_time", "has_scipy", "failure_count"}
        """
        canaries = []
        for p in projects:
            # Low-dependency projects are good canaries
            if p.get("risk_profile") in ("medium", "medium_high"):
                if p.get("math_score", 0) <= 5:  # Not math-heavy
                    canaries.append(p["project_id"])
            # Projects that always pass are canaries
            if p.get("failure_count", 0) == 0 and p.get("total_runs", 0) >= 3:
                canaries.append(p["project_id"])
        return list(set(canaries))

    def check_canaries(
        self,
        canary_ids: list[str],
        current_verdicts: dict[str, str],
        project_names: dict[str, str],
    ) -> list[CanaryAlert]:
        """Check if any canary projects failed — indicates infrastructure problem."""
        alerts = []
        for pid in canary_ids:
            verdict = current_verdicts.get(pid)
            if verdict and verdict in ("FAIL", "REJECT"):
                alerts.append(CanaryAlert(
                    project_id=pid,
                    project_name=project_names.get(pid, pid[:20]),
                    reason=f"Canary project failed with {verdict} — possible infrastructure issue",
                ))
        return alerts
