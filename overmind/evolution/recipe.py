"""Recipe model for procedural memory."""
from __future__ import annotations

from dataclasses import dataclass, field

from overmind.storage.models import utc_now


@dataclass
class Recipe:
    recipe_id: str
    failure_type: str
    pattern: str
    fix_description: str
    times_seen: int = 1
    times_resolved: int = 0
    confidence: float = 0.0
    last_seen: str = ""
    first_seen: str = ""
    example_project: str = ""
    # PRAXIS: outcome history — True=stayed healthy, False=broke again
    outcome_history: list = field(default_factory=list)
    # MACLA: contrastive refinement — what changed between fail and success
    contrastive_diff: str = ""
    # Mem^p: two-level abstraction
    abstract_strategy: str = ""

    def __post_init__(self):
        if not self.last_seen:
            self.last_seen = utc_now()
        if not self.first_seen:
            self.first_seen = self.last_seen
        self._update_confidence()

    def record_seen(self, date: str) -> None:
        self.times_seen += 1
        self.last_seen = date

    def record_resolved(self, diff: str = "") -> None:
        self.times_resolved += 1
        if diff:
            self.contrastive_diff = diff  # MACLA: store what changed
        self._update_confidence()

    def record_outcome(self, healthy: bool) -> None:
        """PRAXIS: record whether the fix held on subsequent nights."""
        self.outcome_history.append(healthy)
        # Decay confidence if fix keeps failing after being applied
        if len(self.outcome_history) >= 3:
            recent = self.outcome_history[-3:]
            if not any(recent):  # 3 consecutive failures after fix
                self.confidence = max(0, self.confidence - 0.1)

    def is_proven(self) -> bool:
        return self.times_seen >= 2 and self.confidence > 0

    @property
    def durability(self) -> float:
        """PRAXIS: what fraction of outcomes stayed healthy after fix."""
        if not self.outcome_history:
            return 1.0
        return sum(self.outcome_history) / len(self.outcome_history)

    def _update_confidence(self) -> None:
        if self.times_seen > 0:
            self.confidence = round(self.times_resolved / self.times_seen, 2)
