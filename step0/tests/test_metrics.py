from __future__ import annotations

import pytest

from step0.metrics import LatencyRecorder


def test_latency_summary_reports_percentiles_without_content() -> None:
    recorder = LatencyRecorder()
    for value in (10, 20, 30, 40, 100):
        recorder.add("tool_ms", value)
    summary = recorder.summary()["tool_ms"]
    assert summary == {"count": 5, "p50_ms": 30.0, "p95_ms": 88.0, "max_ms": 100.0}


def test_invalid_metric_values_are_rejected() -> None:
    recorder = LatencyRecorder()
    with pytest.raises(ValueError):
        recorder.add("llm_ms", -1)
