from __future__ import annotations

import subprocess
from pathlib import Path

from overmind.subprocess_utils import split_command

from overmind.storage.models import ProjectRecord, TaskRecord, VerificationResult
from overmind.verification.profiles import VerificationPlanner


class VerificationEngine:
    def __init__(self, artifacts_dir: Path, verification_timeout: int = 900) -> None:
        self.artifacts_dir = artifacts_dir
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.planner = VerificationPlanner()
        self.verification_timeout = verification_timeout

    def run(self, task: TaskRecord, project: ProjectRecord) -> VerificationResult:
        completed_checks: list[str] = []
        skipped_checks: list[str] = []
        details: list[str] = []
        success = True
        cached_results: dict[str, tuple[bool, str]] = {}

        for check, commands in self.planner.plan(task, project).items():
            if not commands:
                skipped_checks.append(f"{check}: no command discovered")
                if check != "build_or_direct_evidence":
                    success = False
                continue

            check_passed = True
            for index, command in enumerate(commands, start=1):
                if command in cached_results:
                    cached_success, source_check = cached_results[command]
                    details.append(f"{check}: reused verification evidence from {source_check} command={command}")
                    if not cached_success:
                        check_passed = False
                        success = False
                        break
                    continue

                exit_code, stdout, stderr = self._run_command(command, project.root_path)

                artifact_path = self.artifacts_dir / f"{task.task_id}_{check}_{index}.log"
                artifact_path.write_text(
                    f"$ {command}\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}",
                    encoding="utf-8",
                )
                details.append(f"{check}: exit={exit_code} command={command}")
                if exit_code == -1:
                    details.append(f"{check}: timed out after {self.verification_timeout}s")
                cached_results[command] = (exit_code == 0, check)
                if exit_code != 0:
                    check_passed = False
                    success = False
                    break
            if check_passed:
                completed_checks.append(check)

        return VerificationResult(
            task_id=task.task_id,
            success=success,
            required_checks=task.required_verification,
            completed_checks=completed_checks,
            skipped_checks=skipped_checks,
            details=details,
        )

    def _run_command(self, command: str, cwd: str) -> tuple[int, str, str]:
        try:
            proc = subprocess.Popen(
                split_command(command),
                cwd=cwd,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                stdout, stderr = proc.communicate(timeout=self.verification_timeout)
                return proc.returncode, stdout, stderr
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    stdout, stderr = proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    stdout, stderr = "", ""
                return -1, stdout, f"Command timed out after {self.verification_timeout}s"
        except OSError as exc:
            return -1, "", f"Failed to start command: {exc}"
