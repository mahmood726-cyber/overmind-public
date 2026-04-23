from __future__ import annotations

from collections import Counter
import queue
import subprocess
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from overmind.runners.protocols import INTERACTIVE, RunnerProtocol
from overmind.subprocess_utils import split_command
from overmind.sessions.output_stream import OutputStreamReader
from overmind.sessions.transcript_store import TranscriptStore
from overmind.storage.models import SessionObservation, utc_now


@dataclass(slots=True)
class TerminalSession:
    session_id: str
    runner_id: str
    task_id: str
    command: str
    cwd: Path
    transcript_store: TranscriptStore
    protocol: RunnerProtocol = field(default_factory=lambda: INTERACTIVE)
    output_blocker: Callable[[str], str | None] | None = None
    transcript_path: Path = field(init=False)
    buffer: queue.SimpleQueue[str] = field(default_factory=queue.SimpleQueue)
    process: subprocess.Popen[str] | None = None
    prompt_echo_budget: Counter[str] = field(default_factory=Counter)
    prompt_echo_started: bool = False
    total_line_count: int = 0
    started_at: str = field(default_factory=utc_now)
    last_output_at: str = field(default_factory=utc_now)
    started_at_epoch: float = field(default_factory=time.time)
    last_output_epoch: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        self.transcript_path = self.transcript_store.path_for(
            self.session_id, self.runner_id, self.task_id
        )

    def start(self, prompt: str) -> None:
        self.process = subprocess.Popen(
            split_command(self.command) if isinstance(self.command, str) else self.command,
            cwd=self.cwd,
            shell=False,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self.started_at = utc_now()
        self.last_output_at = self.started_at
        self.started_at_epoch = time.time()
        self.last_output_epoch = self.started_at_epoch
        self.transcript_store.append_event(self.transcript_path, f"SESSION START {self.command}")
        self.transcript_store.append_event(self.transcript_path, f"PROTOCOL {self.protocol.name}")
        if self.process.stdout is not None:
            OutputStreamReader(self.process.stdout, self._handle_output).start()
        if prompt:
            wrapped_prompt = self.protocol.wrap_prompt(prompt)
            self._prime_prompt_echo_budget(wrapped_prompt)
            self.send(wrapped_prompt)
            if self.protocol.close_stdin_after_prompt:
                self._close_stdin()

    def send(self, text: str) -> None:
        if not self.process or self.process.stdin is None or self.process.stdin.closed:
            return
        self.process.stdin.write(text)
        if not text.endswith("\n"):
            self.process.stdin.write("\n")
        self.process.stdin.flush()
        first_line = text.strip().splitlines()[0] if text.strip() else "<empty>"
        self.transcript_store.append_event(self.transcript_path, f"INPUT {first_line[:200]}")

    def observe(self) -> SessionObservation:
        lines: list[str] = []
        while True:
            try:
                raw_line = self.buffer.get_nowait()
            except queue.Empty:
                break
            filtered = self.protocol.filter_output(raw_line)
            if filtered is not None:
                lines.append(filtered)

        exit_code = self.process.poll() if self.process else None
        return SessionObservation(
            session_id=self.session_id,
            runner_id=self.runner_id,
            task_id=self.task_id,
            lines=lines,
            total_line_count=self.total_line_count,
            exit_code=exit_code,
            idle_seconds=round(time.time() - self.last_output_epoch, 2),
            runtime_seconds=round(time.time() - self.started_at_epoch, 2),
            started_at=self.started_at,
            last_output_at=self.last_output_at,
            command=self.command,
        )

    def stop(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        self.transcript_store.append_event(self.transcript_path, "SESSION STOP requested")
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()

    def _handle_output(self, line: str) -> None:
        self.total_line_count += 1
        self.last_output_at = utc_now()
        self.last_output_epoch = time.time()
        self.transcript_store.append_line(self.transcript_path, line)
        if self._consume_prompt_echo(line):
            return
        self.buffer.put(line)
        if self.output_blocker is not None:
            block_message = self.output_blocker(line)
            if block_message:
                self.transcript_store.append_event(
                    self.transcript_path,
                    f"SESSION STOP policy block: {block_message[:200]}",
                )
                self.stop()

    def _close_stdin(self) -> None:
        if not self.process or self.process.stdin is None or self.process.stdin.closed:
            return
        self.process.stdin.close()
        self.transcript_store.append_event(self.transcript_path, "STDIN CLOSED after initial prompt")

    def _prime_prompt_echo_budget(self, prompt: str) -> None:
        self.prompt_echo_budget = Counter(line.rstrip("\r\n") for line in prompt.splitlines())
        self.prompt_echo_started = False

    def _consume_prompt_echo(self, line: str) -> bool:
        normalized = line.rstrip("\r\n")
        if not self.prompt_echo_budget and not self.prompt_echo_started:
            return False

        if not self.prompt_echo_started:
            if normalized == "user":
                self.prompt_echo_started = True
                return True
            if self.prompt_echo_budget.get(normalized, 0):
                self.prompt_echo_started = True
            else:
                return False

        remaining = self.prompt_echo_budget.get(normalized, 0)
        if remaining > 0:
            if remaining == 1:
                del self.prompt_echo_budget[normalized]
            else:
                self.prompt_echo_budget[normalized] = remaining - 1
            return True

        if normalized == "user":
            return True

        self.prompt_echo_budget.clear()
        self.prompt_echo_started = False
        return False
