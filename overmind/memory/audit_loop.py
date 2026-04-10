from __future__ import annotations

import uuid

from overmind.storage.db import StateDatabase
from overmind.storage.models import MemoryRecord, VerificationResult, utc_now


class AuditLoop:
    def __init__(self, db: StateDatabase) -> None:
        self.db = db

    def evaluate(self, project_id: str, result: VerificationResult, tick: int) -> dict[str, object]:
        """Compare current verification result against project history. Returns assessment."""
        history = self.db.list_memories(
            scope=project_id,
            memory_type="audit_snapshot",
            limit=5,
        )

        current_pass_rate = len(result.completed_checks) / max(len(result.required_checks), 1)

        # Store snapshot
        snapshot = MemoryRecord(
            memory_id=f"audit_{uuid.uuid4().hex[:8]}",
            memory_type="audit_snapshot",
            scope=project_id,
            title=f"Audit: {current_pass_rate:.0%} pass rate",
            content=f"Tick {tick}: {len(result.completed_checks)}/{len(result.required_checks)} checks passed. "
                    f"Completed: {', '.join(result.completed_checks)}. "
                    f"Failed/skipped: {', '.join(result.skipped_checks)}.",
            source_task_id=result.task_id,
            source_tick=tick,
            tags=["audit", "snapshot", f"pass_rate:{current_pass_rate:.2f}"],
            confidence=0.9,
        )
        self.db.upsert_memory(snapshot)

        if not history:
            return {
                "project_id": project_id,
                "current_pass_rate": current_pass_rate,
                "trend": "baseline",
                "delta": 0.0,
            }

        # Calculate historical average
        historical_rates: list[float] = []
        for mem in history:
            for tag in mem.tags:
                if tag.startswith("pass_rate:"):
                    try:
                        historical_rates.append(float(tag.split(":")[1]))
                    except ValueError:
                        pass

        if not historical_rates:
            return {
                "project_id": project_id,
                "current_pass_rate": current_pass_rate,
                "trend": "baseline",
                "delta": 0.0,
            }

        avg_historical = sum(historical_rates) / len(historical_rates)
        delta = current_pass_rate - avg_historical

        trend = "stable"
        if delta > 0.05:
            trend = "improving"
        elif delta < -0.05:
            trend = "degrading"
            # Create regression alert
            self.db.upsert_memory(MemoryRecord(
                memory_id=f"audit_alert_{uuid.uuid4().hex[:8]}",
                memory_type="regression",
                scope=project_id,
                title=f"Pass rate degraded: {avg_historical:.0%} -> {current_pass_rate:.0%}",
                content=f"Project {project_id} pass rate dropped by {abs(delta):.0%} on tick {tick}. "
                        f"Historical avg: {avg_historical:.0%}, current: {current_pass_rate:.0%}.",
                source_task_id=result.task_id,
                source_tick=tick,
                tags=["audit", "regression", "degrading"],
                confidence=0.85,
            ))

        return {
            "project_id": project_id,
            "current_pass_rate": current_pass_rate,
            "historical_avg": avg_historical,
            "trend": trend,
            "delta": delta,
        }

    def project_history(self, project_id: str, limit: int = 10) -> list[dict[str, object]]:
        """Get audit history for a project."""
        snapshots = self.db.list_memories(
            scope=project_id,
            memory_type="audit_snapshot",
            limit=limit,
        )
        return [
            {
                "memory_id": s.memory_id,
                "title": s.title,
                "content": s.content,
                "tick": s.source_tick,
                "created_at": s.created_at,
            }
            for s in snapshots
        ]
