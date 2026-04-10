"""Agent-as-a-Judge: LLM-based verification of agent task completion.

Inspired by metauto-ai/agent-as-a-judge: after test commands pass, an LLM
reads the transcript + task requirements + verification results and gives a
structured verdict on whether the agent actually met the requirements.

Backends:
  - StubBackend:       deterministic, for tests
  - SubprocessBackend: calls `claude -p` or any CLI
  - GeminiBackend:     calls Google Gemini API (reads GEMINI_API_KEY from env/.env)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from urllib.request import Request, urlopen
from urllib.error import URLError

from overmind.storage.models import ProjectRecord, TaskRecord, VerificationResult, utc_now


# ── Data models ─────────────────────────────────────────────────────


@dataclass(slots=True)
class JudgeVerdict:
    passed: bool
    confidence: float  # 0.0–1.0
    reasoning: str
    concerns: list[str] = field(default_factory=list)
    requirements_met: list[str] = field(default_factory=list)
    requirements_missed: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)


# ── Backend protocol ────────────────────────────────────────────────


class JudgeBackend(Protocol):
    def query(self, prompt: str) -> str: ...


class SubprocessBackend:
    """Call an LLM CLI tool (e.g., `claude -p`) via subprocess."""

    def __init__(self, command: str = "claude -p", timeout: int = 120) -> None:
        self.command = command
        self.timeout = timeout

    def query(self, prompt: str) -> str:
        try:
            result = subprocess.run(
                self.command.split(),
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            return result.stdout.strip()
        except (subprocess.TimeoutExpired, OSError) as exc:
            return f"JUDGE_ERROR: {exc}"


class StubBackend:
    """Deterministic backend for testing."""

    def __init__(self, response: str = "VERDICT: PASS\nCONFIDENCE: 0.9\nREASONING: All requirements met.") -> None:
        self.response = response
        self.last_prompt: str | None = None

    def query(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self.response


class GeminiBackend:
    """Call Google Gemini API via REST (no SDK dependency).

    Reads GEMINI_API_KEY from:
      1. Environment variable
      2. .env file in project root (parent of overmind/ package)
    """

    ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(
        self,
        model: str = "gemini-2.0-flash",
        timeout: int = 120,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self._api_key = api_key

    @property
    def api_key(self) -> str:
        if self._api_key:
            return self._api_key
        key = os.environ.get("GEMINI_API_KEY", "")
        if key:
            return key
        # Try .env file
        env_path = Path(__file__).resolve().parents[2] / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("GEMINI_API_KEY="):
                    return line.split("=", 1)[1].strip()
        return ""

    def query(self, prompt: str) -> str:
        key = self.api_key
        if not key:
            return "JUDGE_ERROR: GEMINI_API_KEY not found in environment or .env file"
        url = self.ENDPOINT.format(model=self.model) + f"?key={key}"
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1024},
        })
        req = Request(url, data=payload.encode("utf-8"), method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "JUDGE_ERROR: empty response")
            return "JUDGE_ERROR: no candidates in response"
        except (URLError, OSError, json.JSONDecodeError, KeyError) as exc:
            return f"JUDGE_ERROR: {exc}"


# ── Judge prompt ────────────────────────────────────────────────────

JUDGE_PROMPT_TEMPLATE = """\
You are an independent verification judge.  Your task is to determine whether
an AI coding agent successfully completed the assigned task.

TASK:
{task_title}

REQUIRED VERIFICATION:
{required_verification}

PROJECT:
{project_name} ({project_path})

VERIFICATION RESULT:
Tests passed: {tests_passed}
Checks completed: {completed_checks}
Checks skipped: {skipped_checks}
Details: {details}

AGENT SESSION TRANSCRIPT (last {transcript_window} lines):
{transcript}

INSTRUCTIONS:
1. Assess whether the task requirements were actually met (not just "tests pass").
2. Look for signs of incomplete work, hacks, or workarounds.
3. Check if the verification evidence actually proves the task was done.

Respond in EXACTLY this format:
VERDICT: PASS or FAIL
CONFIDENCE: 0.0 to 1.0
REASONING: one paragraph explaining your assessment
CONCERNS: comma-separated list (or "none")
MET: comma-separated list of requirements met (or "none")
MISSED: comma-separated list of requirements missed (or "none")
"""


# ── LLM Judge ───────────────────────────────────────────────────────


class LLMJudge:
    """LLM-based judge that evaluates whether an agent completed its task."""

    def __init__(
        self,
        backend: JudgeBackend | None = None,
        transcript_window: int = 80,
    ) -> None:
        self.backend = backend or StubBackend()
        self.transcript_window = transcript_window

    def judge(
        self,
        task: TaskRecord,
        project: ProjectRecord,
        verification_result: VerificationResult,
        transcript_lines: list[str] | None = None,
    ) -> JudgeVerdict:
        """Submit task context to LLM and parse structured verdict."""
        prompt = self._build_prompt(task, project, verification_result, transcript_lines)
        response = self.backend.query(prompt)
        return self._parse_verdict(response)

    def _build_prompt(
        self,
        task: TaskRecord,
        project: ProjectRecord,
        result: VerificationResult,
        transcript_lines: list[str] | None,
    ) -> str:
        transcript = "\n".join(
            (transcript_lines or ["(no transcript available)"])[-self.transcript_window :]
        )
        return JUDGE_PROMPT_TEMPLATE.format(
            task_title=task.title,
            required_verification=", ".join(task.required_verification),
            project_name=project.name,
            project_path=project.root_path,
            tests_passed="yes" if result.success else "no",
            completed_checks=", ".join(result.completed_checks) or "none",
            skipped_checks=", ".join(result.skipped_checks) or "none",
            details="; ".join(result.details[:5]) or "none",
            transcript_window=self.transcript_window,
            transcript=transcript,
        )

    def _parse_verdict(self, response: str) -> JudgeVerdict:
        """Parse structured LLM response into JudgeVerdict."""
        if response.startswith("JUDGE_ERROR:"):
            return JudgeVerdict(
                passed=True,  # fail-open: don't block on judge errors
                confidence=0.0,
                reasoning=f"Judge unavailable: {response}",
                concerns=["judge_error"],
            )

        lines = response.strip().splitlines()
        fields: dict[str, str] = {}
        for line in lines:
            match = re.match(r"^(VERDICT|CONFIDENCE|REASONING|CONCERNS|MET|MISSED):\s*(.+)", line, re.IGNORECASE)
            if match:
                fields[match.group(1).upper()] = match.group(2).strip()

        passed = fields.get("VERDICT", "PASS").upper() == "PASS"
        try:
            confidence = float(fields.get("CONFIDENCE", "0.5"))
            confidence = max(0.0, min(1.0, confidence))
        except ValueError:
            confidence = 0.5

        reasoning = fields.get("REASONING", "No reasoning provided.")
        concerns = _parse_csv(fields.get("CONCERNS", "none"))
        met = _parse_csv(fields.get("MET", "none"))
        missed = _parse_csv(fields.get("MISSED", "none"))

        return JudgeVerdict(
            passed=passed,
            confidence=confidence,
            reasoning=reasoning,
            concerns=concerns,
            requirements_met=met,
            requirements_missed=missed,
        )


def _parse_csv(value: str) -> list[str]:
    """Parse comma-separated value, filtering 'none' and empty strings."""
    items = [item.strip() for item in value.split(",")]
    return [item for item in items if item and item.lower() != "none"]
