from __future__ import annotations

import sys
from pathlib import Path

import pytest

from overmind.config import AppConfig
from overmind.discovery.project_scanner import ProjectScanner
from overmind.storage.db import StateDatabase
from overmind.storage.models import ProjectRecord, TaskRecord
from overmind.verification.verifier import VerificationEngine


def _make_config(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir(exist_ok=True)
    data_dir.mkdir(exist_ok=True)
    (config_dir / "roots.yaml").write_text("scan_roots: []\nscan_rules: {}\nguidance_filenames: []\n", encoding="utf-8")
    (config_dir / "runners.yaml").write_text("runners: []\n", encoding="utf-8")
    (config_dir / "policies.yaml").write_text(
        "concurrency:\n  default_active_sessions: 1\n  max_active_sessions: 1\n  degraded_sessions: 1\n"
        "limits:\n  idle_timeout_min: 10\n  summary_trigger_output_lines: 400\n"
        "routing: {}\nrisk_policy: {}\n",
        encoding="utf-8",
    )
    (config_dir / "projects_ignore.yaml").write_text("ignored_directories: []\nignored_file_suffixes: []\n", encoding="utf-8")
    (config_dir / "verification_profiles.yaml").write_text("profiles: {}\n", encoding="utf-8")
    return AppConfig.from_directory(config_dir=config_dir, data_dir=data_dir, db_path=data_dir / "state.db")


# P0-1: Prompts included in package
def test_prompts_directory_contains_worker_prompt():
    prompts_dir = Path(__file__).resolve().parents[2] / "overmind" / "prompts"
    worker_prompt = prompts_dir / "worker_prompt.txt"
    assert worker_prompt.exists()
    text = worker_prompt.read_text(encoding="utf-8")
    assert "{project_name}" in text
    assert "{required_verification}" in text
    assert "{prior_learnings}" in text


# P0-3: Consistent tuple lengths
def test_command_priority_returns_consistent_tuple_lengths(tmp_path):
    config = _make_config(tmp_path)
    scanner = ProjectScanner(config)

    test_tuple = scanner._command_priority("test", "python -m pytest -q")
    browser_tuple = scanner._command_priority("browser", "npx playwright test")
    other_tuple = scanner._command_priority("build", "npm run build")

    assert len(test_tuple) == len(browser_tuple) == len(other_tuple), (
        f"Tuple lengths differ: test={len(test_tuple)}, browser={len(browser_tuple)}, other={len(other_tuple)}"
    )


# P1-1: Verifier timeout handling
def test_verifier_handles_command_timeout(tmp_path):
    hang_script = tmp_path / "hang.py"
    hang_script.write_text("import time; time.sleep(999)\n", encoding="utf-8")

    project = ProjectRecord(
        project_id="timeout-project",
        name="Timeout Project",
        root_path=str(tmp_path),
        project_type="python_tool",
        stack=["python"],
        test_commands=[f'"{sys.executable}" "{hang_script}"'],
    )
    task = TaskRecord(
        task_id="task-timeout",
        project_id=project.project_id,
        title="Verify timeout project",
        task_type="verification",
        source="test",
        priority=0.9,
        risk="medium",
        expected_runtime_min=1,
        expected_context_cost="low",
        required_verification=["relevant_tests"],
    )

    engine = VerificationEngine(tmp_path / "artifacts", verification_timeout=2)
    result = engine.run(task, project)

    assert result.success is False
    assert any("timed out" in detail for detail in result.details)


# P1-2: SQL table name whitelist
def test_db_rejects_invalid_table_names(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    try:
        with pytest.raises(ValueError, match="Invalid table name"):
            db._upsert("users; DROP TABLE projects --", "id-1", {"key": "val"})
        with pytest.raises(ValueError, match="Invalid table name"):
            db._get("nonexistent_table", "id-1", dict)
        with pytest.raises(ValueError, match="Invalid table name"):
            db._list("nonexistent_table", dict)
    finally:
        db.close()


# P1-3: Empty candidates in _last_active_timestamp
def test_last_active_timestamp_returns_none_for_empty_project(tmp_path):
    config = _make_config(tmp_path)
    scanner = ProjectScanner(config)
    empty_dir = tmp_path / "empty_project"
    empty_dir.mkdir()
    result = scanner._last_active_timestamp(empty_dir, [], [])
    assert result is None


def test_last_active_timestamp_handles_nonexistent_guidance_files(tmp_path):
    config = _make_config(tmp_path)
    scanner = ProjectScanner(config)
    project_dir = tmp_path / "project_with_missing_guidance"
    project_dir.mkdir()
    result = scanner._last_active_timestamp(
        project_dir,
        guidance_files=["NONEXISTENT.md"],
        activity_files=["/fake/path/to/nothing.log"],
    )
    assert result is None
