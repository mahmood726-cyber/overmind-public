from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

_GEMINI_CONCISENESS_PREFIX = (
    "Be concise. No decorative formatting, no insight boxes, "
    "no unicode borders. Print commands and results only.\n\n"
)

_GEMINI_DECORATIVE_RE = re.compile(
    r"^[\s]*(?:[─═╔╗╚╝║│┌┐└┘┬┴├┤┼]{3,}|★.*[─═]{3,})"
)

_GEMINI_CAPACITY_PATTERNS: tuple[str, ...] = (
    "too many people",
    "at capacity",
    "overloaded",
    "try again later",
    "temporarily unavailable",
)


def _identity(text: str) -> str:
    return text


def _gemini_prompt_wrapper(text: str) -> str:
    return _GEMINI_CONCISENESS_PREFIX + text


def _no_filter(line: str) -> str | None:
    return line


def _gemini_output_filter(line: str) -> str | None:
    if _GEMINI_DECORATIVE_RE.match(line):
        return None
    return line


@dataclass(frozen=True, slots=True)
class RunnerProtocol:
    """Protocol descriptor for a runner type."""

    name: str
    close_stdin_after_prompt: bool
    supports_intervention: bool
    prompt_wrapper: Callable[[str], str]
    output_filter: Callable[[str], str | None]
    capacity_error_patterns: tuple[str, ...]

    def wrap_prompt(self, prompt: str) -> str:
        return self.prompt_wrapper(prompt)

    def filter_output(self, line: str) -> str | None:
        return self.output_filter(line)


INTERACTIVE = RunnerProtocol(
    name="interactive",
    close_stdin_after_prompt=False,
    supports_intervention=True,
    prompt_wrapper=_identity,
    output_filter=_no_filter,
    capacity_error_patterns=(),
)

ONE_SHOT = RunnerProtocol(
    name="one_shot",
    close_stdin_after_prompt=True,
    supports_intervention=False,
    prompt_wrapper=_identity,
    output_filter=_no_filter,
    capacity_error_patterns=(),
)

PIPE = RunnerProtocol(
    name="pipe",
    close_stdin_after_prompt=False,
    supports_intervention=True,
    prompt_wrapper=_gemini_prompt_wrapper,
    output_filter=_gemini_output_filter,
    capacity_error_patterns=_GEMINI_CAPACITY_PATTERNS,
)
