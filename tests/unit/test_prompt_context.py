from __future__ import annotations

from overmind.config import AppConfig
from overmind.core.orchestrator import Orchestrator
from overmind.storage.models import ProjectRecord, TaskRecord


def test_orchestrator_prompt_includes_statistical_rigor(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    data_dir.mkdir()

    (config_dir / "roots.yaml").write_text("scan_roots: []\nscan_rules: {}\nguidance_filenames: []\n", encoding="utf-8")
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
    orchestrator = Orchestrator(config)
    try:
        project = ProjectRecord(
            project_id="math-project",
            name="Math Project",
            root_path="C:\\Projects\\math-project",
            project_type="python_tool",
            stack=["python"],
            has_numeric_logic=True,
            has_advanced_math=True,
            advanced_math_signals=["meta_analysis", "bayesian_modeling"],
            advanced_math_score=8,
            advanced_math_rigor="high",
            analysis_focus_areas=["evidence synthesis", "probabilistic inference"],
            analysis_risk_factors=["heterogeneity and effect-size specification", "sampler convergence and prior sensitivity"],
            test_commands=["python -m pytest tests/test_math.py -q"],
        )
        task = TaskRecord(
            task_id="task-math",
            project_id=project.project_id,
            title="Investigate posterior regression drift",
            task_type="focused_fix",
            source="test",
            priority=0.9,
            risk="high",
            expected_runtime_min=5,
            expected_context_cost="medium",
            required_verification=["relevant_tests", "numeric_regression"],
        )

        prompt = orchestrator._build_worker_prompt(project, task)

        assert "STATISTICAL RIGOR" in prompt
        assert "- rigor: high" in prompt
        assert "- score: 8" in prompt
        assert "meta_analysis, bayesian_modeling" in prompt
        assert "ANALYSIS PROFILE" in prompt
        assert "evidence synthesis, probabilistic inference" in prompt
        assert "heterogeneity and effect-size specification" in prompt
    finally:
        orchestrator.close()
