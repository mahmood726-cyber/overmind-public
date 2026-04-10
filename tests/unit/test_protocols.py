from __future__ import annotations

import sys

from overmind.config import AppConfig, RunnerDefinition
from overmind.runners.base import BaseRunnerAdapter
from overmind.runners.claude_runner import ClaudeRunnerAdapter
from overmind.runners.codex_runner import CodexRunnerAdapter
from overmind.runners.gemini_runner import GeminiRunnerAdapter
from overmind.runners.protocols import INTERACTIVE, ONE_SHOT, PIPE
from overmind.runners.runner_registry import RunnerRegistry
from overmind.storage.db import StateDatabase


# ---------------------------------------------------------------------------
# Protocol property tests
# ---------------------------------------------------------------------------

def test_interactive_protocol_properties():
    assert INTERACTIVE.name == "interactive"
    assert INTERACTIVE.close_stdin_after_prompt is False
    assert INTERACTIVE.supports_intervention is True
    assert INTERACTIVE.capacity_error_patterns == ()


def test_one_shot_protocol_properties():
    assert ONE_SHOT.name == "one_shot"
    assert ONE_SHOT.close_stdin_after_prompt is True
    assert ONE_SHOT.supports_intervention is False
    assert ONE_SHOT.capacity_error_patterns == ()


def test_pipe_protocol_properties():
    assert PIPE.name == "pipe"
    assert PIPE.close_stdin_after_prompt is False
    assert PIPE.supports_intervention is True
    assert len(PIPE.capacity_error_patterns) == 5


# ---------------------------------------------------------------------------
# Gemini prompt wrapper
# ---------------------------------------------------------------------------

def test_gemini_prompt_wrapper_adds_prefix():
    raw = "Explain this code."
    wrapped = PIPE.wrap_prompt(raw)
    assert wrapped.startswith("Be concise.")
    assert wrapped.endswith(raw)
    assert "no unicode borders" in wrapped


def test_interactive_prompt_wrapper_is_identity():
    raw = "Hello world"
    assert INTERACTIVE.wrap_prompt(raw) == raw


def test_one_shot_prompt_wrapper_is_identity():
    raw = "Hello world"
    assert ONE_SHOT.wrap_prompt(raw) == raw


# ---------------------------------------------------------------------------
# Gemini output filter
# ---------------------------------------------------------------------------

def test_gemini_filter_drops_star_line():
    assert PIPE.filter_output("★ Insight ─────") is None


def test_gemini_filter_drops_heavy_border():
    assert PIPE.filter_output("═══════════════════") is None


def test_gemini_filter_drops_light_border():
    assert PIPE.filter_output("─────────────────") is None


def test_gemini_filter_drops_indented_border():
    assert PIPE.filter_output("   ═══════════════") is None


def test_gemini_filter_keeps_real_content():
    line = "  result = x + y"
    assert PIPE.filter_output(line) == line


def test_gemini_filter_keeps_empty_line():
    assert PIPE.filter_output("") == ""


def test_interactive_filter_passes_all():
    assert INTERACTIVE.filter_output("★ Insight ─────") == "★ Insight ─────"


# ---------------------------------------------------------------------------
# Gemini capacity error patterns
# ---------------------------------------------------------------------------

def test_gemini_capacity_patterns_match():
    patterns = PIPE.capacity_error_patterns
    assert "too many people" in patterns
    assert "at capacity" in patterns
    assert "overloaded" in patterns
    assert "try again later" in patterns
    assert "temporarily unavailable" in patterns


def test_claude_codex_have_no_capacity_patterns():
    assert INTERACTIVE.capacity_error_patterns == ()
    assert ONE_SHOT.capacity_error_patterns == ()


# ---------------------------------------------------------------------------
# Adapter protocol wiring
# ---------------------------------------------------------------------------

