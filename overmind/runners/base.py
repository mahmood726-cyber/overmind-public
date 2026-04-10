from __future__ import annotations

from dataclasses import dataclass

from overmind.config import RunnerDefinition
from overmind.runners.protocols import INTERACTIVE, RunnerProtocol
from overmind.storage.models import RunnerRecord


@dataclass(slots=True)
class BaseRunnerAdapter:
    definition: RunnerDefinition

    def protocol(self) -> RunnerProtocol:
        return INTERACTIVE

    def preferred_tasks(self, routing_strengths: list[str]) -> list[str]:
        return list(routing_strengths)

    def build_record(self, previous: RunnerRecord | None, available: bool, reason: str | None) -> RunnerRecord:
        if previous:
            return RunnerRecord(
                runner_id=self.definition.runner_id,
                runner_type=self.definition.type,
                environment=self.definition.environment,
                command=self.definition.command,
                status=previous.status,
                health=previous.health,
                current_task_id=previous.current_task_id,
                avg_latency_sec=previous.avg_latency_sec,
                success_rate_7d=previous.success_rate_7d,
                failure_rate_7d=previous.failure_rate_7d,
                quota_state=previous.quota_state,
                preferred_tasks=previous.preferred_tasks,
                optional=self.definition.optional,
                available=available,
                unavailability_reason=reason,
            )
        return RunnerRecord(
            runner_id=self.definition.runner_id,
            runner_type=self.definition.type,
            environment=self.definition.environment,
            command=self.definition.command,
            preferred_tasks=[],
            optional=self.definition.optional,
            available=available,
            unavailability_reason=reason,
        )

