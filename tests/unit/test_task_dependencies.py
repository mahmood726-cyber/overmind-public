from __future__ import annotations

from overmind.storage.db import StateDatabase
from overmind.storage.models import ProjectRecord, TaskRecord
from overmind.tasks.task_queue import TaskQueue
from overmind.tasks.task_generator import TaskGenerator


def test_queued_filters_out_blocked_tasks(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    queue = TaskQueue(db)
    try:
        build_task = TaskRecord(
            task_id="task-build",
            project_id="proj-1",
            title="Build",
            task_type="verification",
            source="test",
            priority=0.9,
            risk="medium",
            expected_runtime_min=5,
            expected_context_cost="low",
            required_verification=["build"],
            status="QUEUED",
        )
        test_task = TaskRecord(
            task_id="task-test",
            project_id="proj-1",
            title="Test",
            task_type="verification",
            source="test",
            priority=0.8,
            risk="medium",
            expected_runtime_min=5,
            expected_context_cost="low",
            required_verification=["relevant_tests"],
            status="QUEUED",
            blocked_by=["task-build"],
        )
        queue.upsert([build_task, test_task])

        queued = queue.queued()
        queued_ids = {t.task_id for t in queued}
        assert "task-build" in queued_ids
        assert "task-test" not in queued_ids

        queue.transition("task-build", "ASSIGNED")
        queue.transition("task-build", "RUNNING")
        queue.transition("task-build", "VERIFYING")
        queue.transition("task-build", "COMPLETED")

        queued_after = queue.queued()
        queued_ids_after = {t.task_id for t in queued_after}
        assert "task-test" in queued_ids_after
    finally:
        db.close()


def test_task_with_no_blockers_is_always_queued(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    queue = TaskQueue(db)
    try:
        task = TaskRecord(
            task_id="task-free",
            project_id="proj-1",
            title="Free task",
            task_type="verification",
            source="test",
            priority=0.5,
            risk="medium",
            expected_runtime_min=5,
            expected_context_cost="low",
            required_verification=["build"],
            status="QUEUED",
        )
        queue.upsert([task])
        queued = queue.queued()
        assert any(t.task_id == "task-free" for t in queued)
    finally:
        db.close()
