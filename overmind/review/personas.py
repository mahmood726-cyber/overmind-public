from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ReviewPersona:
    name: str
    focus: str
    prompt_file: str
    preferred_runner_type: str
    priority: int  # lower = reviewed first


PERSONAS = [
    ReviewPersona(
        name="correctness",
        focus="Logic errors, edge cases, spec compliance",
        prompt_file="correctness.txt",
        preferred_runner_type="claude",
        priority=1,
    ),
    ReviewPersona(
        name="statistical_rigor",
        focus="Math correctness, numerical stability, statistical assumptions",
        prompt_file="statistical_rigor.txt",
        preferred_runner_type="claude",
        priority=2,
    ),
    ReviewPersona(
        name="security",
        focus="Secrets, injection, OWASP, path traversal",
        prompt_file="security.txt",
        preferred_runner_type="codex",
        priority=3,
    ),
    ReviewPersona(
        name="robustness",
        focus="Error handling, platform issues, failure modes",
        prompt_file="robustness.txt",
        preferred_runner_type="gemini",
        priority=4,
    ),
    ReviewPersona(
        name="efficiency",
        focus="Token waste, redundant ops, YAGNI, complexity",
        prompt_file="efficiency.txt",
        preferred_runner_type="codex",
        priority=5,
    ),
]


def personas_for_project(
    has_advanced_math: bool,
    risk_profile: str,
) -> list[ReviewPersona]:
    """Select which personas to run based on project characteristics."""
    selected = [PERSONAS[0]]  # correctness always runs

    if has_advanced_math:
        selected.append(PERSONAS[1])  # statistical_rigor

    if risk_profile in ("high", "medium_high"):
        selected.append(PERSONAS[2])  # security
        selected.append(PERSONAS[3])  # robustness

    selected.append(PERSONAS[4])  # efficiency always runs

    return sorted(selected, key=lambda p: p.priority)
