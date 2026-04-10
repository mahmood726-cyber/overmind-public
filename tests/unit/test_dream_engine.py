from __future__ import annotations

from overmind.memory.dream_engine import DreamEngine
from overmind.memory.heuristic_engine import HeuristicEngine
from overmind.storage.db import StateDatabase
from overmind.storage.models import MemoryRecord


def test_dream_merges_duplicate_memories(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    try:
        for i in range(3):
            db.upsert_memory(MemoryRecord(
                memory_id=f"mem_dup_{i}",
                memory_type="project_learning",
                scope="proj-1",
                title="Verification passed",
                content=f"proj-1 verification passed on tick {i + 1}.",
                relevance=0.8 - i * 0.1,
                tags=["verification", "passed"],
            ))

        engine = DreamEngine(db)
        summary = engine.dream()

        assert summary["merges"] > 0
        active = db.list_memories(status="active", scope="proj-1")
        assert len(active) < 3
    finally:
        db.close()


def test_dream_archives_low_relevance_memories(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    try:
        db.upsert_memory(MemoryRecord(
            memory_id="mem_stale",
            memory_type="runner_learning",
            scope="codex_a",
            title="Rate limited once",
            content="codex_a hit rate limit.",
            relevance=0.05,
        ))

        engine = DreamEngine(db)
        summary = engine.dream()

        assert summary["archives"] >= 1
        stale = db.get_memory("mem_stale")
        assert stale is not None
        assert stale.status == "archived"
    finally:
        db.close()


def test_dream_generates_heuristics_from_patterns(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    try:
        for i in range(4):
            db.upsert_memory(MemoryRecord(
                memory_id=f"mem_loop_{i}",
                memory_type="task_pattern",
                scope="proj-browser",
                title="Loop detected",
                content=f"Task entered retry loop on tick {i} (runner: codex_a).",
                tags=["loop", "retry", "codex_a"],
            ))

        engine = DreamEngine(db)
        summary = engine.dream()

        assert summary["heuristics_generated"] >= 1
        heuristics = db.list_memories(memory_type="heuristic")
        assert len(heuristics) >= 1
        assert "loop" in heuristics[0].content.lower() or "retry" in heuristics[0].content.lower()
    finally:
        db.close()


def test_heuristic_engine_requires_minimum_pattern_count(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    try:
        db.upsert_memory(MemoryRecord(
            memory_id="mem_single",
            memory_type="task_pattern",
            scope="proj-x",
            title="Loop detected",
            content="Single occurrence.",
            tags=["loop"],
        ))

        engine = HeuristicEngine(db)
        heuristics = engine.generate()

        assert len(heuristics) == 0
    finally:
        db.close()


def test_dream_should_dream_conditions():
    from overmind.memory.dream_engine import DreamEngine
    db = None  # not needed for should_dream
    engine = DreamEngine.__new__(DreamEngine)

    assert engine.should_dream(ticks_since_last=5, active_memory_count=10) is True
    assert engine.should_dream(ticks_since_last=4, active_memory_count=10) is False
    assert engine.should_dream(ticks_since_last=5, active_memory_count=9) is False
    assert engine.should_dream(ticks_since_last=10, active_memory_count=50) is True


def test_dream_full_cycle_summary_shape(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    try:
        db.upsert_memory(MemoryRecord(
            memory_id="mem_fc1",
            memory_type="project_learning",
            scope="proj-a",
            title="Test passed",
            content="All good.",
        ))

        engine = DreamEngine(db)
        summary = engine.dream()

        assert "last_dream_at" in summary
        assert "memories_before" in summary
        assert "memories_after" in summary
        assert "merges" in summary
        assert "heuristics_generated" in summary
        assert "archives" in summary
    finally:
        db.close()
