# sentinel:skip-file — hardcoded paths are fixture/registry/audit-narrative data for this repo's research workflow, not portable application configuration. Same pattern as push_all_repos.py and E156 workbook files.
from __future__ import annotations

from overmind.runners.base import BaseRunnerAdapter
from overmind.runners.protocols import ONE_SHOT, RunnerProtocol


class CodexRunnerAdapter(BaseRunnerAdapter):

    def protocol(self) -> RunnerProtocol:
        return ONE_SHOT


