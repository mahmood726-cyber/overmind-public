from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class OverviewSchema:
    active_projects: int
    active_runners: int
    queued_tasks: int

