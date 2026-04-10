from __future__ import annotations

from overmind.storage.db import StateDatabase


class QRouter:
    def __init__(self, db: StateDatabase) -> None:
        self.db = db

    def score(self, runner_type: str, task_type: str) -> float:
        return self.db.get_routing_score(runner_type, task_type)

    def record(self, runner_type: str, task_type: str, success: bool) -> None:
        self.db.update_routing_score(runner_type, task_type, success)

    def scores_table(self) -> list[dict]:
        return self.db.list_routing_scores()
