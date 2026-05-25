from __future__ import annotations

import shutil

from overmind.config import AppConfig
from overmind.discovery.project_scanner import ProjectScanner


def test_project_scanner_applies_explicit_verification_profiles(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    project_root = tmp_path / "Projects" / "example-extractor-v2"
    project_root.mkdir(parents=True)
    config_dir.mkdir()
    data_dir.mkdir()

    (project_root / "pyproject.toml").write_text("[project]\nname='example-extractor-v2'\n", encoding="utf-8")
    (project_root / "README.md").write_text("# Extractor\npython -m pytest -q\n", encoding="utf-8")

    (config_dir / "roots.yaml").write_text(
        f'scan_roots:\n  - "{(tmp_path / "Projects").as_posix()}"\nscan_rules:\n  include_git_repos: true\n  include_non_git_apps: true\n  incremental_scan: true\n  max_depth: 4\nguidance_filenames:\n  - "CLAUDE.md"\n  - "README.md"\n',
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
    (config_dir / "verification_profiles.yaml").write_text(
        "profiles:\n"
        "  extractor_pipeline:\n"
        "    required:\n"
        "      - relevant_tests\n"
        "      - numeric_regression\n"
        "      - regression_checks\n"
        "project_rules:\n"
        "  - profile: extractor_pipeline\n"
        "    match_path_contains:\n"
        "      - '\\\\example-extractor-v2'\n",
        encoding="utf-8",
    )

    config = AppConfig.from_directory(config_dir=config_dir, data_dir=data_dir, db_path=data_dir / "state.db")
    project = ProjectScanner(config).scan_project(project_root)

    assert "extractor_pipeline" in project.verification_profiles
    assert "regression_checks" in project.recommended_verification
    assert "relevant_tests" in project.recommended_verification


def test_project_scanner_rewrites_stale_guidance_paths_and_prioritizes_focused_tests(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    project_root = tmp_path / "Projects" / "example-extractor-v2"
    tests_dir = project_root / "tests"
    tests_dir.mkdir(parents=True)
    config_dir.mkdir()
    data_dir.mkdir()

    (project_root / "pyproject.toml").write_text("[project]\nname='example-extractor-v2'\n", encoding="utf-8")
    (tests_dir / "test_proof_carrying_numbers.py").write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")
    (project_root / "CLAUDE.md").write_text(
        "python -m pytest C:/Projects/example-extractor-v2/tests/test_proof_carrying_numbers.py\n"
        "python -m pytest tests/ --tb=short -q\n",
        encoding="utf-8",
    )

    (config_dir / "roots.yaml").write_text(
        f'scan_roots:\n  - "{(tmp_path / "Projects").as_posix()}"\nscan_rules:\n  include_git_repos: true\n  include_non_git_apps: true\n  incremental_scan: true\n  max_depth: 4\nguidance_filenames:\n  - "CLAUDE.md"\n  - "README.md"\n',
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
    project = ProjectScanner(config).scan_project(project_root)

    assert project.test_commands[0].endswith("example-extractor-v2\\tests\\test_proof_carrying_numbers.py")
    assert project.test_commands[-1] == "python -m pytest -q"


def test_project_scanner_detects_single_file_html_app_and_filters_unavailable_profile_checks(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    project_root = tmp_path / "ExampleApp1"
    config_dir.mkdir()
    data_dir.mkdir()
    project_root.mkdir()

    (project_root / "package.json").write_text('{"devDependencies":{"terser":"^5.0.0"}}\n', encoding="utf-8")
    (project_root / "app.js").write_text("console.log('ok');\n", encoding="utf-8")
    (project_root / "Example-Tool-v1.0.html").write_text("<!doctype html>\n", encoding="utf-8")
    (project_root / "CLAUDE.md").write_text(
        "node -c C:/ExampleApp1/app.js\n",
        encoding="utf-8",
    )

    (config_dir / "roots.yaml").write_text(
        f'scan_roots:\n  - "{tmp_path.as_posix()}"\nscan_rules:\n  include_git_repos: true\n  include_non_git_apps: true\n  incremental_scan: true\n  max_depth: 4\nguidance_filenames:\n  - "CLAUDE.md"\n  - "README.md"\n',
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
    (config_dir / "verification_profiles.yaml").write_text(
        "profiles:\n"
        "  example_suite:\n"
        "    required:\n"
        "      - build\n"
        "      - relevant_tests\n"
        "      - targeted_browser_test\n"
        "      - numeric_regression\n"
        "      - regression_checks\n"
        "project_rules:\n"
        "  - profile: example_suite\n"
        "    match_path_contains:\n"
        "      - '\\\\exampleapp1'\n",
        encoding="utf-8",
    )

    config = AppConfig.from_directory(config_dir=config_dir, data_dir=data_dir, db_path=data_dir / "state.db")
    project = ProjectScanner(config).scan_project(project_root)

    assert project.project_type == "browser_app"
    assert "html" in project.stack
    assert "javascript" in project.stack
    assert any(command.startswith("node -c") for command in project.build_commands)
    # Profile requires 5 checks; targeted_browser_test gets filtered (no browser command available).
    assert project.recommended_verification == ["build", "relevant_tests", "numeric_regression", "regression_checks"]


def test_project_scanner_detects_advanced_math_and_strengthens_verification(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    project_root = tmp_path / "Projects" / "example-stats-app"
    tests_dir = project_root / "tests"
    config_dir.mkdir()
    data_dir.mkdir()
    tests_dir.mkdir(parents=True)

    (project_root / "pyproject.toml").write_text("[project]\nname='example-stats-app'\n", encoding="utf-8")
    (tests_dir / "test_hazard_ratio.py").write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")
    (project_root / "CLAUDE.md").write_text(
        "# Prognostic meta-analysis\n"
        "Bayesian posterior checks for hazard ratio outputs and bootstrap intervals.\n"
        "python -m pytest tests/test_hazard_ratio.py -q\n",
        encoding="utf-8",
    )
    (project_root / "oracle_validation.log").write_text(
        "Oracle benchmark complete for network meta-analysis.\n"
        "Bootstrap confidence interval validation passed.\n",
        encoding="utf-8",
    )

    (config_dir / "roots.yaml").write_text(
        f'scan_roots:\n  - "{(tmp_path / "Projects").as_posix()}"\nscan_rules:\n  include_git_repos: true\n  include_non_git_apps: true\n  incremental_scan: true\n  max_depth: 4\nguidance_filenames:\n  - "CLAUDE.md"\n  - "README.md"\n',
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
    project = ProjectScanner(config).scan_project(project_root)

    assert project.has_advanced_math is True
    assert project.advanced_math_score >= 10
    assert project.advanced_math_rigor == "extreme"
    assert "meta_analysis" in project.advanced_math_signals
    assert "survival_analysis" in project.advanced_math_signals
    assert "bayesian_modeling" in project.advanced_math_signals
    assert "resampling" in project.advanced_math_signals
    assert "deterministic_fixture_tests" in project.recommended_verification
    assert "edge_case_tests" in project.recommended_verification
    assert "output_comparison" in project.recommended_verification
    assert "sensitivity_checks" in project.recommended_verification
    assert "stochastic_stability" in project.recommended_verification
    assert "regression_checks" in project.recommended_verification
    assert project.risk_profile == "high"


def test_project_scanner_derives_analysis_focus_and_method_specific_checks(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    project_root = tmp_path / "Projects" / "advanced-evidence-lab"
    tests_dir = project_root / "tests"
    config_dir.mkdir()
    data_dir.mkdir()
    tests_dir.mkdir(parents=True)

    (project_root / "pyproject.toml").write_text("[project]\nname='advanced-evidence-lab'\n", encoding="utf-8")
    (tests_dir / "test_network_meta.py").write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")
    (project_root / "CLAUDE.md").write_text(
        "# Advanced evidence synthesis\n"
        "Network meta-analysis with SUCRA treatment ranking and Egger funnel plot diagnostics.\n"
        "Fine-Gray competing risks, hazard ratio modeling, multiple imputation, decision curve analysis, and Bayesian posterior checks.\n"
        "python -m pytest tests/test_network_meta.py -q\n",
        encoding="utf-8",
    )
    (project_root / "oracle_validation.log").write_text(
        "Validation baseline complete for network meta-analysis.\n"
        "R parity confirmed for competing risks and imputation outputs.\n",
        encoding="utf-8",
    )

    (config_dir / "roots.yaml").write_text(
        f'scan_roots:\n  - "{(tmp_path / "Projects").as_posix()}"\nscan_rules:\n  include_git_repos: true\n  include_non_git_apps: true\n  incremental_scan: true\n  max_depth: 4\nguidance_filenames:\n  - "CLAUDE.md"\n  - "README.md"\n',
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
    project = ProjectScanner(config).scan_project(project_root)

    assert "network_meta_analysis" in project.advanced_math_signals
    assert "publication_bias_small_study" in project.advanced_math_signals
    assert "competing_risks_multistate" in project.advanced_math_signals
    assert "missing_data_imputation" in project.advanced_math_signals
    assert "evidence synthesis" in project.analysis_focus_areas
    assert "survival and censored outcomes" in project.analysis_focus_areas
    assert "missing-data handling" in project.analysis_focus_areas
    assert "indirect-comparison consistency and ranking stability" in project.analysis_risk_factors
    assert "censoring and proportional-hazards assumptions" in project.analysis_risk_factors
    assert "missingness mechanism sensitivity" in project.analysis_risk_factors
    assert "consistency_checks" in project.recommended_verification
    assert "ranking_stability" in project.recommended_verification
    assert "publication_bias_checks" in project.recommended_verification
    assert "censoring_checks" in project.recommended_verification
    assert "competing_risks_checks" in project.recommended_verification
    assert "missing_data_checks" in project.recommended_verification
    assert "posterior_sanity_checks" in project.recommended_verification
    assert "decision_curve_checks" in project.recommended_verification
    assert "model_assumption_checks" in project.recommended_verification
    assert "cross_implementation_parity" in project.recommended_verification


def test_project_scanner_derives_repo_pytest_for_browser_app_with_python_smoke_tests(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    project_root = tmp_path / "Projects" / "example-stats-app"
    tests_dir = project_root / "tests"
    config_dir.mkdir()
    data_dir.mkdir()
    tests_dir.mkdir(parents=True)

    (project_root / "index.html").write_text("<!doctype html>\n", encoding="utf-8")
    (project_root / "CLAUDE.md").write_text(
        "node C:/Projects/test_example_v2.js\n"
        "node C:/Projects/example_r_validation.js\n",
        encoding="utf-8",
    )
    (tests_dir / "test_smoke.py").write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")
    (tests_dir / "automated_visual_test.html").write_text(
        "<!doctype html>\n<div id='summary'>Tests Complete: 10/10 passed (100%)</div>\n",
        encoding="utf-8",
    )
    (tests_dir / "automated_test_suite.html").write_text(
        "<!doctype html>\n<div class='summary'>Test Summary\nPass Rate: 100.0%</div>\n",
        encoding="utf-8",
    )

    (config_dir / "roots.yaml").write_text(
        f'scan_roots:\n  - "{(tmp_path / "Projects").as_posix()}"\nscan_rules:\n  include_git_repos: true\n  include_non_git_apps: true\n  incremental_scan: true\n  max_depth: 4\nguidance_filenames:\n  - "CLAUDE.md"\n  - "README.md"\n',
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
    project = ProjectScanner(config).scan_project(project_root)

    assert project.project_type == "browser_app"
    assert project.test_commands[0] == "python -m pytest tests/test_smoke.py -q"
    assert 'browser_checks.py"' in project.browser_test_commands[0]
    assert 'tests/automated_test_suite.html' in project.browser_test_commands[0]
    assert 'tests/automated_visual_test.html' in project.browser_test_commands[1]
    assert set(project.test_commands[1:]) == {
        "node C:/Projects/example_r_validation.js",
        "node C:/Projects/test_example_v2.js",
    }


def test_project_scanner_prioritizes_available_test_command_over_unavailable_rscript(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    project_root = tmp_path / "Projects" / "Pairwise70"
    testthat_dir = project_root / "tests" / "testthat"
    config_dir.mkdir()
    data_dir.mkdir()
    project_root.mkdir(parents=True)
    testthat_dir.mkdir(parents=True)

    (project_root / "package.json").write_text('{"name":"pairwise70"}\n', encoding="utf-8")
    (project_root / "index.html").write_text("<!doctype html>\n", encoding="utf-8")
    (project_root / "app.R").write_text("# placeholder\n", encoding="utf-8")
    (project_root / "CLAUDE.md").write_text(
        "python C:/Projects/example_functional_test.py\n",
        encoding="utf-8",
    )

    (config_dir / "roots.yaml").write_text(
        f'scan_roots:\n  - "{(tmp_path / "Projects").as_posix()}"\nscan_rules:\n  include_git_repos: true\n  include_non_git_apps: true\n  incremental_scan: true\n  max_depth: 4\nguidance_filenames:\n  - "CLAUDE.md"\n  - "README.md"\n',
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

    real_which = shutil.which

    def fake_which(command: str):
        if command.lower() == "rscript":
            return None
        return real_which(command)

    monkeypatch.setattr("overmind.discovery.project_scanner.shutil.which", fake_which)

    config = AppConfig.from_directory(config_dir=config_dir, data_dir=data_dir, db_path=data_dir / "state.db")
    project = ProjectScanner(config).scan_project(project_root)

    assert project.test_commands[0] == "python C:/Projects/example_functional_test.py"
    assert project.test_commands[1].startswith("Rscript -e")
