from __future__ import annotations

import json

from overmind.config import AppConfig
from overmind.discovery.indexer import ProjectIndexer
from overmind.storage.db import StateDatabase


def test_project_indexer_discovers_browser_app_and_guidance(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    project_root = tmp_path / "projects" / "sample-app"
    project_root.mkdir(parents=True)
    config_dir.mkdir()
    data_dir.mkdir()

    (project_root / "package.json").write_text(
        json.dumps({"scripts": {"build": "vite build", "test": "vitest"}}),
        encoding="utf-8",
    )
    (project_root / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (project_root / "README.md").write_text("# App\n- Keep output concise\n", encoding="utf-8")

    (config_dir / "roots.yaml").write_text(
        f'scan_roots:\n  - "{(tmp_path / "projects").as_posix()}"\nscan_rules:\n  include_git_repos: true\n  include_non_git_apps: true\n  incremental_scan: true\n  max_depth: 4\nguidance_filenames:\n  - "README.md"\n',
        encoding="utf-8",
    )
    (config_dir / "runners.yaml").write_text("runners: []\n", encoding="utf-8")
    (config_dir / "policies.yaml").write_text(
        "concurrency:\n  default_active_sessions: 1\n  max_active_sessions: 1\n  degraded_sessions: 1\n"
        "limits:\n  idle_timeout_min: 10\n  summary_trigger_output_lines: 400\n"
        "routing: {}\n"
        "risk_policy: {}\n",
        encoding="utf-8",
    )
    (config_dir / "projects_ignore.yaml").write_text("ignored_directories: []\nignored_file_suffixes: []\n", encoding="utf-8")
    (config_dir / "verification_profiles.yaml").write_text("profiles: {}\n", encoding="utf-8")

    config = AppConfig.from_directory(config_dir=config_dir, data_dir=data_dir, db_path=data_dir / "state.db")
    db = StateDatabase(config.db_path)
    indexer = ProjectIndexer(config, db)

    projects = indexer.incremental_refresh()

    assert len(projects) == 1
    project = projects[0]
    assert project.project_type == "browser_app"
    assert project.name == "sample-app"
    assert "README.md" in project.guidance_files
    assert project.build_commands == ["npm run build"]
    assert project.test_commands == ["npm run test"]
    db.close()

