"""LLM-based auto-repair using the Agentless pattern.

Given a diagnosis + failing test output, asks Claude to generate a minimal
patch. The patch is applied, re-verified, and rolled back if it fails.

Safety rules (inherited from AutoFixer):
- NEVER auto-fix FORMULA_ERROR or FLOAT_PRECISION (needs human judgment)
- Re-verify after every patch
- Roll back if verification fails
- Never commit — human reviews
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from overmind.diagnosis.judge import Diagnosis
from overmind.remediation.strategies import FixResult

CLAUDE_CMD = "claude"

# Failure types the LLM is allowed to attempt fixing
LLM_FIXABLE_TYPES = {
    "DEPENDENCY_ROT",
    "SYNTAX_ERROR",
    "MISSING_FIXTURE",
    "TEST_FAILURE",
    "PLATFORM_COMPAT",
    "CONFIGURATION",
    "TIMEOUT",
}

# Types that require human judgment — NEVER auto-fix
HUMAN_ONLY_TYPES = {
    "FORMULA_ERROR",
    "FLOAT_PRECISION",
    "NUMERICAL_DRIFT",
}

REPAIR_PROMPT = """You are a minimal-patch repair agent. Fix this failing project.

Project: {project_path}
Failure type: {failure_type}
Diagnosis: {summary}
Recommended action: {recommended_action}
Failing file: {failing_file}

Evidence:
{evidence}

Project documentation:
{project_docs}

Rules:
1. Generate the SMALLEST possible fix — target the specific failing file, not the whole project
2. Do NOT change any formula, mathematical constant, or numerical logic
3. Do NOT add new features — only fix the diagnosed issue
4. If the fix requires installing a package, output: INSTALL: package_name
5. If the fix requires a code change, output the exact file path and the change

