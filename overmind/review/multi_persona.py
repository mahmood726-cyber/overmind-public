from __future__ import annotations

import uuid
from pathlib import Path

from overmind.review.finding import (
    ConsensusResult,
    PersonaReviewResult,
    compute_consensus,
    parse_review_output,
)
from overmind.review.personas import ReviewPersona, personas_for_project
from overmind.storage.db import StateDatabase
from overmind.storage.models import MemoryRecord, ProjectRecord, TaskRecord, utc_now


class MultiPersonaReviewer:
    def __init__(self, db: StateDatabase, prompts_dir: Path | None = None) -> None:
        self.db = db
        self.prompts_dir = prompts_dir or (
            Path(__file__).resolve().parents[1] / "prompts" / "review"
        )

    def select_personas(self, project: ProjectRecord) -> list[ReviewPersona]:
        """Select review personas based on project characteristics."""
        return personas_for_project(
            has_advanced_math=project.has_advanced_math,
            risk_profile=project.risk_profile,
        )

    def build_review_prompt(
        self,
        persona: ReviewPersona,
        project: ProjectRecord,
        task: TaskRecord,
        changes_summary: str = "",
    ) -> str:
        """Build the review prompt for a specific persona."""
        prompt_path = self.prompts_dir / persona.prompt_file
        if not prompt_path.exists():
            return f"Review this code as a {persona.name} reviewer."

        template = prompt_path.read_text(encoding="utf-8")
        return template.format(
            project_name=project.name,
            project_path=project.root_path,
            task_title=task.title,
            changes_summary=changes_summary or "See task description.",
            math_signals=", ".join(project.advanced_math_signals) if project.advanced_math_signals else "none",
        )

    def preferred_runner_for(
        self,
        persona: ReviewPersona,
        writer_runner_type: str,
    ) -> str:
        """Return the preferred runner type for review, ensuring cross-model dispatch."""
        preferred = persona.preferred_runner_type
        if preferred == writer_runner_type:
            # Cross-model: pick a different runner type
            alternatives = {"claude", "codex", "gemini"} - {writer_runner_type}
            return sorted(alternatives)[0]  # deterministic fallback
        return preferred

    def process_review_output(
        self,
        persona: ReviewPersona,
        raw_output: str,
    ) -> PersonaReviewResult:
        """Parse raw review output into structured findings."""
        return parse_review_output(persona.name, raw_output)

    def compute_consensus(
        self,
        results: list[PersonaReviewResult],
    ) -> ConsensusResult:
        """Aggregate all persona results into a consensus verdict."""
        return compute_consensus(results)

    def store_review_memory(
        self,
        project_id: str,
        task_id: str,
        consensus: ConsensusResult,
        tick: int,
    ) -> None:
        """Store review results as a memory for future reference."""
        findings_text = []
        for finding in consensus.consensus_findings[:5]:
            personas = ", ".join(finding["personas"])
            findings_text.append(
                f"[{finding['severity']}] {finding['description']} (by: {personas})"
            )

        content = (
            f"Multi-persona review on tick {tick}: "
            f"verdict={consensus.overall_verdict}, "
            f"P0={consensus.p0_count}, P1={consensus.p1_count}, P2={consensus.p2_count}. "
            f"Findings: {'; '.join(findings_text) or 'none'}."
        )

        memory = MemoryRecord(
            memory_id=f"review_{uuid.uuid4().hex[:8]}",
            memory_type="decision",
            scope=project_id,
            title=f"Review: {consensus.overall_verdict} ({consensus.p0_count}P0/{consensus.p1_count}P1/{consensus.p2_count}P2)",
            content=content,
            source_task_id=task_id,
            source_tick=tick,
            tags=["review", "multi_persona", consensus.overall_verdict.lower()],
            confidence=0.9,
        )
        self.db.upsert_memory(memory)
