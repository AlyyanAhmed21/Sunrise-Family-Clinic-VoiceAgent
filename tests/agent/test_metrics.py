from __future__ import annotations

import logging
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from livekit.agents.llm import ChatMessage

from agent.metrics import attach_session_metrics


class FakeEmitter:
    def __init__(self) -> None:
        self.handlers: dict[str, Callable[[Any], None]] = {}

    def on(self, event: str) -> Callable[[Callable[[Any], None]], Callable[[Any], None]]:
        def register(handler: Callable[[Any], None]) -> Callable[[Any], None]:
            self.handlers[event] = handler
            return handler

        return register


class TTSMetrics:
    def __init__(self) -> None:
        self.ttfb = 0.4
        self.duration = 2.0
        self.audio_duration = 4.0
        self.timestamp = 123.0


def test_tts_metrics_include_real_time_factor(caplog: pytest.LogCaptureFixture) -> None:
    session = FakeEmitter()
    attach_session_metrics(session, "call-1")  # type: ignore[arg-type]

    with caplog.at_level(logging.INFO, logger="sunrise.agent.metrics"):
        session.handlers["metrics_collected"](SimpleNamespace(metrics=TTSMetrics()))

    assert '"real_time_factor": 0.5' in caplog.text
    assert '"ttfb": 0.4' in caplog.text
    assert "timestamp" not in caplog.text


def test_turn_latency_logs_numbers_never_content(caplog: pytest.LogCaptureFixture) -> None:
    session = FakeEmitter()
    attach_session_metrics(session, "call-1")  # type: ignore[arg-type]
    message = ChatMessage(role="user", content=["my secret words"])
    message.metrics["end_of_turn_delay"] = 0.62
    message.metrics["started_speaking_at"] = 1700000000.0

    with caplog.at_level(logging.INFO, logger="sunrise.agent.metrics"):
        session.handlers["conversation_item_added"](SimpleNamespace(item=message))

    assert '"end_of_turn_delay": 0.62' in caplog.text
    assert "secret" not in caplog.text
    assert "started_speaking_at" not in caplog.text
