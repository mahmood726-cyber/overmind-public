from __future__ import annotations


TASK_TRANSITIONS = {
    "DISCOVERED": {"QUEUED", "PAUSED", "ARCHIVED"},
    "QUEUED": {"ASSIGNED", "PAUSED", "ARCHIVED"},
    "ASSIGNED": {"RUNNING", "BLOCKED", "FAILED", "PAUSED"},
    "RUNNING": {"NEEDS_INTERVENTION", "VERIFYING", "BLOCKED", "FAILED", "PAUSED"},
    "NEEDS_INTERVENTION": {"ASSIGNED", "BLOCKED", "FAILED", "PAUSED"},
    "VERIFYING": {"COMPLETED", "FAILED", "BLOCKED", "PAUSED"},
    "BLOCKED": {"ASSIGNED", "PAUSED", "FAILED", "ARCHIVED"},
    "COMPLETED": {"ARCHIVED"},
    "FAILED": {"QUEUED", "ARCHIVED"},
    "PAUSED": {"QUEUED", "ARCHIVED"},
    "ARCHIVED": set(),
}


def assert_valid_task_transition(current: str, target: str) -> None:
    if current == target:
        return
    allowed = TASK_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValueError(f"Invalid task transition: {current} -> {target}")

