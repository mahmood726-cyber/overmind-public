from __future__ import annotations

from overmind.storage.models import ProjectRecord, SessionEvidence, TaskRecord


class ContextSummaries:
    def build_packet(
        self,
        project: ProjectRecord,
        task: TaskRecord,
        evidence: SessionEvidence | None = None,
    ) -> str:
        facts = [
            f"- build commands: {', '.join(project.build_commands) or 'none'}",
            f"- test commands: {', '.join(project.test_commands) or 'none'}",
            f"- browser commands: {', '.join(project.browser_test_commands) or 'none'}",
        ]
        if evidence:
            facts.extend(f"- risk: {risk}" for risk in evidence.risks[:3])
        return "\n".join(
            [
                f"TASK:\n{task.title}",
                "KNOWN FACTS:",
                *facts,
                "NEXT GOAL:",
                "Produce terminal-visible proof for the required verification.",
            ]
        )

