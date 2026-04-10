from __future__ import annotations

import json

from overmind.config import AppConfig
from overmind.discovery.indexer import ProjectIndexer
from overmind.storage.db import StateDatabase


def test_indexer_invalidates_old_cache_versions(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    project_root = tmp_path / "Projects" / "Pairwise70"
    config_dir.mkdir()
    data_dir.mkdir()
    project_root.mkdir(parents=True)

    (project_root / "package.json").write_text('{"name":"pairwise70"}\n', encoding="utf-8")
    (project_root / "index.html").write_text("<!doctype html>\n", encoding="utf-8")

    (config_dir / "roots.yaml").write_text(
        f'scan_roots:\n  - "{(tmp_path / "Projects").as_posix()}"\nscan_rules:\n  include_git_repos: true\n  include_non_git_apps: true\n  incremental_scan: true\n  max_depth: 3\nguidance_filenames:\n  - "CLAUDE.md"\n',
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
    (config_dir / "verification_profiles.yaml").write_text("profiles: {}\nproject_rules: []\n", encoding="utf-8")

    config = AppConfig.from_directory(config_dir=config_dir, data_dir=data_dir, db_path=data_dir / "state.db")
    stale_cache = {
        "cache_version": 3,
        "projects": {
            str(project_root.resolve()): {
                "signature": "stale",
                "record": {
                    "project_id": "stale-project",
                    "name": "Stale Project",
                    "root_path": str(project_root),
                },
            }
        },
    }
    (data_dir / "cache" / "indexer_state.json").write_text(json.dumps(stale_cache), encoding="utf-8")

    db = StateDatabase(config.db_path)
    indexer = ProjectIndexer(config, db)
    try:
        records = indexer.incremental_refresh()
        assert len(records) == 1
        assert records[0].name == "Pairwise70"
        assert records[0].project_id != "stale-project"
    finally:
        db.close()
