"""Content-free latency samples and percentile summaries for Step 0."""

from __future__ import annotations

import json
import logging
import math
import time
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

_LOG = logging.getLogger("sunrise.step0.metrics")


@dataclass(frozen=True, slots=True)
class Sample:
    name: str
    duration_ms: float
    call_id: str = "step0"


class LatencyRecorder:
    """Collect numeric timings only; this class has no transcript/content field."""

    def __init__(self) -> None:
        self._samples: dict[str, list[float]] = defaultdict(list)

    def add(self, name: str, duration_ms: float) -> None:
        if not name or duration_ms < 0 or not math.isfinite(duration_ms):
            raise ValueError("metric name and finite non-negative duration are required")
        self._samples[name].append(float(duration_ms))
        _LOG.info(
            json.dumps(
                {"event": "latency_sample", "metric": name, "duration_ms": round(duration_ms, 2)}
            )
        )

    def measure(self, name: str):
        """Return a context manager that records elapsed wall-clock milliseconds."""
        return _Measure(self, name)

    def summary(self) -> dict[str, dict[str, float | int]]:
        return {name: _summary(values) for name, values in sorted(self._samples.items())}


class _Measure:
    def __init__(self, recorder: LatencyRecorder, name: str) -> None:
        self.recorder, self.name = recorder, name
        self.started = 0.0

    def __enter__(self) -> _Measure:
        self.started = time.perf_counter()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.recorder.add(self.name, (time.perf_counter() - self.started) * 1000)


def _percentile(values: Iterable[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _summary(values: list[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "p50_ms": round(_percentile(values, 0.50), 2),
        "p95_ms": round(_percentile(values, 0.95), 2),
        "max_ms": round(max(values), 2),
    }
