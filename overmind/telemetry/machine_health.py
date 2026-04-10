from __future__ import annotations

import psutil

from overmind.storage.models import MachineHealthSnapshot


class MachineHealthMonitor:
    def snapshot(self, active_sessions: int) -> MachineHealthSnapshot:
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        cpu = psutil.cpu_percent(interval=0.1)
        if cpu >= 88 or memory.percent >= 85:
            load_state = "degraded"
        elif cpu <= 70 and memory.percent <= 80:
            load_state = "healthy"
        else:
            load_state = "steady"
        return MachineHealthSnapshot(
            cpu_percent=cpu,
            ram_percent=memory.percent,
            swap_used_mb=round(swap.used / (1024 * 1024), 2),
            active_sessions=active_sessions,
            load_state=load_state,
        )

