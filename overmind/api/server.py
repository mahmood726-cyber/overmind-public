from __future__ import annotations

from overmind.core.orchestrator import Orchestrator


def build_dashboard_payload(orchestrator: Orchestrator) -> dict[str, object]:
    return orchestrator.show_state()

