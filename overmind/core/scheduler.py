from __future__ import annotations

from typing import TYPE_CHECKING

from overmind.config import PoliciesConfig
from overmind.storage.models import Assignment, ProjectRecord, RunnerRecord, TaskRecord

if TYPE_CHECKING:
    from overmind.runners.q_router import QRouter


class Scheduler:
    def __init__(self, policies: PoliciesConfig, q_router: QRouter | None = None) -> None:
        self.policies = policies
        self.q_router = q_router

    def assign(
        self,
        tasks: list[TaskRecord],
        runners: list[RunnerRecord],
        projects: dict[str, ProjectRecord],
        capacity: int,
        prompt_builder,
    ) -> list[Assignment]:
        available_runners = [runner for runner in runners if runner.status == "AVAILABLE" and runner.available]
        queued_tasks = sorted(tasks, key=lambda task: task.priority, reverse=True)
        assignments: list[Assignment] = []

        for task in queued_tasks:
            if len(assignments) >= capacity:
                break
            if not available_runners:
                break
            project = projects.get(task.project_id)
            if not project:
                continue
            best_runner = max(
                available_runners,
                key=lambda runner: self._runner_score(runner, task),
            )
            assignments.append(
                Assignment(
                    runner_id=best_runner.runner_id,
                    task_id=task.task_id,
                    project_id=task.project_id,
                    prompt=prompt_builder(project, task),
                )
            )
            available_runners.remove(best_runner)
        return assignments

    def _runner_score(self, runner: RunnerRecord, task: TaskRecord) -> float:
        strengths = self.policies.strengths_for(runner.runner_type)
        score = runner.success_rate_7d - runner.failure_rate_7d
        if task.task_type == "verification" and "tests" in strengths:
            score += 0.4
        if task.task_type == "performance_optimization" and "benchmarks" in strengths:
            score += 0.4
        if task.task_type in {"architecture", "refactor"} and "architecture" in strengths:
            score += 0.4
        if task.risk.startswith("high") and runner.runner_type == "claude":
            score += 0.2
        score -= min(runner.avg_latency_sec / 120.0, 0.3)
        if self.q_router is not None:
            score += self.q_router.score(runner.runner_type, task.task_type) * 0.5
        return score
