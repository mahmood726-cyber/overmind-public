from __future__ import annotations

import uuid

from overmind.memory import embeddings
from overmind.storage.db import StateDatabase
from overmind.storage.models import (
    MemoryRecord,
    SessionEvidence,
    VerificationResult,
    utc_now,
)


class MemoryExtractor:
    def __init__(self, db: StateDatabase) -> None:
        self.db = db

    def extract(
        self,
        evidence_items: list[SessionEvidence],
        verification_results: list[VerificationResult],
        project_ids: dict[str, str],
        runner_ids: dict[str, str],
        tick: int,
    ) -> list[MemoryRecord]:
        memories: list[MemoryRecord] = []

        for result in verification_results:
            project_id = project_ids.get(result.task_id, "unknown")
            if result.success:
                memories.append(self._make(
                    memory_type="project_learning",
                    scope=project_id,
                    title="Verification passed",
                    content=f"{project_id} verification passed on tick {tick}. "
                            f"Checks: {', '.join(result.completed_checks)}.",
                    source_task_id=result.task_id,
                    tick=tick,
                    tags=["verification", "passed"] + result.completed_checks,
                ))
            else:
                details_text = "; ".join(result.details[:3])
                skipped_text = "; ".join(result.skipped_checks[:3])
                memories.append(self._make(
                    memory_type="regression",
                    scope=project_id,
                    title="Verification failed",
                    content=f"{project_id} verification failed on tick {tick}. "
                            f"Details: {details_text}. Skipped: {skipped_text}.",
                    source_task_id=result.task_id,
                    tick=tick,
                    tags=["verification", "failed", "regression"],
                    confidence=0.8,
                ))

        for evidence in evidence_items:
            runner_id = runner_ids.get(evidence.task_id, evidence.runner_id)
            project_id = project_ids.get(evidence.task_id, "unknown")

            if any(event.kind == "rate_limited" for event in evidence.events):
                memories.append(self._make(
                    memory_type="runner_learning",
                    scope=runner_id,
                    title="Rate limited",
                    content=f"{runner_id} hit rate limit on tick {tick}.",
                    source_task_id=evidence.task_id,
                    tick=tick,
                    tags=["rate_limit", runner_id],
                ))

            if evidence.loop_detected:
                memories.append(self._make(
                    memory_type="task_pattern",
                    scope=project_id,
                    title="Loop detected",
                    content=f"Task on {project_id} entered retry loop on tick {tick} "
                            f"(runner: {runner_id}). Risks: {', '.join(evidence.risks)}.",
                    source_task_id=evidence.task_id,
                    tick=tick,
                    tags=["loop", "retry", runner_id],
                ))

            if evidence.proof_gap:
                memories.append(self._make(
                    memory_type="task_pattern",
                    scope=project_id,
                    title="Proof gap detected",
                    content=f"Runner {runner_id} claimed completion on {project_id} "
                            f"without terminal-visible proof (tick {tick}).",
                    source_task_id=evidence.task_id,
                    tick=tick,
                    tags=["proof_gap", runner_id],
                ))

            if evidence.exited and evidence.exit_code not in (None, 0):
                if not any(event.kind == "rate_limited" for event in evidence.events):
                    memories.append(self._make(
                        memory_type="runner_learning",
                        scope=runner_id,
                        title="Non-zero exit",
                        content=f"{runner_id} exited with code {evidence.exit_code} "
                                f"on {project_id} (tick {tick}). "
                                f"Risks: {', '.join(evidence.risks[:3])}.",
                        source_task_id=evidence.task_id,
                        tick=tick,
                        tags=["exit_error", runner_id],
                    ))

        self._deduplicate_and_save(memories)
        return memories

    def _make(
        self,
        memory_type: str,
        scope: str,
        title: str,
        content: str,
        source_task_id: str | None = None,
        tick: int = 0,
        tags: list[str] | None = None,
        confidence: float = 0.5,
    ) -> MemoryRecord:
        now = utc_now()
        embed_text = f"{title}. {content}"
        return MemoryRecord(
            memory_id=f"mem_{uuid.uuid4().hex[:8]}",
            memory_type=memory_type,
            scope=scope,
            title=title,
            content=content,
            source_task_id=source_task_id,
            source_tick=tick,
            tags=tags or [],
            confidence=confidence,
            valid_from=now,
            embedding=embeddings.embed(embed_text),
        )

    def _deduplicate_and_save(self, memories: list[MemoryRecord]) -> None:
        for memory in memories:
            existing = self.db.list_memories(
                scope=memory.scope,
                memory_type=memory.memory_type,
                limit=20,
            )
            duplicate = self._find_duplicate(memory, existing)
            if duplicate:
                duplicate.relevance = round(min(1.0, duplicate.relevance + 0.15), 4)
                duplicate.confidence = round(min(1.0, duplicate.confidence + 0.05), 4)
                duplicate.content = f"{duplicate.content} Confirmed tick {memory.source_tick}."
                duplicate.updated_at = utc_now()
                for tag in memory.tags:
                    if tag not in duplicate.tags:
                        duplicate.tags.append(tag)
                self.db.upsert_memory(duplicate)
            else:
                self.db.upsert_memory(memory)

    def _find_duplicate(self, candidate: MemoryRecord, existing: list[MemoryRecord]) -> MemoryRecord | None:
        candidate_words = set(candidate.title.lower().split())
        for memory in existing:
            existing_words = set(memory.title.lower().split())
            union = candidate_words | existing_words
            if not union:
                continue
            overlap = len(candidate_words & existing_words)
            if overlap / len(union) >= 0.6:
                return memory
        return None
