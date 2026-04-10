from __future__ import annotations

from overmind.storage.models import ProjectRecord, TaskRecord
from overmind.tasks.task_models import build_baseline_task, build_test_first_tasks


OPEN_TASK_STATES = {
    "DISCOVERED",
    "QUEUED",
    "ASSIGNED",
    "RUNNING",
    "NEEDS_INTERVENTION",
    "VERIFYING",
    "BLOCKED",
    "PAUSED",
}


class TaskGenerator:
    def generate(self, projects: list[ProjectRecord], existing_tasks: list[TaskRecord]) -> list[TaskRecord]:
        existing_by_project = {
            task.project_id
            for task in existing_tasks
            if task.status in OPEN_TASK_STATES
        }
        tasks: list[TaskRecord] = []
        for project in projects:
            if project.project_id in existing_by_project:
                continue
            if project.project_type not in {"browser_app", "python_tool", "hybrid_browser_analytics_app"}:
                continue
            if project.has_advanced_math and project.test_commands:
                tasks.extend(build_test_first_tasks(project))
            else:
                tasks.append(build_baseline_task(project))
        return tasks
