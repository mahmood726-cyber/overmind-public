from __future__ import annotations

from overmind.storage.models import ProjectRecord, TaskRecord


class Prioritizer:
    def reprioritize(self, tasks: list[TaskRecord], projects: dict[str, ProjectRecord]) -> list[TaskRecord]:
        for task in tasks:
            project = projects.get(task.project_id)
            if not project:
                continue
            score = 0.5
            if project.browser_test_commands:
                score += 0.15
            if project.has_numeric_logic:
                score += 0.2
            if project.has_advanced_math:
                score += min(project.advanced_math_score / 40.0, 0.2)
            if project.analysis_risk_factors:
                score += min(len(project.analysis_risk_factors) / 40.0, 0.08)
            if task.task_type == "performance_optimization":
                score += 0.1
            task.priority = round(min(score, 0.99), 2)
        return sorted(tasks, key=lambda task: task.priority, reverse=True)
