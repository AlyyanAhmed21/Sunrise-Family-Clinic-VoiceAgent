"""Optional OpenTelemetry tracing to Langfuse, with conversation content stripped in-process.

LiveKit Agents already emits spans for every turn (end of turn, STT, LLM, tool calls, TTS) and
marks every attribute that can carry conversation content (`lk.pii.*` and the GenAI content
attributes). With `allow_pii=False`, LiveKit removes those attributes inside this process,
before any exporter runs. Langfuse therefore receives timings, ids, models, tool names,
token counts and errors, but no transcript, prompt, tool argument or tool result.

Off unless LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set. Langfuse is a third-party
processor: production use with PHI would still need a signed BAA or a self-hosted instance.
"""

from __future__ import annotations

import base64
import logging

from livekit.agents.telemetry import set_tracer_provider
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("sunrise.agent.tracing")
SERVICE_NAME = "sunrise-clinic-voice-agent"


class TracingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    # EU: https://cloud.langfuse.com   US: https://us.cloud.langfuse.com
    # Langfuse's own docs use both names, so both are accepted.
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com",
        validation_alias=AliasChoices("LANGFUSE_HOST", "LANGFUSE_BASE_URL"),
    )

    @property
    def enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


def langfuse_exporter(settings: TracingSettings) -> OTLPSpanExporter:
    secret = settings.langfuse_secret_key
    if not settings.langfuse_public_key or secret is None:
        raise ValueError("Langfuse keys are not configured")
    token = f"{settings.langfuse_public_key}:{secret.get_secret_value()}"
    return OTLPSpanExporter(
        endpoint=f"{settings.langfuse_host.rstrip('/')}/api/public/otel/v1/traces",
        headers={"Authorization": f"Basic {base64.b64encode(token.encode()).decode()}"},
        timeout=10,
    )


def install_tracing(exporter: SpanExporter, *, call_id: str) -> TracerProvider:
    """Route LiveKit's spans to `exporter` with all content attributes removed."""
    provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
    provider.add_span_processor(BatchSpanProcessor(exporter))  # exports off the audio loop
    set_tracer_provider(
        provider,
        metadata={"langfuse.session.id": call_id, "call_id": call_id},
        allow_pii=False,
    )
    return provider


def configure_tracing(call_id: str) -> TracerProvider | None:
    settings = TracingSettings()
    if not settings.enabled:
        return None
    provider = install_tracing(langfuse_exporter(settings), call_id=call_id)
    logger.info("event=tracing_enabled call_id=%s backend=langfuse content=stripped", call_id)
    return provider
