from __future__ import annotations

from overmind.runners.base import BaseRunnerAdapter
from overmind.runners.protocols import ONE_SHOT, RunnerProtocol


class CodexRunnerAdapter(BaseRunnerAdapter):

    def protocol(self) -> RunnerProtocol:
        return ONE_SHOT

