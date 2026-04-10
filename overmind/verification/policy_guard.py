"""Real-time policy enforcement for agent terminal output.

Inspired by Cupcake (EQTY Lab): intercepts dangerous commands in terminal
output before they cause harm.  Pure Python pattern matching — no Wasm/Rego.

Integrates into Orchestrator._decide_interventions() to generate block/warn
actions alongside existing loop and proof-gap interventions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from overmind.storage.models import utc_now

Severity = Literal["block", "warn", "review"]


@dataclass(slots=True)
class PolicyRule:
    name: str
    pattern: re.Pattern[str]
    severity: Severity
    message: str


@dataclass(slots=True)
class PolicyViolation:
    rule_name: str
    severity: Severity
    matched_line: str
    message: str
    created_at: str = field(default_factory=utc_now)


# ── Default rule set ────────────────────────────────────────────────

DEFAULT_RULES: list[PolicyRule] = [
    # Destructive filesystem
    PolicyRule(
        "rm_recursive_root",
        re.compile(r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/(?!\w)", re.IGNORECASE),
        "block",
        "Blocked: recursive delete targeting root filesystem",
    ),
    PolicyRule(
        "rm_rf_broad",
        re.compile(r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f?\s+\.\s*$", re.IGNORECASE),
        "block",
        "Blocked: rm -rf on current directory",
    ),
    # Destructive git
    PolicyRule(
        "git_force_push",
        re.compile(r"git\s+push\s+.*--force(?!-with-lease)", re.IGNORECASE),
        "block",
        "Blocked: force push without --force-with-lease",
    ),
    PolicyRule(
        "git_reset_hard",
        re.compile(r"git\s+reset\s+--hard", re.IGNORECASE),
        "warn",
        "Warning: git reset --hard may discard uncommitted work",
    ),
    PolicyRule(
        "git_clean_force",
        re.compile(r"git\s+clean\s+-[a-zA-Z]*f", re.IGNORECASE),
        "warn",
        "Warning: git clean -f removes untracked files permanently",
    ),
    # Credential exposure
    PolicyRule(
        "secret_echo",
        re.compile(
            r"(echo|printf|cat)\s+.*\b(api[_-]?key|secret|password|token|credential)\b",
            re.IGNORECASE,
        ),
        "block",
        "Blocked: potential credential exposure via stdout",
    ),
    PolicyRule(
        "env_secret_set",
        re.compile(
            r"export\s+(API[_-]?KEY|SECRET|PASSWORD|TOKEN|AWS_SECRET)\s*=",
            re.IGNORECASE,
        ),
        "warn",
        "Warning: setting secret in environment variable via terminal",
    ),
    # Process/system
    PolicyRule(
        "kill_all",
        re.compile(r"(kill\s+-9\s+-1|killall\s)", re.IGNORECASE),
        "block",
        "Blocked: mass process kill",
    ),
    PolicyRule(
        "chmod_world_writable",
        re.compile(r"chmod\s+[0-7]*7[0-7]*[0-7]\s", re.IGNORECASE),
        "warn",
        "Warning: world-writable permission change",
    ),
    # Database
    PolicyRule(
        "drop_database",
        re.compile(r"DROP\s+(DATABASE|TABLE|SCHEMA)\s", re.IGNORECASE),
        "block",
        "Blocked: destructive database DDL",
    ),
    # Network
    PolicyRule(
        "curl_pipe_shell",
        re.compile(r"curl\s+.*\|\s*(ba)?sh", re.IGNORECASE),
        "warn",
        "Warning: piping remote content to shell",
    ),
]


class PolicyGuard:
    """Evaluate terminal output lines against a set of policy rules."""

    def __init__(self, rules: list[PolicyRule] | None = None) -> None:
        self.rules = rules if rules is not None else list(DEFAULT_RULES)

    def evaluate(self, lines: list[str]) -> list[PolicyViolation]:
        """Check lines against all rules.  Returns violations sorted by severity."""
        violations: list[PolicyViolation] = []
        for line in lines:
            for rule in self.rules:
                if rule.pattern.search(line):
                    violations.append(
                        PolicyViolation(
                            rule_name=rule.name,
                            severity=rule.severity,
                            matched_line=line.strip()[:200],
                            message=rule.message,
                        )
                    )
        severity_order: dict[str, int] = {"block": 0, "warn": 1, "review": 2}
        violations.sort(key=lambda v: severity_order.get(v.severity, 9))
        return violations

    def has_blocks(self, violations: list[PolicyViolation]) -> bool:
        """Return True if any violation has 'block' severity."""
        return any(v.severity == "block" for v in violations)

    def to_interventions(
        self, violations: list[PolicyViolation], task_id: str
    ) -> list[dict[str, str]]:
        """Convert violations to Overmind intervention dicts."""
        interventions: list[dict[str, str]] = []
        for v in violations:
            if v.severity == "block":
                interventions.append({
                    "task_id": task_id,
                    "action": "send_message",
                    "message": f"POLICY VIOLATION [{v.rule_name}]: {v.message}. "
                               f"Matched: {v.matched_line[:100]}. "
                               "Stop this action immediately.",
                })
            elif v.severity == "warn":
                interventions.append({
                    "task_id": task_id,
                    "action": "send_message",
                    "message": f"POLICY WARNING [{v.rule_name}]: {v.message}. "
                               f"Matched: {v.matched_line[:100]}. "
                               "Proceed with caution.",
                })
        return interventions
