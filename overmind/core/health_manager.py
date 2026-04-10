from __future__ import annotations

from overmind.storage.models import MachineHealthSnapshot
from overmind.telemetry.machine_health import MachineHealthMonitor


class HealthManager:
    def __init__(self) -> None:
        self.monitor = MachineHealthMonitor()

    def snapshot(self, active_sessions: int) -> MachineHealthSnapshot:
        return self.monitor.snapshot(active_sessions)

