"""Per-stage timing for one chat turn, reported as a Server-Timing header.

Server-Timing is a standard header: browsers show it in the Network tab
(Timing section), and scripts/measure_latency.py reads it to report p50/p95
per stage against a live deployment.
"""
import time
from contextlib import contextmanager
from typing import Callable, Dict

__all__ = ["StageTimer"]


class StageTimer:
    def __init__(self, clock: Callable[[], float] = time.perf_counter):
        self._clock = clock
        self._started = clock()
        self.stages_ms: Dict[str, float] = {}

    @contextmanager
    def stage(self, name: str):
        start = self._clock()
        try:
            yield
        finally:
            self.stages_ms[name] = (self._clock() - start) * 1000

    def header(self) -> str:
        """e.g. "asr;dur=812, graph;dur=2431, tts;dur=903, total;dur=4170".
        Stages that didn't run (asr for a typed message) are left out."""
        parts = [f"{name};dur={ms:.0f}" for name, ms in self.stages_ms.items()]
        parts.append(f"total;dur={(self._clock() - self._started) * 1000:.0f}")
        return ", ".join(parts)
