"""CUSUM (Cumulative Sum) drift detector for numerical baselines.

Tracks cumulative deltas over time. Triggers WARNING when gradual drift
accumulates past a threshold, before it crosses the hard FAIL boundary.

Statistical Process Control applied to CI — catches slow dependency-driven
drift that appears as a sudden break.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CUSUMState:
    """Per-project, per-value CUSUM accumulator."""
    key: str
    cusum_pos: float = 0.0  # Upward drift accumulator
    cusum_neg: float = 0.0  # Downward drift accumulator
    n_observations: int = 0
    last_delta: float = 0.0
    warning: bool = False
    drift_detected: bool = False


@dataclass
class CUSUMResult:
    """Result of CUSUM check across all values for one project."""
    project_id: str
    warnings: list[str] = field(default_factory=list)
    drifts: list[str] = field(default_factory=list)
    states: dict[str, CUSUMState] = field(default_factory=dict)

    @property
    def has_warning(self) -> bool:
        return len(self.warnings) > 0

    @property
    def has_drift(self) -> bool:
        return len(self.drifts) > 0


class CUSUMMonitor:
    """Monitors numerical baseline values for gradual drift using CUSUM."""

    def __init__(
        self,
        state_dir: Path,
        warning_threshold: float = 3.0,
        drift_threshold: float = 5.0,
        slack: float = 0.5,
    ) -> None:
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.warning_threshold = warning_threshold
        self.drift_threshold = drift_threshold
        self.slack = slack  # Allowable slack before accumulating

    def check(
        self,
        project_id: str,
        expected: dict,
        actual: dict,
        tolerance: float = 1e-6,
    ) -> CUSUMResult:
        """Compare actual vs expected values, updating CUSUM state.

        Returns CUSUMResult with any warnings or drift detections.
        """
        states = self._load_state(project_id)
        result = CUSUMResult(project_id=project_id)

        for key, exp_val in expected.items():
            act_val = actual.get(key)
            if not isinstance(exp_val, (int, float)) or not isinstance(act_val, (int, float)):
                continue

            # Normalized delta (relative to tolerance)
            if exp_val != 0:
                delta = abs(act_val - exp_val) / max(abs(exp_val), tolerance)
            else:
                delta = abs(act_val - exp_val) / tolerance

            state = states.get(key, CUSUMState(key=key))
            state.n_observations += 1
            state.last_delta = delta

            # CUSUM update: accumulate deviations above slack
            state.cusum_pos = max(0, state.cusum_pos + delta - self.slack)
            state.cusum_neg = max(0, state.cusum_neg - delta + self.slack)

            cusum_max = max(state.cusum_pos, abs(state.cusum_neg))

            if cusum_max >= self.drift_threshold:
                state.drift_detected = True
                state.warning = True
                result.drifts.append(
                    f"{key}: CUSUM={cusum_max:.2f} (threshold={self.drift_threshold}), "
                    f"last_delta={delta:.4f}, n={state.n_observations}"
                )
            elif cusum_max >= self.warning_threshold:
                state.warning = True
                result.warnings.append(
                    f"{key}: CUSUM={cusum_max:.2f} approaching drift threshold "
                    f"({self.drift_threshold}), last_delta={delta:.4f}"
                )
            else:
                state.warning = False
                state.drift_detected = False

            states[key] = state

        result.states = states
        self._save_state(project_id, states)
        return result

    def reset(self, project_id: str) -> None:
        """Reset CUSUM state for a project (e.g., after baseline regeneration)."""
        state_path = self.state_dir / f"{project_id[:20]}_cusum.json"
        if state_path.exists():
            state_path.unlink()

    def _load_state(self, project_id: str) -> dict[str, CUSUMState]:
        state_path = self.state_dir / f"{project_id[:20]}_cusum.json"
        if not state_path.exists():
            return {}
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return {k: CUSUMState(**v) for k, v in data.items()}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _save_state(self, project_id: str, states: dict[str, CUSUMState]) -> None:
        state_path = self.state_dir / f"{project_id[:20]}_cusum.json"
        data = {}
        for key, state in states.items():
            data[key] = {
                "key": state.key,
                "cusum_pos": state.cusum_pos,
                "cusum_neg": state.cusum_neg,
                "n_observations": state.n_observations,
                "last_delta": state.last_delta,
                "warning": state.warning,
                "drift_detected": state.drift_detected,
            }
        state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
