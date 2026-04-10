from __future__ import annotations

from overmind.core.state_machine import assert_valid_task_transition
from overmind.storage.db import StateDatabase
from overmind.storage.models import TaskRecord, utc_now


class TaskQueue:
    def __init__(self, db: StateDatabase) -> None:
        self.db = db

    def upsert(self, tasks: list[TaskRecord]) -> None:
        for task in tasks:
            task.updated_at = utc_now()
            self.db.upsert_task(task)

    def list_all(self) -> list[TaskRecord]:
        return self.db.list_tasks()

    def list_by_status(self, *statuses: str) -> list[TaskRecord]:
        if not statuses:
            return self.list_all()
        allowed = set(statuses)
        return [task for task in self.db.list_tasks() if task.status in allowed]

    def queued(self) -> list[TaskRecord]:
        candidates = self.list_by_status("QUEUED", "DISCOVERED")
        completed_ids = {task.task_id for task in self.db.list_tasks() if task.status in {"COMPLETED", "ARCHIVED"}}
        return [
            task for task in candidates
            if not task.blocked_by or all(dep in completed_ids for dep in task.blocked_by)
        ]

    def transition(
        self,
        task_id: str,
        status: str,
        assigned_runner_id: str | None = None,
        last_error: str | None = None,
        verification_summary: list[str] | None = None,
    ) -> TaskRecord:
        task = self.db.get_task(task_id)
        if not task:
            raise KeyError(f"Unknown task {task_id}")

        assert_valid_task_transition(task.status, status)
        task.status = status
        task.updated_at = utc_now()
        if assigned_runner_id is not None:
            task.assigned_runner_id = assigned_runner_id
        if last_error is not None:
            task.last_error = last_error
        if verification_summary is not None:
            task.verification_summary = verification_summary
        if status == "ASSIGNED":
            task.attempt_count += 1
        self.db.upsert_task(task)
        return task

