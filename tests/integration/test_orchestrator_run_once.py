from __future__ import annotations

import sys
from pathlib import Path

from overmind.config import AppConfig
from overmind.core.orchestrator import Orchestrator
from overmind.storage.models import ProjectRecord, TaskRecord


def test_orchestrator_completes_task_with_dummy_runner(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    project_root = tmp_path / "project"
    runner_script = tmp_path / "dummy_runner.py"
    config_dir.mkdir()
    data_dir.mkdir()
    project_root.mkdir()

    runner_script.write_text(
        "import sys\n"
        "sys.stdin.readline()\n"
        "print('COMMAND: inspect task', flush=True)\n"
        "print('build passed', flush=True)\n"
        "print('tests passed', flush=True)\n",
        encoding="utf-8",
    )

    (config_dir / "roots.yaml").write_text(
        f'scan_roots:\n  - "{project_root.as_posix()}"\nscan_rules:\n  include_git_repos: true\n  include_non_git_apps: true\n  incremental_scan: true\n  max_depth: 2\nguidance_filenames:\n  - "README.md"\n',
        encoding="utf-8",
    )
    (config_dir / "runners.yaml").write_text(
        "runners:\n"
        f"  - runner_id: dummy_runner\n"
        "    type: codex\n"
        "    mode: terminal\n"
        f"    command: '\"{Path(sys.executable).as_posix()}\" \"{runner_script.as_posix()}\"'\n"
        "    environment: windows\n",
        encoding="utf-8",
    )
    (config_dir / "policies.yaml").write_text(
        "concurrency:\n  default_active_sessions: 1\n  max_active_sessions: 1\n  degraded_sessions: 1\n"
        "  scale_up_cpu_below: 100\n  scale_down_cpu_above: 100\n  scale_down_ram_above: 100\n  scale_down_swap_above_mb: 999999\n"
        "limits:\n  idle_timeout_min: 10\n  summary_trigger_output_lines: 400\n"
        "routing:\n  codex:\n    strengths: ['tests']\n"
        "risk_policy: {}\n",
        encoding="utf-8",
    )
    (config_dir / "projects_ignore.yaml").write_text("ignored_directories: []\nignored_file_suffixes: []\n", encoding="utf-8")
    (config_dir / "verification_profiles.yaml").write_text("profiles: {}\n", encoding="utf-8")

    config = AppConfig.from_directory(config_dir=config_dir, data_dir=data_dir, db_path=data_dir / "state.db")
    orchestrator = Orchestrator(config)
    try:
        project = ProjectRecord(
            project_id="demo-project",
            name="Demo Project",
            root_path=str(project_root),
            project_type="browser_app",
            stack=["html", "javascript", "css"],
            build_commands=[f'"{sys.executable}" -c "print(\'build ok\')"'],
            test_commands=[f'"{sys.executable}" -c "print(\'test ok\')"'],
        )
        task = TaskRecord(
            task_id="task-demo",
            project_id=project.project_id,
            title="Run baseline verification",
            task_type="verification",
            source="test",
            priority=0.9,
            risk="medium",
            expected_runtime_min=1,
            expected_context_cost="low",
            required_verification=["build", "relevant_tests"],
        )
        orchestrator.db.upsert_project(project)
        orchestrator.db.upsert_task(task)

        result = orchestrator.run_once(settle_seconds=0.5)
        assignments = list(result["assignments"])
        saved_task = orchestrator.db.get_task(task.task_id)
        if saved_task is not None and saved_task.status != "COMPLETED":
            result = orchestrator.run_once(settle_seconds=0.5)
            assignments.extend(result["assignments"])
            saved_task = orchestrator.db.get_task(task.task_id)

        assert assignments
        assert saved_task is not None
        assert saved_task.status == "COMPLETED"
        assert saved_task.verification_summary
    finally:
        orchestrator.close()


def test_orchestrator_completes_task_with_one_shot_stdin_runner(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    project_root = tmp_path / "project"
    runner_script = tmp_path / "dummy_exec_runner.py"
    config_dir.mkdir()
    data_dir.mkdir()
    project_root.mkdir()

    runner_script.write_text(
        "import sys\n"
        "prompt = sys.stdin.buffer.read().decode('utf-8')\n"
        "print(f'COMMAND: received {len(prompt.splitlines())} lines', flush=True)\n"
        "print('tests passed', flush=True)\n",
        encoding="utf-8",
    )

    (config_dir / "roots.yaml").write_text(
        f'scan_roots:\n  - "{project_root.as_posix()}"\nscan_rules:\n  include_git_repos: true\n  include_non_git_apps: true\n  incremental_scan: true\n  max_depth: 2\nguidance_filenames:\n  - "README.md"\n',
        encoding="utf-8",
    )
    (config_dir / "runners.yaml").write_text(
        "runners:\n"
        f"  - runner_id: dummy_exec_runner\n"
        "    type: codex\n"
        "    mode: terminal\n"
        f"    command: '\"{Path(sys.executable).as_posix()}\" \"{runner_script.as_posix()}\" exec -'\n"
        "    environment: windows\n",
        encoding="utf-8",
    )
    (config_dir / "policies.yaml").write_text(
        "concurrency:\n  default_active_sessions: 1\n  max_active_sessions: 1\n  degraded_sessions: 1\n"
        "  scale_up_cpu_below: 100\n  scale_down_cpu_above: 100\n  scale_down_ram_above: 100\n  scale_down_swap_above_mb: 999999\n"
        "limits:\n  idle_timeout_min: 10\n  summary_trigger_output_lines: 400\n"
        "routing:\n  codex:\n    strengths: ['tests']\n"
        "risk_policy: {}\n",
        encoding="utf-8",
    )
    (config_dir / "projects_ignore.yaml").write_text("ignored_directories: []\nignored_file_suffixes: []\n", encoding="utf-8")
    (config_dir / "verification_profiles.yaml").write_text("profiles: {}\n", encoding="utf-8")

    config = AppConfig.from_directory(config_dir=config_dir, data_dir=data_dir, db_path=data_dir / "state.db")
    orchestrator = Orchestrator(config)
    try:
        project = ProjectRecord(
            project_id="one-shot-project",
            name="One Shot Project",
            root_path=str(project_root),
            project_type="python_tool",
            stack=["python"],
            guidance_summary=["Résumé check — ensure UTF-8 prompt delivery"],
            test_commands=[f'"{sys.executable}" -c "print(\'test ok\')"'],
        )
        task = TaskRecord(
            task_id="task-one-shot",
            project_id=project.project_id,
            title="Run focused verification — UTF-8",
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

        result = orchestrator.run_once(settle_seconds=0.5)
        assignments = list(result["assignments"])
        saved_task = orchestrator.db.get_task(task.task_id)
        if saved_task is not None and saved_task.status != "COMPLETED":
            result = orchestrator.run_once(settle_seconds=0.5)
            assignments.extend(result["assignments"])
            saved_task = orchestrator.db.get_task(task.task_id)

        assert assignments
        assert saved_task is not None
        assert saved_task.status == "COMPLETED"
    finally:
        orchestrator.close()


def test_orchestrator_rewrites_bare_codex_command_to_exec_mode(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    project_root = tmp_path / "project"
    runner_script = tmp_path / "capture_codex.py"
    wrapper_script = tmp_path / "codex.cmd"
    config_dir.mkdir()
    data_dir.mkdir()
    project_root.mkdir()

    runner_script.write_text(
        "import sys\n"
        "prompt = sys.stdin.buffer.read().decode('utf-8')\n"
        "args = sys.argv[1:]\n"
        "print(f'COMMAND: args={args}', flush=True)\n"
        "if 'exec' not in args or args[-1] != '-':\n"
        "    print('runner exited non-zero', flush=True)\n"
        "    raise SystemExit(1)\n"
        "if '--dangerously-bypass-approvals-and-sandbox' not in args:\n"
        "    print('runner exited non-zero', flush=True)\n"
        "    raise SystemExit(1)\n"
        "if '--skip-git-repo-check' not in args:\n"
        "    print('runner exited non-zero', flush=True)\n"
        "    raise SystemExit(1)\n"
        "if not prompt.strip():\n"
        "    print('runner exited non-zero', flush=True)\n"
        "    raise SystemExit(1)\n"
        "print('tests passed', flush=True)\n",
        encoding="utf-8",
    )
    wrapper_script.write_text(
        f'@echo off\r\n"{Path(sys.executable)}" "{runner_script}" %*\r\n',
        encoding="utf-8",
    )

    (config_dir / "roots.yaml").write_text(
        f'scan_roots:\n  - "{project_root.as_posix()}"\nscan_rules:\n  include_git_repos: true\n  include_non_git_apps: true\n  incremental_scan: true\n  max_depth: 2\nguidance_filenames:\n  - "README.md"\n',
        encoding="utf-8",
    )
    (config_dir / "runners.yaml").write_text(
        "runners:\n"
        f"  - runner_id: codex_bare_runner\n"
        "    type: codex\n"
        "    mode: terminal\n"
        f"    command: '\"{wrapper_script.as_posix()}\"'\n"
        "    environment: windows\n",
        encoding="utf-8",
    )
    (config_dir / "policies.yaml").write_text(
        "concurrency:\n  default_active_sessions: 1\n  max_active_sessions: 1\n  degraded_sessions: 1\n"
        "  scale_up_cpu_below: 100\n  scale_down_cpu_above: 100\n  scale_down_ram_above: 100\n  scale_down_swap_above_mb: 999999\n"
        "limits:\n  idle_timeout_min: 10\n  summary_trigger_output_lines: 400\n"
        "routing:\n  codex:\n    strengths: ['tests']\n"
        "risk_policy: {}\n",
        encoding="utf-8",
    )
    (config_dir / "projects_ignore.yaml").write_text("ignored_directories: []\nignored_file_suffixes: []\n", encoding="utf-8")
    (config_dir / "verification_profiles.yaml").write_text("profiles: {}\n", encoding="utf-8")

    config = AppConfig.from_directory(config_dir=config_dir, data_dir=data_dir, db_path=data_dir / "state.db")
    orchestrator = Orchestrator(config)
    try:
        project = ProjectRecord(
            project_id="codex-bare-project",
            name="Codex Bare Project",
            root_path=str(project_root),
            project_type="python_tool",
            stack=["python"],
            test_commands=[f'"{sys.executable}" -c "print(\'test ok\')"'],
        )
        task = TaskRecord(
            task_id="task-codex-bare",
            project_id=project.project_id,
            title="Run baseline verification through bare codex",
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

        result = orchestrator.run_once(settle_seconds=0.5)
        assignments = list(result["assignments"])
        saved_task = orchestrator.db.get_task(task.task_id)
        if saved_task is not None and saved_task.status != "COMPLETED":
            result = orchestrator.run_once(settle_seconds=0.5)
            assignments.extend(result["assignments"])
            saved_task = orchestrator.db.get_task(task.task_id)

        assert assignments
        assert saved_task is not None
        assert saved_task.status == "COMPLETED"
    finally:
        orchestrator.close()
