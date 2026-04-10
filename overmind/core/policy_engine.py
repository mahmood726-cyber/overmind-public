from __future__ import annotations

from overmind.config import PoliciesConfig
from overmind.storage.models import MachineHealthSnapshot, TaskRecord


class PolicyEngine:
    def __init__(self, policies: PoliciesConfig) -> None:
        self.policies = policies

    def compute_concurrency(self, machine: MachineHealthSnapshot, available_runners: int) -> int:
        concurrency = self.policies.concurrency
        default_sessions = int(concurrency.get("default_active_sessions", 3))
        max_sessions = int(concurrency.get("max_active_sessions", 3))
        degraded_sessions = int(concurrency.get("degraded_sessions", 1))
        cpu_high = float(concurrency.get("scale_down_cpu_above", 88))
        ram_high = float(concurrency.get("scale_down_ram_above", 85))
        swap_high = float(concurrency.get("scale_down_swap_above_mb", 1024))
        cpu_low = float(concurrency.get("scale_up_cpu_below", 70))

        if machine.cpu_percent >= cpu_high or machine.ram_percent >= ram_high or machine.swap_used_mb >= swap_high:
            return max(1, min(degraded_sessions, available_runners or degraded_sessions))
        if machine.cpu_percent <= cpu_low and machine.load_state == "healthy":
            return max(1, min(max_sessions, available_runners or max_sessions))
        return max(1, min(default_sessions, available_runners or default_sessions))

    def required_proof_for(self, task: TaskRecord) -> list[str]:
        risk_key = f"{task.risk.replace('-', '_')}_requires"
        proof = self.policies.risk_policy.get(risk_key)
        return list(proof or task.required_verification)

