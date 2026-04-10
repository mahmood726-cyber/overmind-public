from __future__ import annotations

from overmind.memory.extractor import MemoryExtractor
from overmind.storage.db import StateDatabase
from overmind.storage.models import (
    EvidenceEvent,
    MemoryRecord,
    SessionEvidence,
    VerificationResult,
)


def test_extractor_produces_project_learning_on_verification_pass(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    extractor = MemoryExtractor(db)
    try:
        results = [
            VerificationResult(
                task_id="task-1",
                success=True,
                required_checks=["relevant_tests"],
                completed_checks=["relevant_tests"],
                skipped_checks=[],
                details=["relevant_tests: exit=0 command=pytest"],
            )
        ]
        memories = extractor.extract(
            evidence_items=[],
            verification_results=results,
            project_ids={"task-1": "proj-alpha"},
            runner_ids={},
            tick=1,
        )
        assert any(m.memory_type == "project_learning" for m in memories)
        assert any("proj-alpha" in m.scope for m in memories)
    finally:
        db.close()


def test_extractor_produces_regression_on_verification_fail(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    extractor = MemoryExtractor(db)
    try:
        results = [
            VerificationResult(
                task_id="task-2",
                success=False,
                required_checks=["relevant_tests"],
                completed_checks=[],
                skipped_checks=[],
                details=["relevant_tests: exit=1 command=pytest"],
            )
        ]
        memories = extractor.extract(
            evidence_items=[],
            verification_results=results,
            project_ids={"task-2": "proj-beta"},
            runner_ids={},
            tick=2,
        )
        assert any(m.memory_type == "regression" for m in memories)
    finally:
        db.close()


def test_extractor_produces_runner_learning_on_rate_limit(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    extractor = MemoryExtractor(db)
    try:
        evidence = [
            SessionEvidence(
                task_id="task-3",
                runner_id="codex_a",
                state="NEEDS_INTERVENTION",
                risks=["provider quota/rate limit detected"],
                next_action="pause",
                required_proof=[],
                events=[EvidenceEvent(kind="rate_limited", line="usage limit hit")],
                exited=True,
                exit_code=1,
            )
        ]
        memories = extractor.extract(
            evidence_items=evidence,
            verification_results=[],
            project_ids={},
            runner_ids={"task-3": "codex_a"},
            tick=3,
        )
        assert any(m.memory_type == "runner_learning" for m in memories)
        assert any("codex_a" in m.scope for m in memories)
    finally:
        db.close()


def test_extractor_produces_task_pattern_on_loop(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    extractor = MemoryExtractor(db)
    try:
        evidence = [
            SessionEvidence(
                task_id="task-4",
                runner_id="claude_main",
                state="NEEDS_INTERVENTION",
                risks=["repeated retry loop detected"],
                next_action="stop",
                required_proof=[],
                loop_detected=True,
            )
        ]
        memories = extractor.extract(
            evidence_items=evidence,
            verification_results=[],
            project_ids={"task-4": "proj-gamma"},
            runner_ids={"task-4": "claude_main"},
            tick=4,
        )
        assert any(m.memory_type == "task_pattern" for m in memories)
    finally:
        db.close()


def test_extractor_deduplicates_existing_memory(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    extractor = MemoryExtractor(db)
    try:
        existing = MemoryRecord(
            memory_id="mem_existing",
            memory_type="project_learning",
            scope="proj-alpha",
            title="Verification passed",
            content="proj-alpha verification passed on tick 1",
            relevance=0.5,
        )
        db.upsert_memory(existing)

        results = [
            VerificationResult(
                task_id="task-5",
                success=True,
                required_checks=["relevant_tests"],
                completed_checks=["relevant_tests"],
                skipped_checks=[],
                details=["relevant_tests: exit=0 command=pytest"],
            )
        ]
        extractor.extract(
            evidence_items=[],
            verification_results=results,
            project_ids={"task-5": "proj-alpha"},
            runner_ids={},
            tick=5,
        )
        boosted = db.get_memory("mem_existing")
        assert boosted is not None
        assert boosted.relevance > 0.5
    finally:
        db.close()


def test_extractor_produces_proof_gap_memory(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    extractor = MemoryExtractor(db)
    try:
        evidence = [
            SessionEvidence(
                task_id="task-6",
                runner_id="claude_main",
                state="VERIFYING",
                risks=["claim without proof"],
                next_action="verify",
                required_proof=["terminal-visible verification"],
                proof_gap=True,
            )
        ]
        memories = extractor.extract(
            evidence_items=evidence,
            verification_results=[],
            project_ids={"task-6": "proj-delta"},
            runner_ids={"task-6": "claude_main"},
            tick=6,
        )
        assert any(m.memory_type == "task_pattern" and "proof_gap" in m.tags for m in memories)
    finally:
        db.close()
