from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from overmind.config import AppConfig
from overmind.discovery.activity_analyzer import ActivityLogAnalyzer
from overmind.discovery.analysis_signals import (
    analysis_rigor_level,
    compute_analysis_score,
    describe_analysis_focus_areas,
    describe_analysis_risk_factors,
    detect_analysis_signals,
    recommended_analysis_checks,
)
from overmind.discovery.git_probe import GitProbe
from overmind.discovery.guidance_parser import GuidanceParser
from overmind.discovery.manifest_parser import ManifestParser
from overmind.storage.models import ProjectRecord, slugify, utc_now

NUMERIC_HINTS = (
    "meta",
    "stats",
    "regression",
    "bootstrap",
    "effect",
    "forest",
    "numeric",
    "calc",
    "analysis",
    "bayes",
    "heterogeneity",
    "bias",
    "oracle",
    "survival",
    "certainty",
)
PROJECT_DIR_HINTS = {"src", "tests", "analysis", "scripts", "R", "python", "js", "docs", "dashboard", "data"}
WINDOWS_PATH_PATTERN = re.compile(r'(?P<quote>["\']?)(?P<path>[A-Za-z]:[\\/][^"\';\s]+)(?P=quote)')


class ProjectScanner:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.git_probe = GitProbe()
        self.guidance_parser = GuidanceParser()
        self.manifest_parser = ManifestParser()
        self.activity_analyzer = ActivityLogAnalyzer(config.ignored_directories)

    def discover_project_roots(self) -> list[Path]:
        discovered: list[Path] = []
        seen: set[str] = set()
        max_depth = int(self.config.roots.scan_rules.max_depth)
        ignored = set(self.config.ignored_directories)

        for scan_root in self.config.roots.scan_roots:
            if not scan_root.exists():
                continue
            scan_root = scan_root.resolve()
            for current_root, dirnames, filenames in os.walk(scan_root):
                current = Path(current_root)
                relative_depth = len(current.relative_to(scan_root).parts)
                dirnames[:] = [name for name in dirnames if name not in ignored]
                if relative_depth > max_depth:
                    dirnames[:] = []
                    continue
                if self._is_project_root(current, filenames):
                    key = str(current).lower()
                    if key not in seen:
                        seen.add(key)
                        discovered.append(current)
                    dirnames[:] = []
        return discovered

    def compute_signature(self, root: Path) -> str:
        relevant_paths: list[Path] = []
        for candidate in (
            "package.json",
            "index.html",
            "pyproject.toml",
            "requirements.txt",
            "Pipfile",
            "environment.yml",
            "app.R",
            "DESCRIPTION",
        ):
            path = root / candidate
            if path.exists():
                relevant_paths.append(path)
        relevant_paths.extend(root.glob("*.Rproj"))
        for guidance_name in self.config.roots.guidance_filenames:
            path = root / guidance_name
            if path.exists():
                relevant_paths.append(path)
        relevant_paths.extend(self.activity_analyzer.signature_files(root))

        fingerprint = []
        for path in sorted(relevant_paths):
            try:
                stat = path.stat()
            except OSError:
                continue
            fingerprint.append(f"{path.name}:{stat.st_size}:{int(stat.st_mtime)}")
        return hashlib.sha1("|".join(fingerprint).encode("utf-8")).hexdigest()

    def scan_project(self, root: Path) -> ProjectRecord:
        manifest = self.manifest_parser.parse(root)
        guidance = self.guidance_parser.load(
            root, self.config.roots.guidance_filenames
        )
        normalized_guidance_commands = [
            self._normalize_guidance_command(root, command)
            for command in guidance.commands
        ]
        activity = self.activity_analyzer.analyze(root)
        is_git_repo, _branch = self.git_probe.inspect(root)

        stack = set(manifest["stack"])
        if (root / "src").exists():
            stack.update({"javascript", "css"})
        if self._has_html_surface(root):
            stack.add("html")
        if self._has_javascript_surface(root):
            stack.add("javascript")
        if self._is_python_project(root):
            stack.add("python")
        if self._is_r_project(root):
            stack.add("r")

        derived_commands = self._derive_commands(root, normalized_guidance_commands)
        build_commands = self._merge_commands(
            manifest["build_commands"],
            derived_commands["build"],
            command_type="build",
        )
        test_commands = self._merge_commands(
            manifest["test_commands"],
            derived_commands["test"],
            command_type="test",
        )
        browser_test_commands = self._merge_commands(
            manifest["browser_test_commands"],
            derived_commands["browser"],
            command_type="browser",
        )
        perf_commands = self._merge_commands(
            manifest["perf_commands"],
            derived_commands["perf"],
            command_type="perf",
        )

        advanced_math_signals = self._advanced_math_signals(root, guidance.summary, normalized_guidance_commands, activity)
        analysis_focus_areas = describe_analysis_focus_areas(advanced_math_signals)
        analysis_risk_factors = describe_analysis_risk_factors(advanced_math_signals)
        advanced_math_score = compute_analysis_score(
            advanced_math_signals,
            has_validation_history=activity.has_validation_history,
            has_oracle_benchmarks=activity.has_oracle_benchmarks,
            has_drift_history=activity.has_drift_history,
        )
        advanced_math_rigor = analysis_rigor_level(advanced_math_score)
        has_advanced_math = advanced_math_score > 0
        has_numeric_logic = self._has_numeric_hints(root) or "r" in stack or activity.has_oracle_benchmarks or activity.has_drift_history
        has_numeric_logic = has_numeric_logic or has_advanced_math
        root_name = root.name or "project"
        project_id = f"{slugify(root_name)}-{hashlib.sha1(str(root).encode('utf-8')).hexdigest()[:8]}"
        risk_profile = self._risk_profile(
            has_numeric_logic=has_numeric_logic,
            has_advanced_math=has_advanced_math,
            advanced_math_score=advanced_math_score,
            browser_test_commands=browser_test_commands,
            activity=activity,
        )
        project_type = self._infer_project_type(root, stack)
        verification_profiles = self._select_verification_profiles(
            project_name=root_name,
            root=root,
            project_type=project_type,
            has_numeric_logic=has_numeric_logic,
            has_advanced_math=has_advanced_math,
            advanced_math_score=advanced_math_score,
            activity=activity,
        )
        recommended_verification = self._recommended_verification(
            build_commands=build_commands,
            test_commands=test_commands,
            browser_test_commands=browser_test_commands,
            perf_commands=perf_commands,
            has_numeric_logic=has_numeric_logic,
            has_advanced_math=has_advanced_math,
            advanced_math_score=advanced_math_score,
            advanced_math_signals=advanced_math_signals,
            activity=activity,
            verification_profiles=verification_profiles,
        )

        return ProjectRecord(
            project_id=project_id,
            name=root_name,
            root_path=str(root),
            is_git_repo=is_git_repo,
            project_type=project_type,
            stack=sorted(stack),
            has_numeric_logic=has_numeric_logic,
            has_advanced_math=has_advanced_math,
            advanced_math_signals=advanced_math_signals,
            advanced_math_score=advanced_math_score,
            advanced_math_rigor=advanced_math_rigor,
            analysis_focus_areas=analysis_focus_areas,
            analysis_risk_factors=analysis_risk_factors,
            guidance_files=guidance.found,
            guidance_summary=guidance.summary,
            guidance_commands=normalized_guidance_commands,
            activity_files=activity.files,
            activity_summary=activity.summary,
            has_oracle_benchmarks=activity.has_oracle_benchmarks,
            has_drift_history=activity.has_drift_history,
            has_validation_history=activity.has_validation_history,
            verification_profiles=verification_profiles,
            recommended_verification=recommended_verification,
            build_commands=build_commands,
            test_commands=test_commands,
            browser_test_commands=browser_test_commands,
            perf_commands=perf_commands,
            risk_profile=risk_profile,
            manifest_hash=manifest["manifest_hash"] or self.compute_signature(root),
            package_manager=manifest["package_manager"],
            last_active_at=self._last_active_timestamp(root, guidance.found, activity.files),
            last_indexed_at=utc_now(),
        )

    def _is_project_root(self, root: Path, filenames: list[str]) -> bool:
        lowered_filenames = {filename.lower() for filename in filenames}
        markers = {
            "package.json",
            "index.html",
            "pyproject.toml",
            "requirements.txt",
            "pipfile",
            "environment.yml",
            "app.r",
            "description",
        }
        if markers.intersection(lowered_filenames):
            return True
        if list(root.glob("*.Rproj")):
            return True
        if any((root / filename).exists() for filename in ("playwright.config.js", "playwright.config.ts")):
            return True
        if any(filename.lower().endswith(".html") for filename in filenames) and self._has_guidance_file(root):
            return True
        if self._has_guidance_file(root):
            child_dirs = {child.name for child in root.iterdir() if child.is_dir()}
            if PROJECT_DIR_HINTS.intersection(child_dirs):
                return True
        return False

    def _infer_project_type(self, root: Path, stack: set[str]) -> str:
        browser_stack = {"html", "javascript", "css"}.intersection(stack)
        if browser_stack and ("r" in stack or "python" in stack):
            return "hybrid_browser_analytics_app"
        if self._has_html_surface(root) or browser_stack:
            return "browser_app"
        if self._is_r_project(root):
            return "r_project"
        if self._is_python_project(root):
            return "python_tool"
        return "unknown"

    def _has_numeric_hints(self, root: Path) -> bool:
        ignored = set(self.config.ignored_directories)
        for current_root, dirnames, filenames in os.walk(root):
            current = Path(current_root)
            relative_depth = len(current.relative_to(root).parts)
            if relative_depth > 2:
                dirnames[:] = []
                continue
            dirnames[:] = [name for name in dirnames if name not in ignored]
            names = [*dirnames, *filenames]
            if any(hint in name.lower() for name in names for hint in NUMERIC_HINTS):
                return True
        return False

    def _last_active_timestamp(
        self,
        root: Path,
        guidance_files: list[str],
        activity_files: list[str],
    ) -> str | None:
        candidates: list[Path] = []
        for filename in (
            "package.json",
            "index.html",
            "pyproject.toml",
            "requirements.txt",
            "app.R",
            "DESCRIPTION",
        ):
            path = root / filename
            if path.exists():
                candidates.append(path)
        for filename in guidance_files:
            path = root / filename
            if path.exists():
                candidates.append(path)
        for raw_path in activity_files[:5]:
            path = Path(raw_path)
            if path.exists():
                candidates.append(path)
        if not candidates:
            return None
        mtimes: list[float] = []
        for path in candidates:
            try:
                mtimes.append(path.stat().st_mtime)
            except OSError:
                continue
        if not mtimes:
            return None
        return datetime.fromtimestamp(max(mtimes), tz=UTC).replace(microsecond=0).isoformat()

    def _derive_commands(self, root: Path, guidance_commands: list[str]) -> dict[str, list[str]]:
        commands = {"build": [], "test": [], "browser": [], "perf": []}
        pytest_commands = self._derive_pytest_commands(root)
        if pytest_commands:
            commands["test"].extend(pytest_commands)
        browser_checks = self._derive_browser_check_commands(root)
        if browser_checks:
            commands["browser"].extend(browser_checks)
        if self._is_python_project(root) and (root / "tests").exists():
            commands["test"].append("python -m pytest -q")
        if self._is_r_project(root) and (root / "tests" / "testthat").exists():
            commands["test"].append("Rscript -e \"testthat::test_dir('tests/testthat')\"")
        if (root / "run_oracle_benchmark.ps1").exists():
            commands["perf"].append("powershell -ExecutionPolicy Bypass -File run_oracle_benchmark.ps1")
        if (root / "app.R").exists() and not (root / "tests").exists():
            commands["build"].append("Rscript -e \"source('app.R')\"")
        if self._has_html_surface(root) and (root / "app.js").exists():
            commands["build"].append("node -c app.js")
        for command in guidance_commands:
            lowered = command.lower()
            if any(token in lowered for token in ("playwright", "selenium")):
                commands["browser"].append(command)
            elif any(token in lowered for token in ("lighthouse", "benchmark", "oracle")):
                commands["perf"].append(command)
            elif any(token in lowered for token in ("pytest", "test", "validation")):
                commands["test"].append(command)
            elif lowered.startswith("node -c ") or lowered.startswith("node --check ") or any(
                token in lowered for token in ("build", "vite", "webpack", "rollup")
            ):
                commands["build"].append(command)
        return commands

    def _derive_pytest_commands(self, root: Path) -> list[str]:
        tests_root = root / "tests"
        if not tests_root.is_dir():
            return []

        candidates: list[Path] = []
        for pattern in ("test_*.py", "*_test.py"):
            candidates.extend(tests_root.rglob(pattern))

        path_by_name = {candidate.relative_to(root).as_posix(): candidate for candidate in candidates}
        unique_candidates = [path_by_name[name] for name in sorted(path_by_name)]
        if not unique_candidates:
            return []

        def priority(path: Path) -> tuple[int, int, int, str]:
            lowered = path.relative_to(root).as_posix().lower()
            smoke_signal = int(any(token in lowered for token in ("smoke", "validation", "functional")))
            numeric_signal = int(
                any(
                    token in lowered
                    for token in ("hazard", "meta", "bayes", "survival", "ratio", "calibration", "math", "stats", "numeric")
                )
            )
            depth = len(path.relative_to(root).parts)
            return (-smoke_signal, -numeric_signal, depth, lowered)

        selected = min(unique_candidates, key=priority)
        relative_path = selected.relative_to(root).as_posix()
        return [f"python -m pytest {relative_path} -q"]

    def _derive_browser_check_commands(self, root: Path) -> list[str]:
        helper_script = Path(__file__).resolve().parents[1] / "verification" / "browser_checks.py"
        page_profiles = [
            {
                "path": Path("tests/automated_test_suite.html"),
                "selector": ".summary",
                "ready_text": "Test Summary",
                "min_pass_rate": 95,
            },
            {
                "path": Path("tests/automated_visual_test.html"),
                "selector": "#summary",
                "ready_text": "Tests Complete:",
                "min_pass_rate": 95,
            },
            {
                "path": Path("tests/validation_suite.html"),
                "selector": ".summary",
                "ready_text": "Validation Summary",
                "min_pass_rate": 90,
            },
        ]

        commands: list[str] = []
        for profile in page_profiles:
            page_path = root / profile["path"]
            if not page_path.exists():
                continue
            command = (
                f'"{sys.executable}" "{helper_script}" '
                f'--project-root "{root}" '
                f'--page "{profile["path"].as_posix()}" '
                f'--summary-selector "{profile["selector"]}" '
                f'--ready-text "{profile["ready_text"]}" '
                f'--wait-seconds 20 '
                f'--min-pass-rate {profile["min_pass_rate"]} '
                f'--ignore-console-pattern "favicon\\.ico"'
            )
            commands.append(command)
        return commands

    def _merge_commands(self, primary: list[str], secondary: list[str], command_type: str) -> list[str]:
        merged: list[str] = []
        for command in [*primary, *secondary]:
            if command and command not in merged:
                merged.append(command)
        return sorted(merged, key=lambda command: self._command_priority(command_type, command))

    def _select_verification_profiles(
        self,
        project_name: str,
        root: Path,
        project_type: str,
        has_numeric_logic: bool,
        has_advanced_math: bool,
        advanced_math_score: int,
        activity,
    ) -> list[str]:
        matched: list[str] = []
        path_text = self._normalize_path_fragment(str(root))
        name_text = project_name.lower()
        for rule in self.config.verification_rules:
            matches_name = not rule.match_name_equals or name_text in {
                candidate.lower() for candidate in rule.match_name_equals
            }
            matches_path = not rule.match_path_contains or any(
                self._normalize_path_fragment(candidate) in path_text
                for candidate in rule.match_path_contains
            )
            matches_type = not rule.match_project_type or project_type in rule.match_project_type
            if matches_name and matches_path and matches_type and rule.profile not in matched:
                matched.append(rule.profile)

        if not matched and project_type == "hybrid_browser_analytics_app":
            matched.append("browser_numeric_app")
        if not matched and has_numeric_logic and activity.has_oracle_benchmarks:
            matched.append("extractor_pipeline")
        if not matched and activity.has_drift_history:
            matched.append("living_monitor")
        if (
            not matched
            and has_advanced_math
            and advanced_math_score >= 3
            and project_type in {"python_tool", "r_project", "hybrid_browser_analytics_app"}
        ):
            matched.append("numerical_change")
        return matched

    def _recommended_verification(
        self,
        build_commands: list[str],
        test_commands: list[str],
        browser_test_commands: list[str],
        perf_commands: list[str],
        has_numeric_logic: bool,
        has_advanced_math: bool,
        advanced_math_score: int,
        advanced_math_signals: list[str],
        activity,
        verification_profiles: list[str],
    ) -> list[str]:
        checks: list[str] = []
        if build_commands:
            checks.append("build")
        if test_commands:
            checks.append("relevant_tests")
        if browser_test_commands:
            checks.append("targeted_browser_test")
        if test_commands and (has_numeric_logic or activity.has_validation_history):
            checks.append("numeric_regression")
        if test_commands and has_advanced_math:
            checks.extend(["deterministic_fixture_tests", "edge_case_tests", "output_comparison"])
        if test_commands and advanced_math_score >= 6:
            checks.extend(["sensitivity_checks", "stochastic_stability"])
        if test_commands:
            checks.extend(
                recommended_analysis_checks(
                    advanced_math_signals,
                    score=advanced_math_score,
                    has_validation_history=activity.has_validation_history,
                    has_oracle_benchmarks=activity.has_oracle_benchmarks,
                    has_drift_history=activity.has_drift_history,
                )
            )
        if (build_commands or test_commands) and (has_advanced_math or activity.has_oracle_benchmarks or activity.has_drift_history):
            checks.append("regression_checks")
        if perf_commands and (activity.has_oracle_benchmarks or activity.has_drift_history):
            checks.append("before_after_benchmark")
        for profile in verification_profiles:
            checks.extend(
                self._filter_supported_checks(
                    self.config.verification_profiles.get(profile, []),
                    build_commands=build_commands,
                    test_commands=test_commands,
                    browser_test_commands=browser_test_commands,
                    perf_commands=perf_commands,
                )
            )
        return list(dict.fromkeys(checks))

    def _risk_profile(
        self,
        has_numeric_logic: bool,
        has_advanced_math: bool,
        advanced_math_score: int,
        browser_test_commands: list[str],
        activity,
    ) -> str:
        if has_advanced_math and (advanced_math_score >= 10 or activity.has_oracle_benchmarks or activity.has_drift_history):
            return "high"
        if has_advanced_math and activity.has_validation_history and advanced_math_score >= 6:
            return "high"
        if has_numeric_logic and (activity.has_oracle_benchmarks or activity.has_drift_history):
            return "high"
        if has_advanced_math or has_numeric_logic or browser_test_commands or activity.has_validation_history:
            return "medium_high"
        return "medium"

    def _is_python_project(self, root: Path) -> bool:
        return any((root / name).exists() for name in ("pyproject.toml", "requirements.txt", "Pipfile", "environment.yml"))

    def _is_r_project(self, root: Path) -> bool:
        return bool(list(root.glob("*.Rproj"))) or any((root / name).exists() for name in ("DESCRIPTION", "app.R"))

    def _has_guidance_file(self, root: Path) -> bool:
        return any((root / filename).exists() for filename in self.config.roots.guidance_filenames)

    def _normalize_path_fragment(self, value: str) -> str:
        normalized = value.lower().replace("/", "\\")
        while "\\\\" in normalized:
            normalized = normalized.replace("\\\\", "\\")
        return normalized

    def _normalize_guidance_command(self, root: Path, command: str) -> str:
        def replace(match: re.Match[str]) -> str:
            raw_path = match.group("path")
            replacement = self._rewrite_project_path(root, raw_path)
            if replacement == raw_path:
                return match.group(0)
            quote = match.group("quote") if " " in replacement else ""
            return f"{quote}{replacement}{quote}"

        return WINDOWS_PATH_PATTERN.sub(replace, command)

    def _rewrite_project_path(self, root: Path, raw_path: str) -> str:
        normalized = self._normalize_path_fragment(raw_path)
        root_name = root.name.lower()
        marker = f"\\{root_name}"
        index = normalized.find(marker)
        if index == -1:
            return raw_path

        candidate = Path(normalized)
        if candidate.exists():
            return raw_path

        suffix = normalized[index + len(marker):].lstrip("\\")
        rewritten = root / Path(suffix) if suffix else root
        return str(rewritten)

    def _command_priority(self, command_type: str, command: str) -> tuple[int, int, str]:
        lowered = command.lower()
        executable_missing = int(not self._command_available(command))
        if command_type == "test":
            targeted_file = int(
                any(token in lowered for token in ("test_", "_test", ".spec", "spec."))
                and any(ext in lowered for ext in (".py", ".js", ".ts"))
            )
            functional_signal = int(any(token in lowered for token in ("functional", "validation", "smoke", "selenium", "playwright")))
            targeted_dir = int(("tests/" in lowered or "tests\\" in lowered) and not targeted_file)
            generic_pytest = int(lowered.strip() == "python -m pytest -q")
            return (executable_missing, -targeted_file, -functional_signal, -targeted_dir, generic_pytest, lowered)
        if command_type == "browser":
            automated_visual = int("automated_visual_test.html" in lowered)
            automated_suite = int("automated_test_suite.html" in lowered)
            validation_suite = int("validation_suite.html" in lowered)
            functional_signal = int(any(token in lowered for token in ("playwright", "selenium", "browser_checks", "visual", "validation")))
            return (
                executable_missing,
                -automated_suite,
                -automated_visual,
                -validation_suite,
                -functional_signal,
                lowered,
            )
        return (executable_missing, 0, 0, 0, 0, lowered)

    def _has_html_surface(self, root: Path) -> bool:
        if (root / "index.html").exists():
            return True
        return any(path.is_file() for path in root.glob("*.html"))

    def _has_javascript_surface(self, root: Path) -> bool:
        if (root / "app.js").exists() or (root / "worker.js").exists():
            return True
        return any(path.is_file() for path in root.glob("*.js"))

    def _command_available(self, command: str) -> bool:
        stripped = command.strip()
        if not stripped:
            return False
        if stripped.startswith('"'):
            executable = stripped.split('"', 2)[1]
        else:
            executable = stripped.split(" ", 1)[0]
        return shutil.which(executable) is not None

    def _advanced_math_signals(
        self,
        root: Path,
        guidance_summary: list[str],
        guidance_commands: list[str],
        activity,
    ) -> list[str]:
        combined_text = "\n".join(
            [
                root.name,
                *[path.name for path in root.iterdir()],
                *guidance_summary,
                *guidance_commands,
                *activity.summary,
            ]
        )
        signals = list(dict.fromkeys(detect_analysis_signals(combined_text) + list(activity.advanced_math_signals)))
        return signals

    def _filter_supported_checks(
        self,
        checks: list[str],
        *,
        build_commands: list[str],
        test_commands: list[str],
        browser_test_commands: list[str],
        perf_commands: list[str],
    ) -> list[str]:
        supported: list[str] = []
        for check in checks:
            if check == "build" and build_commands:
                supported.append(check)
            elif check in {
                "relevant_tests",
                "targeted_tests",
                "existing_tests",
                "numeric_regression",
                "deterministic_fixture_tests",
                "edge_case_tests",
                "output_comparison",
                "sensitivity_checks",
                "stochastic_stability",
                "calibration_checks",
                "heterogeneity_checks",
                "publication_bias_checks",
                "consistency_checks",
                "ranking_stability",
                "censoring_checks",
                "competing_risks_checks",
                "convergence_checks",
                "posterior_sanity_checks",
                "missing_data_checks",
                "correlation_structure_checks",
                "shape_constraint_checks",
                "temporal_backtest_checks",
                "measurement_error_checks",
                "decision_curve_checks",
                "threshold_stability_checks",
                "identification_checks",
                "variance_component_checks",
                "matrix_stability_checks",
                "distribution_robustness_checks",
                "model_assumption_checks",
            } and test_commands:
                supported.append(check)
            elif check in {"playwright", "targeted_browser_test", "smoke_flow", "accessibility_check"} and browser_test_commands:
                supported.append(check)
            elif check in {"lighthouse", "before_after_benchmark", "no_correctness_regression"} and perf_commands:
                supported.append(check)
            elif check in {"regression_checks", "cross_implementation_parity"} and (build_commands or test_commands):
                supported.append(check)
            elif check == "build_or_direct_evidence" and build_commands:
                supported.append(check)
        return supported