Respond with ONLY valid JSON:
{{
  "fix_type": "install" | "code_change" | "config_change" | "cannot_fix",
  "description": "one line description",
  "install_package": "package_name or null",
  "file_changes": [
    {{"file": "relative/path.py", "old": "exact text to replace", "new": "replacement text"}}
  ]
}}
"""


@dataclass
class LLMRepairResult:
    fix_type: str
    description: str
    install_package: str | None
    file_changes: list[dict]


class LLMRepairer:
    """Generates and applies minimal patches using Claude CLI."""

    def __init__(self, timeout: int = 60, dry_run: bool = False) -> None:
        self.timeout = timeout
        self.dry_run = dry_run

    def can_fix(self, diagnosis: Diagnosis) -> bool:
        return diagnosis.failure_type in LLM_FIXABLE_TYPES

    def attempt_repair(
        self,
        diagnosis: Diagnosis,
        project_path: str,
        verify_fn=None,
    ) -> FixResult:
        """Generate an LLM patch, apply it, verify, and roll back on failure."""
        if diagnosis.failure_type in HUMAN_ONLY_TYPES:
            return FixResult(False, "skip", f"LLM repair blocked: {diagnosis.failure_type} requires human")

        if not self.can_fix(diagnosis):
            return FixResult(False, "skip", f"LLM repair not applicable for {diagnosis.failure_type}")

        # Generate repair plan
        plan = self._generate_plan(diagnosis, project_path)
        if plan is None:
            return FixResult(False, "llm_repair", "Claude CLI failed or returned invalid JSON")

        if plan.fix_type == "cannot_fix":
            return FixResult(False, "llm_repair", f"LLM says cannot fix: {plan.description}")

        if self.dry_run:
            return FixResult(False, "llm_repair_dry_run", f"Would: {plan.description}")

        # Apply the fix
        applied_changes: list[tuple[str, str, str]] = []  # (file, old, new) for rollback

        if plan.fix_type == "install" and plan.install_package:
            return self._try_install(plan.install_package)

        if plan.fix_type in ("code_change", "config_change") and plan.file_changes:
            # Apply each file change, tracking for rollback
            for change in plan.file_changes[:3]:  # Max 3 files
                file_path = Path(project_path) / change.get("file", "")
                if not file_path.exists():
                    continue
                # Safety: don't modify files outside project
                if not str(file_path.resolve()).startswith(str(Path(project_path).resolve())):
                    continue

                old_text = change.get("old", "")
                new_text = change.get("new", "")
                if not old_text or not new_text or old_text == new_text:
                    continue

                content = file_path.read_text(encoding="utf-8")
                if old_text not in content:
                    continue

                # Apply change
                new_content = content.replace(old_text, new_text, 1)
                file_path.write_text(new_content, encoding="utf-8")
                applied_changes.append((str(file_path), old_text, new_text))

            if not applied_changes:
                return FixResult(False, "llm_repair", "No changes could be applied (text not found in files)")

            # Re-verify
            if verify_fn:
                if verify_fn(project_path):
                    return FixResult(
                        True, f"llm_repair ({len(applied_changes)} changes)",
                        f"{plan.description} | verified PASS"
                    )
                else:
                    # Roll back
                    for file_path, old_text, new_text in applied_changes:
                        content = Path(file_path).read_text(encoding="utf-8")
                        content = content.replace(new_text, old_text, 1)
                        Path(file_path).write_text(content, encoding="utf-8")
                    return FixResult(
                        False, "llm_repair (rolled back)",
                        f"Patch applied but verification failed — rolled back"
                    )

            # No verify_fn — report success but note unverified
            return FixResult(
                True, f"llm_repair ({len(applied_changes)} changes, unverified)",
                plan.description
            )

        return FixResult(False, "llm_repair", f"Unknown fix_type: {plan.fix_type}")

    def _generate_plan(self, diagnosis: Diagnosis, project_path: str) -> LLMRepairResult | None:
        # Extract specific failing file from evidence (DRV paper: narrow scope)
        failing_file = "unknown"
        for ev in diagnosis.evidence:
            import re
            m = re.search(r'File "([^"]+)"', ev)
            if m:
                failing_file = m.group(1)
                break

        # Load project documentation (RepoRepair pattern)
        project_docs = "No documentation found."
        for doc_name in ("CLAUDE.md", "README.md", "AGENTS.md"):
            doc_path = Path(project_path) / doc_name
            if doc_path.exists():
                try:
                    content = doc_path.read_text(encoding="utf-8")[:500]
                    project_docs = f"{doc_name}:\n{content}"
                    break
                except OSError:
                    pass

        prompt = REPAIR_PROMPT.format(
            project_path=project_path,
            failure_type=diagnosis.failure_type,
            summary=diagnosis.summary[:200],
            recommended_action=diagnosis.recommended_action[:200],
            evidence="\n".join(diagnosis.evidence[:3]),
            failing_file=failing_file,
            project_docs=project_docs[:600],
        )

        try:
            proc = subprocess.run(
                [CLAUDE_CMD, "--print", "-p", prompt],
                capture_output=True, text=True, timeout=self.timeout,
            )
            if proc.returncode != 0:
                return None

            response = proc.stdout.strip()
            if response.startswith("```"):
                response = response.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            data = json.loads(response)
            return LLMRepairResult(
                fix_type=data.get("fix_type", "cannot_fix"),
                description=data.get("description", "")[:200],
                install_package=data.get("install_package"),
                file_changes=data.get("file_changes", []),
            )
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            return None

    def _try_install(self, package: str) -> FixResult:
        """Try pip install with validation."""
        import re
        if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]*', package):
            return FixResult(False, "llm_repair", f"Invalid package name: {package}")

        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "install", package, "--quiet"],
                capture_output=True, text=True, timeout=60,
            )
            if proc.returncode == 0:
                return FixResult(True, f"pip install {package}", "Installed by LLM recommendation")
            return FixResult(False, f"pip install {package}", proc.stderr[-200:])
        except (subprocess.TimeoutExpired, OSError) as exc:
            return FixResult(False, f"pip install {package}", str(exc))
