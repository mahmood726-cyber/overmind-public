from __future__ import annotations

import threading
from typing import Callable, TextIO


class OutputStreamReader(threading.Thread):
    def __init__(self, stream: TextIO, sink: Callable[[str], None]) -> None:
        super().__init__(daemon=True)
        self.stream = stream
        self.sink = sink

    def run(self) -> None:
        for line in iter(self.stream.readline, ""):
            self.sink(line.rstrip("\r\n"))

