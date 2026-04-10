from __future__ import annotations

from overmind.memory.audit_loop import AuditLoop
from overmind.storage.db import StateDatabase
from overmind.storage.models import VerificationResult


def test_audit_loop_stores_snapshot(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    loop = AuditLoop(db)
    try:
        result = VerificationResult(
            task_id="t1", success=True,
            required_checks=["build", "test"],
            completed_checks=["build", "test"],
            skipped_checks=[], details=[],
        )
        assessment = loop.evaluate("proj-1", result, tick=1)
        assert assessment["current_pass_rate"] == 1.0
        assert assessment["trend"] == "baseline"

        snapshots = db.list_memories(scope="proj-1", memory_type="audit_snapshot")
        assert len(snapshots) == 1
    finally:
        db.close()


def test_audit_loop_detects_degradation(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    loop = AuditLoop(db)
    try:
        # Store 3 good results
        for i in range(3):
            good = VerificationResult(
                task_id=f"t{i}", success=True,
                required_checks=["build", "test"],
                completed_checks=["build", "test"],
                skipped_checks=[], details=[],
            )
            loop.evaluate("proj-1", good, tick=i+1)

        # Now a bad result
        bad = VerificationResult(
            task_id="t-bad", success=False,
            required_checks=["build", "test"],
            completed_checks=["build"],
            skipped_checks=["test"], details=[],
        )
        assessment = loop.evaluate("proj-1", bad, tick=4)
        assert assessment["trend"] == "degrading"
        assert assessment["delta"] < 0

        # Check regression memory was created
        regressions = db.list_memories(scope="proj-1", memory_type="regression")
        assert len(regressions) >= 1
    finally:
        db.close()


def test_audit_loop_detects_improvement(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    loop = AuditLoop(db)
    try:
        # Store 3 mediocre results (50% pass rate)
        for i in range(3):
            mediocre = VerificationResult(
                task_id=f"t{i}", success=False,
                required_checks=["build", "test"],
                completed_checks=["build"],
                skipped_checks=["test"], details=[],
            )
            loop.evaluate("proj-1", mediocre, tick=i+1)

        # Now a perfect result
        perfect = VerificationResult(
            task_id="t-good", success=True,
            required_checks=["build", "test"],
            completed_checks=["build", "test"],
            skipped_checks=[], details=[],
        )
        assessment = loop.evaluate("proj-1", perfect, tick=4)
        assert assessment["trend"] == "improving"
        assert assessment["delta"] > 0
    finally:
        db.close()


def test_project_history_returns_snapshots(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    loop = AuditLoop(db)
    try:
        result = VerificationResult(
            task_id="t1", success=True,
            required_checks=["test"],
            completed_checks=["test"],
            skipped_checks=[], details=[],
        )
        loop.evaluate("proj-1", result, tick=1)
        history = loop.project_history("proj-1")
        assert len(history) == 1
        assert "tick" in history[0]
    finally:
        db.close()
