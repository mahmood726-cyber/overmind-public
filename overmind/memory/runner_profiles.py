from __future__ import annotations

from overmind.storage.models import RunnerRecord


class RunnerProfiles:
    def suitability(self, runner: RunnerRecord) -> dict[str, float]:
        return {
            "success": runner.success_rate_7d,
            "failure": runner.failure_rate_7d,
            "latency": runner.avg_latency_sec,
        }

