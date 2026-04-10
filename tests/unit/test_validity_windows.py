"""Tests for validity window fields on MemoryRecord."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from overmind.memory.store import MemoryStore
from overmind.storage.db import StateDatabase
from overmind.storage.models import MemoryRecord, utc_now


def _past(hours: int = 1) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).replace(microsecond=0).isoformat()


def _future(hours: int = 1) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).replace(microsecond=0).isoformat()


def test_validity_fields_roundtrip(tmp_path):
    """valid_from / valid_until survive upsert -> get."""
    db = StateDatabase(tmp_path / "test.db")
    try:
        now = utc_now()
        future = _future(24)
        db.upsert_memory(MemoryRecord(
            memory_id="mem_val1",
            memory_type="project_learning",
            scope="proj-a",
            title="Valid window test",
            content="Testing validity.",
            valid_from=now,
            valid_until=future,
        ))
        loaded = db.get_memory("mem_val1")
        assert loaded is not None
        assert loaded.valid_from == now
        assert loaded.valid_until == future
    finally:
        db.close()


def test_expired_memories_excluded_from_list(tmp_path):
    """list_memories excludes memories past their valid_until."""
    db = StateDatabase(tmp_path / "test.db")
    try:
        db.upsert_memory(MemoryRecord(
            memory_id="mem_exp1",
            memory_type="project_learning",
            scope="proj-a",
            title="Expired memory",
            content="This expired an hour ago.",
            valid_from=_past(48),
            valid_until=_past(1),
        ))
        db.upsert_memory(MemoryRecord(
            memory_id="mem_exp2",
            memory_type="project_learning",
            scope="proj-a",
            title="Still valid memory",
            content="This is still valid.",
            valid_from=_past(1),
            valid_until=_future(24),
        ))
        db.upsert_memory(MemoryRecord(
            memory_id="mem_exp3",
            memory_type="project_learning",
            scope="proj-a",
            title="No expiry",
            content="This never expires.",
        ))

        results = db.list_memories()
        ids = {m.memory_id for m in results}
        assert "mem_exp2" in ids
        assert "mem_exp3" in ids
        assert "mem_exp1" not in ids
    finally:
        db.close()


def test_expired_memories_included_with_flag(tmp_path):
    """list_memories with include_expired=True returns expired memories."""
    db = StateDatabase(tmp_path / "test.db")
    try:
        db.upsert_memory(MemoryRecord(
            memory_id="mem_ie1",
            memory_type="project_learning",
            scope="proj-a",
            title="Expired but included",
            content="Past valid_until.",
            valid_from=_past(48),
            valid_until=_past(1),
        ))
        results = db.list_memories(include_expired=True)
        ids = {m.memory_id for m in results}
        assert "mem_ie1" in ids
    finally:
        db.close()


def test_expired_memories_excluded_from_search(tmp_path):
    """search_memories excludes expired memories."""
    db = StateDatabase(tmp_path / "test.db")
    try:
        db.upsert_memory(MemoryRecord(
            memory_id="mem_se1",
            memory_type="project_learning",
            scope="proj-a",
            title="Expired test run",
            content="Expired test memory for search.",
            valid_from=_past(48),
            valid_until=_past(1),
        ))
        db.upsert_memory(MemoryRecord(
            memory_id="mem_se2",
            memory_type="project_learning",
            scope="proj-a",
            title="Active test run",
            content="Active test memory for search.",
            valid_from=_past(1),
            valid_until=_future(24),
        ))
        results = db.search_memories("test")
        ids = {m.memory_id for m in results}
        assert "mem_se2" in ids
        assert "mem_se1" not in ids
    finally:
        db.close()


def test_expire_memories_transitions_status(tmp_path):
    """expire_memories() moves past-due memories to 'expired' status."""
    db = StateDatabase(tmp_path / "test.db")
    try:
        db.upsert_memory(MemoryRecord(
            memory_id="mem_et1",
            memory_type="project_learning",
            scope="proj-a",
            title="Should expire",
            content="This should transition to expired.",
            valid_until=_past(1),
        ))
        db.upsert_memory(MemoryRecord(
            memory_id="mem_et2",
            memory_type="project_learning",
            scope="proj-a",
            title="Should stay active",
            content="This should remain active.",
            valid_until=_future(24),
        ))

        count = db.expire_memories()
        assert count >= 1

        mem1 = db.get_memory("mem_et1")
        assert mem1 is not None
        assert mem1.status == "expired"

        mem2 = db.get_memory("mem_et2")
        assert mem2 is not None
        assert mem2.status == "active"
    finally:
        db.close()


def test_supersede_closes_old_opens_new(tmp_path):
    """supersede() expires old memory and saves new one linked back."""
    db = StateDatabase(tmp_path / "test.db")
    store = MemoryStore(db=db, checkpoints_dir=tmp_path / "cp", logs_dir=tmp_path / "logs")
    try:
        store.save(MemoryRecord(
            memory_id="mem_old",
            memory_type="project_learning",
            scope="proj-a",
            title="Project uses pytest",
            content="proj-a runs tests with pytest.",
            valid_from=_past(48),
        ))
        new_mem = MemoryRecord(
            memory_id="mem_new",
            memory_type="project_learning",
            scope="proj-a",
            title="Project uses vitest",
            content="proj-a switched to vitest.",
        )
        result = store.supersede("mem_old", new_mem)
        assert result is True

        old = store.get("mem_old")
        assert old is not None
        assert old.status == "expired"
        assert old.valid_until is not None

        new = store.get("mem_new")
        assert new is not None
        assert new.valid_from is not None
        assert "mem_old" in new.linked_memories
    finally:
        db.close()


def test_supersede_nonexistent_returns_false(tmp_path):
    """supersede() returns False when old memory doesn't exist."""
    db = StateDatabase(tmp_path / "test.db")
    store = MemoryStore(db=db, checkpoints_dir=tmp_path / "cp", logs_dir=tmp_path / "logs")
    try:
        result = store.supersede("nonexistent", MemoryRecord(
            memory_id="mem_orphan",
            memory_type="project_learning",
            scope="proj-a",
            title="Orphan",
            content="No parent.",
        ))
        assert result is False
    finally:
        db.close()


def test_dream_expires_memories_in_cycle(tmp_path):
    """Dream engine expires memories during consolidation."""
    from overmind.memory.dream_engine import DreamEngine

    db = StateDatabase(tmp_path / "test.db")
    try:
        db.upsert_memory(MemoryRecord(
            memory_id="mem_dream_exp",
            memory_type="project_learning",
            scope="proj-a",
            title="Will expire in dream",
            content="Past due.",
            valid_until=_past(1),
        ))
        db.upsert_memory(MemoryRecord(
            memory_id="mem_dream_ok",
            memory_type="project_learning",
            scope="proj-a",
            title="Stays active",
            content="Still valid.",
        ))

        engine = DreamEngine(db)
        summary = engine.dream()
        assert summary.get("expired", 0) >= 1

        mem = db.get_memory("mem_dream_exp")
        assert mem is not None
        assert mem.status == "expired"
    finally:
        db.close()
