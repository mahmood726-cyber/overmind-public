from __future__ import annotations

import re

from overmind.storage.models import ProjectRecord, TaskRecord


class VerificationPlanner:
    def plan(self, task: TaskRecord, project: ProjectRecord) -> dict[str, list[str]]:
        plan: dict[str, list[str]] = {}
        for check in task.required_verification:
            plan[check] = self._commands_for(check, project)
        return plan

    def _commands_for(self, check: str, project: ProjectRecord) -> list[str]:
        if check == "build":
            return project.build_commands[:1]
        if check in {"relevant_tests", "targeted_tests", "existing_tests"}:
            return self._relevant_test_commands(project)
        if check in {
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
        }:
            return self._numeric_test_commands(project)
        if check in {"playwright", "targeted_browser_test", "smoke_flow", "accessibility_check"}:
            return project.browser_test_commands[:1]
        if check in {"lighthouse", "before_after_benchmark", "no_correctness_regression"}:
            return project.perf_commands[:1]
        if check in {"regression_checks", "cross_implementation_parity"}:
            return self._regression_commands(project)
        if check == "build_or_direct_evidence":
            return project.build_commands[:1]
        return []

    def _relevant_test_commands(self, project: ProjectRecord) -> list[str]:
        return self._pick_test_command(project.test_commands, mode="relevant")

    def _numeric_test_commands(self, project: ProjectRecord) -> list[str]:
        return self._pick_test_command(project.test_commands, mode="numeric")

    def _broad_test_commands(self, project: ProjectRecord, *, exclude: set[str] | None = None) -> list[str]:
        return self._pick_test_command(project.test_commands, mode="broad", exclude=exclude)

    def _regression_commands(self, project: ProjectRecord) -> list[str]:
        commands: list[str] = []
        commands.extend(project.build_commands[:1])

        relevant = self._relevant_test_commands(project)
        numeric = self._numeric_test_commands(project)
        broad = self._broad_test_commands(project, exclude=set(relevant + numeric))

        for command in [*relevant, *broad, *numeric]:
            if command and command not in commands:
                commands.append(command)
        return commands

    def _pick_test_command(
        self,
        commands: list[str],
        *,
        mode: str,
        exclude: set[str] | None = None,
    ) -> list[str]:
        exclude = exclude or set()
        candidates = [command for command in commands if command not in exclude]
        if not candidates:
            return []
        selected = min(candidates, key=lambda command: self._test_command_priority(command, mode))
        return [selected]

    def _test_command_priority(self, command: str, mode: str) -> tuple[int, int, int, int, str]:
        lowered = command.lower()
        feature_text = self._command_feature_text(command)
        is_pytest = int("pytest" in feature_text)
        is_smoke = int("smoke" in feature_text)
        is_numeric = int(
            any(
                token in feature_text
                for token in (
                    "validation",
                    "r_validation",
                    "oracle",
                    "benchmark",
                    "metafor",
                    "compare",
                    "comparison",
                    "numeric",
                    "accuracy",
                    "reference",
                )
            )
        )
        is_broad = int(
            any(
                token in feature_text
                for token in ("functional", "suite", "integration", "selenium", "playwright", "test_")
            )
        )

        if mode == "relevant":
            return (-is_pytest, -is_smoke, -is_broad, is_numeric, lowered)
        if mode == "numeric":
            return (-is_numeric, -is_broad, -is_pytest, -is_smoke, lowered)
        return (-is_broad, is_numeric, -is_pytest, -is_smoke, lowered)

    def _command_feature_text(self, command: str) -> str:
        parts = re.findall(r'"([^"]+)"|\'([^\']+)\'|(\S+)', command)
        normalized_parts: list[str] = []
        for groups in parts:
            token = next((part for part in groups if part), "")
            lowered = token.lower()
            if "\\" in lowered or "/" in lowered:
                normalized_parts.append(lowered.replace("\\", "/").rsplit("/", 1)[-1])
            else:
                normalized_parts.append(lowered)
        return " ".join(normalized_parts)
