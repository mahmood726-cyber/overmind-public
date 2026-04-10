from __future__ import annotations

from overmind.config import AppConfig
from overmind.core.orchestrator import Orchestrator
from overmind.storage.models import ProjectRecord, TaskRecord


def test_dry_run_does_not_dispatch_or_transition(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    data_dir.mkdir()

    (config_dir / "roots.yaml").write_text("scan_roots: []\nscan_rules: {}\nguidance_filenames: []\n", encoding="utf-8")
    (config_dir / "runners.yaml").write_text("runners: []\n", encoding="utf-8")
    (config_dir / "policies.yaml").write_text(
        "concurrency:\n  default_active_sessions: 1\n  max_active_sessions: 1\n  degraded_sessions: 1\n"
        "  scale_up_cpu_below: 100\n  scale_down_cpu_above: 100\n  scale_down_ram_above: 100\n  scale_down_swap_above_mb: 999999\n"
        "limits:\n  idle_timeout_min: 10\n  summary_trigger_output_lines: 400\n"
        "routing: {}\nrisk_policy: {}\n",
        encoding="utf-8",
    )
    (config_dir / "projects_ignore.yaml").write_text("ignored_directories: []\nignored_file_suffixes: []\n", encoding="utf-8")
    (config_dir / "verification_profiles.yaml").write_text("profiles: {}\n", encoding="utf-8")

    config = AppConfig.from_directory(config_dir=config_dir, data_dir=data_dir, db_path=data_dir / "state.db")
    orchestrator = Orchestrator(config)
    try:
        project = ProjectRecord(
            project_id="dry-proj",
            name="Dry Project",
            root_path=str(tmp_path),
            project_type="python_tool",
            stack=["python"],
            test_commands=["python -m pytest -q"],
        )
        task = TaskRecord(
            task_id="task-dry",
            project_id=project.project_id,
            title="Dry run test",
            task_type="verification",
            source="test",
            priority=0.9,
            risk="medium",
            expected_runtime_min=1,
            expected_context_cost="low",
            required_verification=["relevant_tests"],
        )
        orchestrator.db.upsert_project(project)
        orchestrator.db.upsert_task(task)

        result = orchestrator.run_once(dry_run=True)

        assert result.get("dry_run") is True
        assert "would_dispatch" in result

        saved = orchestrator.db.get_task("task-dry")
        assert saved is not None
        assert saved.status == "QUEUED"

        assert orchestrator.session_manager.active_count() == 0
    finally:
        orchestrator.close()
