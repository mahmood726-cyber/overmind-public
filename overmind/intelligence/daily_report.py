"""Overmind Daily Intelligence Report.

Generates a comprehensive daily report analyzing:
- Portfolio verification coverage and gaps
- Regression trends and alerts
- Runner performance (Q-router trends)
- Memory growth and heuristic quality
- Priority queue for next actions

Usage: overmind daily-report
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from overmind.storage.db import StateDatabase
from overmind.storage.models import MemoryRecord, ProjectRecord, utc_now


class DailyReport:
    def __init__(self, db: StateDatabase, artifacts_dir: Path) -> None:
        self.db = db
        self.artifacts_dir = artifacts_dir
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def generate(self) -> dict[str, object]:
        projects = self.db.list_projects()
        memories = self.db.list_memories(limit=10000)
        scores = self.db.list_routing_scores()

        report: dict[str, object] = {
            "generated_at": utc_now(),
            "day_number": self._compute_day_number(),
        }

        report["portfolio"] = self._portfolio_summary(projects, memories)
        report["verification_coverage"] = self._verification_coverage(projects, memories)
        report["regressions"] = self._regression_alerts(memories)
        report["runner_performance"] = self._runner_performance(scores)
        report["memory_health"] = self._memory_health(memories)
        report["priority_queue"] = self._priority_queue(projects, memories)
        report["daily_targets"] = self._daily_targets(report)
        report["benchmark"] = self._benchmark_tracking(projects, memories, scores)
        report["session_mining"] = self._session_mining_summary()

        return report

    def write(self, report: dict[str, object]) -> dict[str, str]:
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        json_path = self.artifacts_dir / f"daily_report_{date_str}.json"
        md_path = self.artifacts_dir / f"daily_report_{date_str}.md"

        json_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
        md_path.write_text(self._to_markdown(report), encoding="utf-8")

        return {"json": str(json_path), "markdown": str(md_path)}

    def _compute_day_number(self) -> int:
        """Compute day number since Overmind's first checkpoint."""
        checkpoint = self.db.latest_checkpoint("dream")
        if not checkpoint:
            return 1
        try:
            first_date = datetime.fromisoformat(checkpoint.get("last_dream_at", ""))
            delta = datetime.now(UTC) - first_date.replace(tzinfo=UTC) if first_date.tzinfo is None else datetime.now(UTC) - first_date
            return max(1, delta.days + 1)
        except (ValueError, TypeError):
            return 1

    def _portfolio_summary(self, projects: list[ProjectRecord], memories: list) -> dict[str, object]:
        by_type = {}
        by_risk = {}
        for p in projects:
            by_type[p.project_type] = by_type.get(p.project_type, 0) + 1
            by_risk[p.risk_profile] = by_risk.get(p.risk_profile, 0) + 1

        return {
            "total_projects": len(projects),
            "by_type": by_type,
            "by_risk": by_risk,
            "with_advanced_math": sum(1 for p in projects if p.has_advanced_math),
            "with_test_commands": sum(1 for p in projects if p.test_commands),
            "with_browser_tests": sum(1 for p in projects if p.browser_test_commands),
            "git_repos": sum(1 for p in projects if p.is_git_repo),
        }

    def _verification_coverage(self, projects: list[ProjectRecord], memories: list[MemoryRecord]) -> dict[str, object]:
        verified_ids = set()
        for m in memories:
            if m.memory_type in ("project_learning", "audit_snapshot"):
                verified_ids.add(m.scope)

        testable = [p for p in projects if p.test_commands]
        high_risk_unverified = [
            {"name": p.name, "id": p.project_id, "risk": p.risk_profile, "math_score": p.advanced_math_score}
            for p in projects
            if p.project_id not in verified_ids and p.risk_profile in ("high", "medium_high") and p.test_commands
        ]
        high_risk_unverified.sort(key=lambda x: x["math_score"], reverse=True)

        return {
            "verified_count": len(verified_ids),
            "total_testable": len(testable),
            "coverage_percent": round(len(verified_ids) / max(len(testable), 1) * 100, 1),
            "high_risk_unverified_count": len(high_risk_unverified),
            "high_risk_unverified_top10": high_risk_unverified[:10],
        }

    def _regression_alerts(self, memories: list[MemoryRecord]) -> dict[str, object]:
        regressions = [m for m in memories if m.memory_type == "regression"]
        degrading = [m for m in memories if m.memory_type == "audit_snapshot" and "degrading" in str(m.tags)]

        return {
            "active_regressions": len(regressions),
            "details": [
                {"scope": m.scope, "title": m.title, "created": m.created_at}
                for m in regressions[:10]
            ],
        }

    def _runner_performance(self, scores: list[dict]) -> dict[str, object]:
        if not scores:
            return {"status": "insufficient_data", "entries": 0}

        by_runner = {}
        for s in scores:
            rt = s["runner_type"]
            by_runner.setdefault(rt, []).append(s)

        summary = {}
        for rt, entries in by_runner.items():
            total_wins = sum(e["wins"] for e in entries)
            total_losses = sum(e["losses"] for e in entries)
            avg_q = sum(e["q_value"] for e in entries) / len(entries) if entries else 0.5
            summary[rt] = {
                "total_wins": total_wins,
                "total_losses": total_losses,
                "avg_q_value": round(avg_q, 3),
                "task_types": len(entries),
            }

        return {"status": "active", "entries": len(scores), "by_runner": summary}

    def _memory_health(self, memories: list[MemoryRecord]) -> dict[str, object]:
        by_type = {}
        by_status = {}
        for m in memories:
            by_type[m.memory_type] = by_type.get(m.memory_type, 0) + 1
            by_status[m.status] = by_status.get(m.status, 0) + 1

        avg_relevance = sum(m.relevance for m in memories) / max(len(memories), 1)

        return {
            "total": len(memories),
            "by_type": by_type,
            "by_status": by_status,
            "avg_relevance": round(avg_relevance, 3),
            "heuristics_count": by_type.get("heuristic", 0),
        }

    def _priority_queue(self, projects: list[ProjectRecord], memories: list[MemoryRecord]) -> list[dict[str, object]]:
        """Generate a priority-ordered list of projects to verify next."""
        verified_ids = {m.scope for m in memories if m.memory_type in ("project_learning", "audit_snapshot")}

        candidates = []
        for p in projects:
            if p.project_id in verified_ids:
                continue
            if not p.test_commands:
                continue
            score = 0
            if p.risk_profile == "high":
                score += 10
            elif p.risk_profile == "medium_high":
                score += 5
            score += min(p.advanced_math_score, 10)
            if p.has_oracle_benchmarks:
                score += 3
            if p.has_validation_history:
                score += 2
            candidates.append({
                "name": p.name,
                "project_id": p.project_id,
                "risk": p.risk_profile,
                "math_score": p.advanced_math_score,
                "priority_score": score,
                "test_cmd": p.test_commands[0][:80] if p.test_commands else None,
            })

        candidates.sort(key=lambda x: x["priority_score"], reverse=True)
        return candidates[:20]

    def _daily_targets(self, report: dict[str, object]) -> dict[str, object]:
        """Suggest daily targets based on current state."""
        coverage = report["verification_coverage"]["coverage_percent"]
        verified = report["verification_coverage"]["verified_count"]
        total = report["verification_coverage"]["total_testable"]
        regressions = report["regressions"]["active_regressions"]
        queue = report["priority_queue"]

        targets = []
        if regressions > 0:
            targets.append(f"FIX {regressions} active regression(s) first")
        if coverage < 10:
            targets.append(f"Verify 10 high-priority projects (coverage: {coverage:.0f}% -> ~{min(100, coverage + 4):.0f}%)")
        elif coverage < 50:
            targets.append(f"Verify 5 projects from priority queue (coverage: {coverage:.0f}%)")
        else:
            targets.append(f"Maintain coverage ({coverage:.0f}%), focus on regressions")

        if queue:
            targets.append(f"Next project: {queue[0]['name']} (priority={queue[0]['priority_score']})")

        return {
            "coverage_target": min(coverage + 5, 100),
            "verify_count": 10 if coverage < 10 else 5,
            "actions": targets,
        }

    def _benchmark_tracking(self, projects, memories, scores) -> dict[str, object]:
        """Track benchmark metrics over time for proof of improvement."""
        verified_ids = {m.scope for m in memories if m.memory_type in ("project_learning", "audit_snapshot")}
        regression_ids = {m.scope for m in memories if m.memory_type == "regression"}
        heuristic_count = sum(1 for m in memories if m.memory_type == "heuristic")

        total_testable = sum(1 for p in projects if p.test_commands)
        coverage = len(verified_ids) / max(total_testable, 1)

        total_wins = sum(s.get("wins", 0) for s in scores)
        total_losses = sum(s.get("losses", 0) for s in scores)
        overall_pass_rate = total_wins / max(total_wins + total_losses, 1)

        return {
            "coverage_percent": round(coverage * 100, 1),
            "projects_verified": len(verified_ids),
            "projects_testable": total_testable,
            "active_regressions": len(regression_ids),
            "total_memories": len(memories),
            "heuristics_learned": heuristic_count,
            "q_router_entries": len(scores),
            "overall_pass_rate": round(overall_pass_rate * 100, 1),
            "total_verifications": total_wins + total_losses,
        }

    def _session_mining_summary(self) -> dict[str, object]:
        """Run session mining and return summary."""
        try:
            from overmind.intelligence.session_miner import SessionMiner
            miner = SessionMiner(self.db)
            results = miner.mine_and_store(max_sessions=30)
            return {
                "sessions_analyzed": results["sessions_analyzed"],
                "total_messages": results["total_messages"],
                "failure_lines": results["failure_lines"],
                "success_lines": results["success_lines"],
                "top_errors": results["top_errors"],
                "top_projects": results["top_projects"],
                "insights_generated": len(results["insights"]),
            }
        except Exception as exc:
            return {"error": str(exc)[:100]}

    def _to_markdown(self, report: dict[str, object]) -> str:
        lines = [
            f"# OVERMIND Daily Intelligence Report",
            f"",
            f"**Day {report['day_number']}** | Generated: {report['generated_at']}",
            f"",
        ]

        # Portfolio
        p = report["portfolio"]
        lines.extend([
            "## Portfolio",
            f"- {p['total_projects']} projects | {p['with_test_commands']} testable | {p['with_advanced_math']} advanced math",
            f"- Risk: {p['by_risk']}",
            "",
        ])

        # Coverage
        c = report["verification_coverage"]
        lines.extend([
            "## Verification Coverage",
            f"- **{c['verified_count']}/{c['total_testable']} tested ({c['coverage_percent']}%)**",
            f"- High-risk unverified: {c['high_risk_unverified_count']}",
        ])
        if c["high_risk_unverified_top10"]:
            lines.append("- Top unverified:")
            for item in c["high_risk_unverified_top10"][:5]:
                lines.append(f"  - {item['name']} (risk={item['risk']}, math={item['math_score']})")
        lines.append("")

        # Regressions
        r = report["regressions"]
        lines.extend([
            "## Regressions",
            f"- Active: {r['active_regressions']}",
        ])
        for d in r["details"]:
            lines.append(f"  - {d['scope']}: {d['title']}")
        lines.append("")

        # Runner Performance
        rp = report["runner_performance"]
        lines.extend(["## Runner Performance"])
        if rp["status"] == "active":
            for rt, data in rp.get("by_runner", {}).items():
                lines.append(f"- {rt}: q={data['avg_q_value']:.3f} (W:{data['total_wins']} L:{data['total_losses']})")
        else:
            lines.append("- Insufficient data")
        lines.append("")

        # Memory
        mh = report["memory_health"]
        lines.extend([
            "## Memory",
            f"- {mh['total']} memories (avg relevance: {mh['avg_relevance']:.2f})",
            f"- Types: {mh['by_type']}",
            f"- Heuristics: {mh['heuristics_count']}",
            "",
        ])

        # Daily Targets
        dt = report["daily_targets"]
        lines.extend(["## Today's Targets"])
        for action in dt["actions"]:
            lines.append(f"- {action}")
        lines.append("")

        # Priority Queue
        lines.extend(["## Priority Queue (next to verify)"])
        for i, item in enumerate(report["priority_queue"][:10], 1):
            lines.append(f"{i}. **{item['name']}** (priority={item['priority_score']}, risk={item['risk']})")
        lines.append("")

        # Benchmark
        bm = report.get("benchmark", {})
        if bm:
            lines.extend([
                "## Benchmark Tracking (40-day proof)",
                f"- Coverage: {bm.get('coverage_percent', 0)}%",
                f"- Pass rate: {bm.get('overall_pass_rate', 0)}%",
                f"- Total verifications: {bm.get('total_verifications', 0)}",
                f"- Regressions found: {bm.get('active_regressions', 0)}",
                f"- Memories: {bm.get('total_memories', 0)}",
                f"- Heuristics learned: {bm.get('heuristics_learned', 0)}",
                f"- Q-router entries: {bm.get('q_router_entries', 0)}",
                "",
            ])

        # Session Mining
        sm = report.get("session_mining", {})
        if sm and not sm.get("error"):
            lines.extend([
                "## Session Mining (Claude Code transcript analysis)",
                f"- Sessions analyzed: {sm.get('sessions_analyzed', 0)}",
                f"- Total messages: {sm.get('total_messages', 0)}",
                f"- Failure signals: {sm.get('failure_lines', 0)} | Success signals: {sm.get('success_lines', 0)}",
            ])
            if sm.get("top_errors"):
                lines.append(f"- Top errors: {sm['top_errors']}")
            if sm.get("top_projects"):
                top = list(sm["top_projects"].items())[:5]
                lines.append(f"- Most active: {', '.join(f'{p}({c}x)' for p, c in top)}")
            lines.append(f"- Insights mined: {sm.get('insights_generated', 0)}")
            lines.append("")

        return "\n".join(lines)