def _make_definition(runner_type: str) -> RunnerDefinition:
    return RunnerDefinition(
        runner_id=f"{runner_type}_test",
        type=runner_type,
        mode="terminal",
        command=f'"{sys.executable}" -V',
        environment="windows",
    )


def test_claude_adapter_returns_interactive():
    adapter = ClaudeRunnerAdapter(_make_definition("claude"))
    assert adapter.protocol() is INTERACTIVE


def test_codex_adapter_returns_one_shot():
    adapter = CodexRunnerAdapter(_make_definition("codex"))
    assert adapter.protocol() is ONE_SHOT


def test_gemini_adapter_returns_pipe():
    adapter = GeminiRunnerAdapter(_make_definition("gemini"))
    assert adapter.protocol() is PIPE


def test_base_adapter_defaults_to_interactive():
    adapter = BaseRunnerAdapter(_make_definition("unknown"))
    assert adapter.protocol() is INTERACTIVE


# ---------------------------------------------------------------------------
# RunnerRegistry.adapter_for
# ---------------------------------------------------------------------------

def test_adapter_for_returns_correct_adapter(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    data_dir.mkdir()

    (config_dir / "roots.yaml").write_text(
        "scan_roots: []\n"
        "scan_rules:\n"
        "  include_git_repos: true\n"
        "  include_non_git_apps: true\n"
        "  incremental_scan: true\n"
        "  max_depth: 2\n"
        "guidance_filenames:\n"
        "  - \"README.md\"\n",
        encoding="utf-8",
    )
    (config_dir / "runners.yaml").write_text(
        "runners:\n"
        "  - runner_id: claude_main\n"
        "    type: claude\n"
        "    mode: terminal\n"
        f"    command: '\"{sys.executable}\" -V'\n"
        "    environment: windows\n"
        "  - runner_id: codex_main\n"
        "    type: codex\n"
        "    mode: terminal\n"
        f"    command: '\"{sys.executable}\" -V'\n"
        "    environment: windows\n"
        "  - runner_id: gemini_main\n"
        "    type: gemini\n"
        "    mode: terminal\n"
        f"    command: '\"{sys.executable}\" -V'\n"
        "    environment: windows\n",
        encoding="utf-8",
    )
    (config_dir / "policies.yaml").write_text(
        "concurrency:\n  default_active_sessions: 1\n  max_active_sessions: 1\n  degraded_sessions: 1\n"
        "limits:\n  idle_timeout_min: 10\n  summary_trigger_output_lines: 400\n"
        "routing: {}\n"
        "risk_policy: {}\n",
        encoding="utf-8",
    )
    (config_dir / "projects_ignore.yaml").write_text(
        "ignored_directories: []\nignored_file_suffixes: []\n",
        encoding="utf-8",
    )
    (config_dir / "verification_profiles.yaml").write_text(
        "profiles: {}\nproject_rules: []\n",
        encoding="utf-8",
    )

    config = AppConfig.from_directory(
        config_dir=config_dir, data_dir=data_dir, db_path=data_dir / "state.db"
    )
    db = StateDatabase(config.db_path)
    try:
        registry = RunnerRegistry(config=config, db=db)

        claude_adapter = registry.adapter_for("claude_main")
        assert isinstance(claude_adapter, ClaudeRunnerAdapter)
        assert claude_adapter.protocol() is INTERACTIVE

        codex_adapter = registry.adapter_for("codex_main")
        assert isinstance(codex_adapter, CodexRunnerAdapter)
        assert codex_adapter.protocol() is ONE_SHOT

        gemini_adapter = registry.adapter_for("gemini_main")
        assert isinstance(gemini_adapter, GeminiRunnerAdapter)
        assert gemini_adapter.protocol() is PIPE

        assert registry.adapter_for("nonexistent") is None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Protocol is frozen
# ---------------------------------------------------------------------------

def test_protocol_is_frozen():
    import pytest
    with pytest.raises(AttributeError):
        INTERACTIVE.name = "changed"  # type: ignore[misc]
