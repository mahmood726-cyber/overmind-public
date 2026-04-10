from __future__ import annotations

from overmind.storage.models import EvidenceEvent


class FailureClassifier:
    def classify(
        self,
        events: list[EvidenceEvent],
        loop_detected: bool,
        proof_gap: bool,
        exit_code: int | None,
        idle_seconds: float,
        idle_timeout_seconds: float,
    ) -> tuple[str, list[str], str]:
        risks: list[str] = []
        has_terminal_failure = any(event.kind.endswith("failed") or event.kind == "timeout" for event in events)
        has_rate_limit = any(event.kind == "rate_limited" for event in events)
        if loop_detected:
            risks.append("repeated retry loop detected")
        if proof_gap:
            risks.append("claim without proof")
        if has_terminal_failure:
            risks.append("terminal-visible failure detected")
        if has_rate_limit:
            risks.append("provider quota/rate limit detected")
        if any(event.kind == "memory_warning" for event in events):
            risks.append("memory pressure detected")
        if any(event.kind == "numeric_warning" for event in events):
            risks.append("numeric stability warning detected")
        if any(event.kind == "locale_warning" for event in events):
            risks.append("locale configuration warning detected")
        if idle_seconds >= idle_timeout_seconds:
            risks.append("session idle beyond limit")

        if exit_code not in (None, 0):
            if has_rate_limit:
                return "NEEDS_INTERVENTION", risks, "pause runner until quota resets"
            return "NEEDS_INTERVENTION", risks or ["runner exited non-zero"], "change strategy before retry"
        if exit_code == 0 and not proof_gap and not has_terminal_failure:
            return "VERIFYING", risks, "verify before marking complete"
        if loop_detected:
            return "NEEDS_INTERVENTION", risks, "stop retrying and isolate the issue"
        if proof_gap:
            return "VERIFYING", risks, "run minimum meaningful verification"
        return "RUNNING", risks, "continue monitoring"
