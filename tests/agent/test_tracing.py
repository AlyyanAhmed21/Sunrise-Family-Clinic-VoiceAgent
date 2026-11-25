"""Tracing must never export conversation content, whatever backend receives it."""

from __future__ import annotations

from livekit.agents.telemetry import trace_types, tracer
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agent.tracing import TracingSettings, configure_tracing, install_tracing

CONTENT = "My date of birth is March 14 1985 and my last four is 3344"


def test_exported_spans_keep_timings_but_never_content() -> None:
    exporter = InMemorySpanExporter()
    provider = install_tracing(exporter, call_id="call-123")

    with tracer.start_as_current_span("user_turn") as span:
        span.set_attribute(trace_types.ATTR_USER_INPUT, CONTENT)
        span.set_attribute(trace_types.ATTR_USER_TRANSCRIPT, CONTENT)
        span.set_attribute(trace_types.ATTR_CHAT_CTX, CONTENT)
        span.set_attribute(trace_types.ATTR_RESPONSE_TEXT, CONTENT)
        span.set_attribute(trace_types.ATTR_FUNCTION_TOOL_OUTPUT, CONTENT)
        span.set_attribute(trace_types.ATTR_GEN_AI_INPUT_MESSAGES, CONTENT)
        span.set_attribute(trace_types.ATTR_GEN_AI_TOOL_CALL_ARGUMENTS, CONTENT)
        span.set_attribute(trace_types.ATTR_TRANSCRIPTION_DELAY, 0.42)
        span.set_attribute(trace_types.ATTR_GEN_AI_USAGE_INPUT_TOKENS, 812)
    provider.force_flush()

    exported = exporter.get_finished_spans()
    assert exported
    attributes = {key: value for span in exported for key, value in (span.attributes or {}).items()}
    assert not any("3344" in str(value) or "1985" in str(value) for value in attributes.values())
    assert not any(key.startswith("lk.pii") for key in attributes)
    assert attributes[trace_types.ATTR_TRANSCRIPTION_DELAY] == 0.42
    assert attributes[trace_types.ATTR_GEN_AI_USAGE_INPUT_TOKENS] == 812
    assert attributes["langfuse.session.id"] == "call-123"


def test_langfuse_host_accepts_both_documented_variable_names(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(TracingSettings, "model_config", {"env_file": None, "extra": "ignore"})
    us = "https://us.cloud.langfuse.com"
    for name in ("LANGFUSE_HOST", "LANGFUSE_BASE_URL"):
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
        monkeypatch.setenv(name, us)
        assert TracingSettings().langfuse_host == us


def test_tracing_is_off_without_langfuse_keys(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setattr(TracingSettings, "model_config", {"env_file": None, "extra": "ignore"})

    assert configure_tracing("call-1") is None
