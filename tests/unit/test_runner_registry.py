from __future__ import annotations

import sys

from overmind.config import AppConfig
from overmind.runners.runner_registry import RunnerRegistry
from overmind.storage.db import StateDatabase


def test_runner_registry_holds_rate_limited_runner_in_cooldown(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    data_dir.mkdir()

    (config_dir / "roots.yaml").write_text(
        "scan_roots: []\n"
        "scan_rules:\n"
        "  include_git_repos: true\n"
        "  include_non_git_apps: true\n"
        "  incremental_scan: true\n"
        "  max_depth: 2\n"
        "guidance_filenames:\n"
        "  - \"README.md\"\n",
        encoding="utf-8",
    )
    (config_dir / "runners.yaml").write_text(
        "runners:\n"
        "  - runner_id: codex_test\n"
        "    type: codex\n"
        "    mode: terminal\n"
        f"    command: '\"{sys.executable}\" -V'\n"
        "    environment: windows\n",
        encoding="utf-8",
    )
    (config_dir / "policies.yaml").write_text(
        "concurrency:\n  default_active_sessions: 1\n  max_active_sessions: 1\n  degraded_sessions: 1\n"
        "limits:\n  idle_timeout_min: 10\n  summary_trigger_output_lines: 400\n"
        "routing: {}\n"
        "risk_policy: {}\n",
        encoding="utf-8",
    )
    (config_dir / "projects_ignore.yaml").write_text("ignored_directories: []\nignored_file_suffixes: []\n", encoding="utf-8")
    (config_dir / "verification_profiles.yaml").write_text("profiles: {}\nproject_rules: []\n", encoding="utf-8")

    config = AppConfig.from_directory(config_dir=config_dir, data_dir=data_dir, db_path=data_dir / "state.db")
    db = StateDatabase(config.db_path)
    registry = RunnerRegistry(config=config, db=db)
    try:
        runner = registry.refresh(active_assignments={})[0]
        assert runner.status == "AVAILABLE"

        registry.update_outcome(
            runner_id="codex_test",
            success=False,
            latency_sec=4.2,
            output_lines=["ERROR: You've hit your usage limit. Try again later."],
        )

        cooled_runner = registry.refresh(active_assignments={})[0]
        assert cooled_runner.quota_state == "limited"
        assert cooled_runner.status == "RATE_LIMITED"
        assert cooled_runner.health == "degraded"
    finally:
        db.close()
