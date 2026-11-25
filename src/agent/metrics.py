"""Latency instrumentation. Logs numbers and ids only, never conversation content.

Two sources, both emitted by the AgentSession:
- `metrics_collected`: per-component metrics (STT, LLM ttft/duration, TTS ttfb/duration/
  audio_duration, end-of-utterance delays).
- `conversation_item_added`: the per-turn breakdown LiveKit attaches to each message
  (end_of_turn_delay, transcription_delay, on_user_turn_completed_delay, llm_node_ttft,
  tts_node_ttfb, playback_latency) plus whether agent speech was interrupted.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from typing import Any

from livekit.agents import AgentSession
from livekit.agents.llm import ChatMessage

logger = logging.getLogger("sunrise.agent.metrics")

_SKIPPED_METRICS = {"VADMetrics"}  # emitted every few hundred ms; too noisy to be useful


def _numbers(source: object) -> dict[str, float | int | bool]:
    """Numeric fields only (durations, counts, flags); absolute timestamps are dropped."""
    items = source.items() if isinstance(source, dict) else vars(source).items()
    return {
        key: round(value, 4) if isinstance(value, float) else value
        for key, value in items
        if isinstance(value, (int, float, bool)) and not key.endswith("_at") and key != "timestamp"
    }


def attach_session_metrics(session: AgentSession[Any], call_id: str) -> None:
    @session.on("metrics_collected")
    def on_metrics(event: Any) -> None:
        metric = event.metrics
        kind = type(metric).__name__
        if kind in _SKIPPED_METRICS:
            return
        values = _numbers(metric)
        duration, audio = values.get("duration"), values.get("audio_duration")
        if isinstance(duration, float) and isinstance(audio, float) and audio > 0:
            values["real_time_factor"] = round(duration / audio, 3)
        logger.info(
            "event=voice_metrics call_id=%s type=%s values=%s",
            call_id,
            kind,
            json.dumps(values, sort_keys=True),
        )

    @session.on("conversation_item_added")
    def on_item(event: Any) -> None:
        item = event.item
        if not isinstance(item, ChatMessage):
            return
        logger.info(
            "event=turn_latency call_id=%s role=%s chars=%d interrupted=%s values=%s",
            call_id,
            item.role,
            len(item.text_content or ""),
            item.interrupted,
            json.dumps(_numbers(dict(item.metrics)), sort_keys=True),
        )


async def timed_service_call[T](
    call_id: str, function: Callable[..., T], /, *args: Any, **kwargs: Any
) -> T:
    """Run synchronous persistence/service work off the event loop; log duration only."""
    started = time.perf_counter()
    outcome = "success"
    try:
        return await asyncio.to_thread(function, *args, **kwargs)
    except Exception as error:
        outcome = type(error).__name__
        raise
    finally:
        logger.info(
            "event=clinic_tool_latency call_id=%s operation=%s duration_ms=%.2f outcome=%s",
            call_id,
            getattr(function, "__name__", "service_call"),
            (time.perf_counter() - started) * 1000,
            outcome,
        )
