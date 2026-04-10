from __future__ import annotations

import shutil

from overmind.config import AppConfig, RunnerDefinition
from overmind.runners.base import BaseRunnerAdapter
from overmind.runners.claude_runner import ClaudeRunnerAdapter
from overmind.runners.codex_runner import CodexRunnerAdapter
from overmind.runners.gemini_runner import GeminiRunnerAdapter
from overmind.runners.quota_tracker import QuotaTracker
from overmind.storage.db import StateDatabase
from overmind.storage.models import RunnerRecord, utc_now


ADAPTERS = {
    "claude": ClaudeRunnerAdapter,
    "codex": CodexRunnerAdapter,
    "gemini": GeminiRunnerAdapter,
}


def _command_name(command: str) -> str:
    stripped = command.strip()
    if stripped.startswith('"'):
        return stripped.split('"', 2)[1]
    return stripped.split(" ", 1)[0]


class RunnerRegistry:
    def __init__(self, config: AppConfig, db: StateDatabase) -> None:
        self.config = config
        self.db = db
        self.quota_tracker = QuotaTracker()

    def refresh(self, active_assignments: dict[str, str]) -> list[RunnerRecord]:
        records: list[RunnerRecord] = []
        for definition in self.config.runners:
            previous = self.db.get_runner(definition.runner_id)
            available, reason = self._command_available(definition)
            adapter_cls = ADAPTERS.get(definition.type, BaseRunnerAdapter)
            adapter = adapter_cls(definition)
            record = adapter.build_record(previous, available=available, reason=reason)
            record.preferred_tasks = adapter.preferred_tasks(
                self.config.policies.strengths_for(definition.type)
            )
            record.last_seen_at = utc_now()
            if definition.runner_id in active_assignments:
                record.status = "BUSY"
                record.current_task_id = active_assignments[definition.runner_id]
            elif available and self.quota_tracker.cooldown_active(record.quota_state, record.last_seen_at):
                record.status = "RATE_LIMITED"
                record.current_task_id = None
                record.health = "degraded"
            elif available:
                if record.quota_state == "limited":
                    record.quota_state = "normal"
                record.status = "AVAILABLE"
                record.current_task_id = None
                record.health = "good"
            else:
                record.status = "OFFLINE"
                record.current_task_id = None
                record.health = "unhealthy" if not definition.optional else "degraded"
            self.db.upsert_runner(record)
            records.append(record)
        return records

    def update_outcome(
        self,
        runner_id: str,
        success: bool,
        latency_sec: float,
        output_lines: list[str] | None = None,
    ) -> None:
        record = self.db.get_runner(runner_id)
        if not record:
            return

        output_lines = output_lines or []
        rate_limited = self.quota_tracker.detect_rate_limit(output_lines)
        record.avg_latency_sec = round(
            latency_sec if record.avg_latency_sec == 0 else (record.avg_latency_sec * 0.7) + (latency_sec * 0.3),
            2,
        )
        record.success_rate_7d = round(
            (record.success_rate_7d * 0.8) + (0.2 if success else 0.0),
            2,
        )
        record.failure_rate_7d = round(
            (record.failure_rate_7d * 0.8) + (0.2 if not success else 0.0),
            2,
        )
        record.quota_state = "limited" if rate_limited else "normal"
        if rate_limited and record.available:
            record.status = "RATE_LIMITED"
            record.health = "degraded"
        else:
            record.status = "AVAILABLE" if record.available else "OFFLINE"
        record.current_task_id = None
        record.last_seen_at = utc_now()
        self.db.upsert_runner(record)

    def adapter_for(self, runner_id: str) -> BaseRunnerAdapter | None:
        for definition in self.config.runners:
            if definition.runner_id == runner_id:
                adapter_cls = ADAPTERS.get(definition.type, BaseRunnerAdapter)
                return adapter_cls(definition)
        return None

    def _command_available(self, definition: RunnerDefinition) -> tuple[bool, str | None]:
        command_name = _command_name(definition.command)
        if shutil.which(command_name):
            return True, None
        return False, f"Command not found: {command_name}"
