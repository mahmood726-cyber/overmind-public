"""Batch verification runner.

Runs verification on a batch of projects from the priority queue.
Usage: overmind batch-verify --count 10
"""
from __future__ import annotations

from overmind.core.orchestrator import Orchestrator
from overmind.storage.models import TaskRecord


def batch_verify(
    orchestrator: Orchestrator,
    count: int = 10,
    risk_filter: str | None = None,
) -> dict[str, object]:
    """Verify the top N projects from the priority queue."""
    projects = orchestrator.db.list_projects()
    memories = orchestrator.db.list_memories(limit=10000)
    verified_ids = {m.scope for m in memories if m.memory_type in ("project_learning", "audit_snapshot")}

    candidates = []
    for p in projects:
        if p.project_id in verified_ids:
            continue
        if not p.test_commands:
            continue
        if risk_filter and p.risk_profile != risk_filter:
            continue
        score = 0
        if p.risk_profile == "high":
            score += 10
        elif p.risk_profile == "medium_high":
            score += 5
        score += min(p.advanced_math_score, 10)
        candidates.append((score, p))

    candidates.sort(key=lambda x: x[0], reverse=True)
    to_verify = [p for _, p in candidates[:count]]

    results = []
    tick = 100  # batch ticks start at 100

    for project in to_verify:
        task = TaskRecord(
            task_id=f"batch_{project.project_id[:12]}",
            project_id=project.project_id,
            title=f"Batch verification for {project.name}",
            task_type="verification",
            source="batch_verify",
            priority=1.0,
            risk=project.risk_profile,
            expected_runtime_min=5,
            expected_context_cost="medium",
            required_verification=["relevant_tests"],
            verify_command=project.test_commands[0] if project.test_commands else None,
        )

        try:
            result = orchestrator.verifier.run(task, project)
            status = "PASS" if result.success else "FAIL"

            # Extract memories
            orchestrator.memory_extractor.extract(
                evidence_items=[],
                verification_results=[result],
                project_ids={task.task_id: project.project_id},
                runner_ids={},
                tick=tick,
            )

            # Audit loop
            orchestrator.audit_loop.evaluate(project.project_id, result, tick=tick)

            # Run verify_command if present
            vc_status = "N/A"
            if task.verify_command and result.success:
                vc_ok = orchestrator._run_verify_command(task, project)
                vc_status = "PASS" if vc_ok else "FAIL"

            details = "; ".join(result.details[:2])
        except Exception as exc:
            status = "ERROR"
            vc_status = "N/A"
            details = str(exc)[:100]

        results.append({
            "name": project.name,
            "project_id": project.project_id,
            "risk": project.risk_profile,
            "math_score": project.advanced_math_score,
            "status": status,
            "verify_command": vc_status,
            "details": details,
        })
        tick += 1

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    errors = sum(1 for r in results if r["status"] == "ERROR")

    return {
        "verified": len(results),
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "results": results,
    }
