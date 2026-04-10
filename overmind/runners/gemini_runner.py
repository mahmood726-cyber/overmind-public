from __future__ import annotations

from overmind.runners.base import BaseRunnerAdapter
from overmind.runners.protocols import PIPE, RunnerProtocol


class GeminiRunnerAdapter(BaseRunnerAdapter):

    def protocol(self) -> RunnerProtocol:
        return PIPE

