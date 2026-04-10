from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from overmind.redaction import detect_secret_kinds
from overmind.storage.models import ProjectRecord, utc_now


class PortfolioAuditor:
    def __init__(self, artifacts_dir: Path) -> None:
        self.artifacts_dir = artifacts_dir
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def build_report(self, projects: list[ProjectRecord]) -> dict[str, Any]:
        by_type = Counter(project.project_type for project in projects)
        by_stack = Counter(stack for project in projects for stack in project.stack)
        risk_counts = Counter(project.risk_profile for project in projects)
        advanced_math_counts = Counter(signal for project in projects for signal in project.advanced_math_signals)
        advanced_math_rigor = Counter(project.advanced_math_rigor for project in projects if project.has_advanced_math)
        analysis_focus_areas = Counter(area for project in projects for area in project.analysis_focus_areas)
        analysis_risk_factors = Counter(factor for project in projects for factor in project.analysis_risk_factors)
        verification_pressure = Counter(check for project in projects for check in project.recommended_verification)
        risk_rank = {"high": 3, "medium_high": 2, "medium": 1, "low": 0}

        report = {
            "generated_at": utc_now(),
            "project_count": len(projects),
            "project_types": dict(by_type),
            "stacks": dict(by_stack.most_common(12)),
            "risk_profiles": dict(risk_counts),
            "projects_with_claude": sum(
                1 for project in projects if any(path.lower() == "claude.md" for path in project.guidance_files)
            ),
            "projects_with_advanced_math": sum(1 for project in projects if project.has_advanced_math),
            "projects_with_validation_logs": sum(1 for project in projects if project.has_validation_history),
            "projects_with_oracle_benchmarks": sum(1 for project in projects if project.has_oracle_benchmarks),
            "projects_with_drift_history": sum(1 for project in projects if project.has_drift_history),
            "advanced_math_signals": dict(advanced_math_counts),
            "advanced_math_rigor": dict(advanced_math_rigor),
            "analysis_focus_areas": dict(analysis_focus_areas),
            "analysis_risk_factors": dict(analysis_risk_factors),
            "verification_pressure": dict(verification_pressure),
            "high_risk_projects": [
                {
                    "project_id": project.project_id,
                    "name": project.name,
                    "root_path": project.root_path,
                    "risk_profile": project.risk_profile,
                    "advanced_math_signals": project.advanced_math_signals[:3],
                    "analysis_focus_areas": project.analysis_focus_areas[:3],
                    "analysis_risk_factors": project.analysis_risk_factors[:3],
                    "advanced_math_score": project.advanced_math_score,
                    "activity_summary": project.activity_summary[:3],
                }
                for project in sorted(
                    projects,
                    key=lambda item: (risk_rank.get(item.risk_profile, -1), item.name.lower()),
                    reverse=True,
                )
                if project.risk_profile in {"high", "medium_high"}
            ][:20],
            "workflow_signals": self._workflow_signals(projects),
            "user_history_findings": self._user_history_findings(),
        }
        return report

    def write_report(self, report: dict[str, Any]) -> dict[str, str]:
        json_path = self.artifacts_dir / "portfolio_audit.json"
        md_path = self.artifacts_dir / "portfolio_audit.md"
        json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        md_path.write_text(self._to_markdown(report), encoding="utf-8")
        return {"json": str(json_path), "markdown": str(md_path)}

    def _workflow_signals(self, projects: list[ProjectRecord]) -> list[str]:
        signals: list[str] = []
        if any(project.has_numeric_logic for project in projects):
            signals.append("numeric and analytical projects dominate the portfolio")
        if any(project.has_advanced_math for project in projects):
            signals.append("advanced statistical or mathematical workflows need stricter fixture, edge-case, and output-comparison checks")
        if any(project.analysis_focus_areas for project in projects):
            signals.append("analysis focus areas can be clustered into evidence synthesis, prediction validation, survival, causal, and numerical stability domains")
        if any(project.analysis_risk_factors for project in projects):
            signals.append("analysis-specific risk factors should drive assumption checks such as censoring, convergence, ranking stability, and missingness sensitivity")
        if any(project.has_validation_history for project in projects):
            signals.append("projects keep repeatable validation logs and regression evidence")
        if any(project.has_oracle_benchmarks for project in projects):
            signals.append("oracle or parity benchmark workflows are present and should raise verification burden")
        if any("r" in project.stack for project in projects):
            signals.append("R-backed analytics projects need first-class detection and test routing")
        if any(any(name.lower() == "claude.md" for name in project.guidance_files) for project in projects):
            signals.append("project-local CLAUDE guidance is common and should be treated as first-class routing input")
        return signals

    def _user_history_findings(self) -> list[dict[str, Any]]:
        home = Path.home()
        findings: list[dict[str, Any]] = []
        candidate_paths = [
            home / ".aider.chat.history.md",
            home / ".aider.input.history",
            home / "training_pipeline.log",
            home / "out.log",
            home / "err.log",
        ]
        for path in candidate_paths:
            if not path.exists():
                continue
            try:
                text = path.read_text(encoding="utf-8-sig", errors="ignore")[:20000]
            except OSError:
                continue
            secret_kinds = detect_secret_kinds(text)
            findings.append(
                {
                    "path": str(path),
                    "secret_kinds": secret_kinds,
                    "has_secret_exposure": bool(secret_kinds),
                }
            )
        return findings

    def _to_markdown(self, report: dict[str, Any]) -> str:
        lines = [
            "# OVERMIND Portfolio Audit",
            "",
            f"- Generated: {report['generated_at']}",
            f"- Projects indexed: {report['project_count']}",
            f"- Advanced math projects: {report['projects_with_advanced_math']}",
            "",
            "## Portfolio Shape",
        ]
        for key, value in report["project_types"].items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Stack Signals"])
        for key, value in report["stacks"].items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Advanced Math Signals"])
        for key, value in report["advanced_math_signals"].items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Advanced Math Rigor"])
        for key, value in report["advanced_math_rigor"].items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Analysis Focus Areas"])
        for key, value in report["analysis_focus_areas"].items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Analysis Risk Factors"])
        for key, value in report["analysis_risk_factors"].items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Verification Pressure"])
        for key, value in report["verification_pressure"].items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Workflow Signals"])
        for signal in report["workflow_signals"]:
            lines.append(f"- {signal}")
        lines.extend(["", "## User History Findings"])
        for finding in report["user_history_findings"]:
            kinds = ", ".join(finding["secret_kinds"]) or "none"
            lines.append(f"- {finding['path']}: secret exposure={finding['has_secret_exposure']} kinds={kinds}")
        return "\n".join(lines) + "\n"
