from __future__ import annotations

import re
from pathlib import Path

from overmind.runners.protocols import INTERACTIVE, RunnerProtocol
from overmind.sessions.terminal_session import TerminalSession
from overmind.sessions.transcript_store import TranscriptStore
from overmind.storage.models import Assignment, ProjectRecord, RunnerRecord, SessionObservation

EXEC_SUBCOMMAND_PATTERN = re.compile(r"\bexec\b", re.IGNORECASE)
SKIP_GIT_REPO_CHECK_PATTERN = re.compile(
    r"(^|\s)--skip-git-repo-check(\s|$)",
    re.IGNORECASE,
)
SANDBOX_FLAG_PATTERN = re.compile(
    r"(^|\s)(-s|--sandbox)\s+\S+|--full-auto|--dangerously-bypass-approvals-and-sandbox",
    re.IGNORECASE,
)
APPROVAL_FLAG_PATTERN = re.compile(
    r"(^|\s)(-a|--ask-for-approval)\s+\S+|--full-auto|--dangerously-bypass-approvals-and-sandbox",
    re.IGNORECASE,
)


class SessionManager:
    def __init__(self, transcripts_dir: Path) -> None:
        self.transcript_store = TranscriptStore(transcripts_dir)
        self.max_active_sessions = 1
        self.sessions: dict[str, TerminalSession] = {}

    def reconcile(self, max_active_sessions: int) -> None:
        self.max_active_sessions = max_active_sessions
        active_sessions = list(self.sessions.values())
        if len(active_sessions) <= max_active_sessions:
            return
        for session in active_sessions[max_active_sessions:]:
            session.stop()
            self.sessions.pop(session.session_id, None)

    def dispatch(
        self,
        assignments: list[Assignment],
        runners: dict[str, RunnerRecord],
        projects: dict[str, ProjectRecord],
        protocols: dict[str, RunnerProtocol] | None = None,
    ) -> list[str]:
        started: list[str] = []
        if self.active_count() >= self.max_active_sessions:
            return started
        protocols = protocols or {}

        for assignment in assignments:
            if self.active_count() >= self.max_active_sessions:
                break
            if assignment.task_id in self.active_tasks():
                continue
            runner = runners.get(assignment.runner_id)
            project = projects.get(assignment.project_id)
            if not runner or not project:
                continue
            session_id = f"{assignment.runner_id}_{assignment.task_id}"
            session = TerminalSession(
                session_id=session_id,
                runner_id=assignment.runner_id,
                task_id=assignment.task_id,
                command=self._launch_command(runner),
                cwd=Path(project.root_path),
                transcript_store=self.transcript_store,
                protocol=protocols.get(assignment.runner_id, INTERACTIVE),
            )
            session.start(assignment.prompt)
            self.sessions[session_id] = session
            started.append(assignment.task_id)
        return started

    def collect_output(self) -> list[SessionObservation]:
        observations: list[SessionObservation] = []
        finished: list[str] = []
        for session_id, session in list(self.sessions.items()):
            observation = session.observe()
            if observation.lines or observation.exit_code is not None:
                observations.append(observation)
            if observation.exit_code is not None:
                finished.append(session_id)
        for session_id in finished:
            self.sessions.pop(session_id, None)
        return observations

    def apply_interventions(self, actions: list[dict[str, str]]) -> None:
        for action in actions:
            task_id = action.get("task_id")
            session = self._find_by_task(task_id) if task_id else None
            if not session:
                continue
            if action.get("action") == "send_message":
                if not session.protocol.supports_intervention:
                    continue
                session.send(action.get("message", ""))
            elif action.get("action") == "pause":
                session.stop()
                self.sessions.pop(session.session_id, None)

    def active_assignments(self) -> dict[str, str]:
        return {
            session.runner_id: session.task_id
            for session in self.sessions.values()
            if session.process and session.process.poll() is None
        }

    def active_tasks(self) -> set[str]:
        return {session.task_id for session in self.sessions.values()}

    def active_count(self) -> int:
        return len(self.active_assignments())

    def _find_by_task(self, task_id: str) -> TerminalSession | None:
        for session in self.sessions.values():
            if session.task_id == task_id:
                return session
        return None

    def _launch_command(self, runner: RunnerRecord) -> str:
        command = runner.command.strip()
        if runner.runner_type.lower() != "codex":
            return command

        executable = self._command_executable(command)
        if Path(executable).stem.lower() != "codex":
            return command

        if EXEC_SUBCOMMAND_PATTERN.search(command):
            normalized = command
            if not SANDBOX_FLAG_PATTERN.search(normalized) and not APPROVAL_FLAG_PATTERN.search(normalized):
                normalized = EXEC_SUBCOMMAND_PATTERN.sub(
                    " --dangerously-bypass-approvals-and-sandbox exec",
                    normalized,
                    count=1,
                )
            if not SKIP_GIT_REPO_CHECK_PATTERN.search(normalized):
                normalized = EXEC_SUBCOMMAND_PATTERN.sub(
                    "exec --skip-git-repo-check",
                    normalized,
                    count=1,
                )
            return normalized

        prefix_parts: list[str] = []
        if not SANDBOX_FLAG_PATTERN.search(command) and not APPROVAL_FLAG_PATTERN.search(command):
            prefix_parts.append("--dangerously-bypass-approvals-and-sandbox")
        suffix_parts = ["exec"]
        if not SKIP_GIT_REPO_CHECK_PATTERN.search(command):
            suffix_parts.append("--skip-git-repo-check")
        suffix_parts.append("-")
        return f"{command} {' '.join([*prefix_parts, *suffix_parts])}".strip()

    @staticmethod
    def _command_executable(command: str) -> str:
        stripped = command.strip()
        if stripped.startswith('"'):
            parts = stripped.split('"', 2)
            return parts[1] if len(parts) > 1 else stripped.strip('"')
        return stripped.split(" ", 1)[0]
