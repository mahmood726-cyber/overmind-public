from __future__ import annotations

from overmind.runners.base import BaseRunnerAdapter
from overmind.runners.protocols import INTERACTIVE, RunnerProtocol


class ClaudeRunnerAdapter(BaseRunnerAdapter):

    def protocol(self) -> RunnerProtocol:
        return INTERACTIVE

