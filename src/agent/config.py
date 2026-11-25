from __future__ import annotations

from typing import Any

import jiter  # noqa: F401  # preload: first LLM turn otherwise imports it on the audio loop
from livekit.agents import AgentSession, TurnHandlingOptions, inference, llm
from livekit.agents.types import APIConnectOptions

# LiveKit plugins must register on the main thread at import time, not inside a job.
from livekit.plugins import deepgram
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from agent.state import CallState


class VoiceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    livekit_url: str | None = None
    livekit_api_key: SecretStr | None = None
    livekit_api_secret: SecretStr | None = None
    deepgram_api_key: SecretStr | None = None
    llm_model: str = "openai/gpt-5.4-mini"
    llm_fallback_models: str = "google/gemma-4-31b-it"
    llm_reasoning_effort: str = "low"
    provider_timeout_seconds: float = 10.0
    deepgram_stt_model: str = "nova-3"
    deepgram_tts_model: str = "aura-2-thalia-en"
    deepgram_keyterms: str = (
        "Sunrise Family Clinic,Dr. Patel,Dr. Lee,Lisinopril,Metformin,Atorvastatin,"
        "Levothyroxine,CVS Main St,Walgreens Oak Ave,Rite Aid 5th St"
    )

    def require_deepgram_key(self) -> str:
        missing = [
            name
            for name, value in (
                ("LIVEKIT_URL", self.livekit_url),
                ("LIVEKIT_API_KEY", self.livekit_api_key),
                ("LIVEKIT_API_SECRET", self.livekit_api_secret),
                ("DEEPGRAM_API_KEY", self.deepgram_api_key),
            )
            if value is None
        ]
        if missing or self.deepgram_api_key is None:
            raise RuntimeError(f"Missing required settings: {', '.join(missing)}")
        return self.deepgram_api_key.get_secret_value()


def build_llm(settings: VoiceSettings) -> llm.LLM:
    """Primary model with low reasoning effort (voice needs fast first tokens) and fallbacks."""
    models = [settings.llm_model] + [
        name.strip() for name in settings.llm_fallback_models.split(",") if name.strip()
    ]
    instances: list[llm.LLM] = []
    for name in models:
        options: dict[str, Any] = {}
        if name.startswith("openai/") and settings.llm_reasoning_effort:
            options["reasoning"] = settings.llm_reasoning_effort
        instances.append(inference.LLM(model=name, **options))
    if len(instances) == 1:
        return instances[0]
    return llm.FallbackAdapter(instances, attempt_timeout=settings.provider_timeout_seconds)


def build_agent_session(state: CallState, settings: VoiceSettings) -> AgentSession[CallState]:
    deepgram_key = settings.require_deepgram_key()
    stt = deepgram.STT(
        model=settings.deepgram_stt_model,
        api_key=deepgram_key,
        mip_opt_out=True,  # opt out of Deepgram's model-improvement program
        numerals=True,  # "three three four four" -> "3344"; parsers handle both forms
        smart_format=True,
        keyterm=[term.strip() for term in settings.deepgram_keyterms.split(",") if term.strip()],
    )
    tts = deepgram.TTS(model=settings.deepgram_tts_model, api_key=deepgram_key, mip_opt_out=True)
    turn_handling: TurnHandlingOptions = {
        # Preemptive generation would start the LLM on the raw transcript before
        # `ClinicAgent` has screened it and removed the DOB and SSN digits.
        "preemptive_generation": {"enabled": False},
        "turn_detection": inference.TurnDetector(
            version="v1",
            local_fallback=False,
            conn_options=APIConnectOptions(
                max_retry=1,
                retry_interval=1.0,
                timeout=settings.provider_timeout_seconds,
            ),
        ),
        "endpointing": {"mode": "fixed", "min_delay": 0.5, "max_delay": 2.5},
    }
    return AgentSession(
        stt=stt,
        llm=build_llm(settings),
        tts=tts,
        vad=inference.VAD(),
        userdata=state,
        turn_handling=turn_handling,
    )
