"""Minimal real-time browser voice loop for Step 0 only."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from dotenv import load_dotenv
from livekit.agents import AgentSession, JobContext, WorkerOptions, cli, function_tool
from livekit.plugins import deepgram, inference, silero

from step0.livekit_guard import GuardedAgent

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
logger = logging.getLogger("sunrise.step0.voice")


class SmokeAgent(GuardedAgent):
    """A non-clinical test agent with one deterministic tool-call probe."""

    def __init__(self) -> None:
        super().__init__(
            instructions="Greet the caller. Explain this is a technical voice test, not a clinic."
        )

    @function_tool
    async def get_test_token(self) -> str:
        """Call this tool when the caller asks for the test token."""
        return "SPIKE_TOOL_OK"


async def entrypoint(ctx: JobContext) -> None:
    deepgram_key = os.getenv("DEEPGRAM_API_KEY")
    livekit_key = os.getenv("LIVEKIT_API_KEY")
    livekit_secret = os.getenv("LIVEKIT_API_SECRET")
    model = os.getenv("LLM_MODEL", "openai/gpt-5.4-mini")
    stt_model = os.getenv("DEEPGRAM_STT_MODEL", "nova-3")
    tts_model = os.getenv("DEEPGRAM_TTS_MODEL", "aura-2-andromeda-en")
    if not all((deepgram_key, livekit_key, livekit_secret)):
        raise RuntimeError("Missing required LiveKit or Deepgram credentials; check .env")

    session = AgentSession(
        stt=deepgram.STT(
            model=stt_model,
            api_key=deepgram_key,
            mip_opt_out=True,
            keyterm=["Lisinopril", "Metformin", "Atorvastatin", "Levothyroxine"],
        ),
        llm=inference.LLM(model=model),
        tts=deepgram.TTS(model=tts_model, api_key=deepgram_key, mip_opt_out=True),
        vad=silero.VAD.load(),
        turn_handling={"preemptive_generation": False},
    )

    @session.on("metrics_collected")
    def on_metrics(event: Any) -> None:
        metrics = getattr(event, "metrics", event)
        safe: dict[str, int | float | str] = {"event": "provider_metric"}
        for field in (
            "type",
            "request_id",
            "duration",
            "ttft",
            "ttfb",
            "audio_duration",
            "total_latency",
            "tokens",
            "prompt_tokens",
            "completion_tokens",
            "end_of_turn_delay",
        ):
            value = getattr(metrics, field, None)
            if isinstance(value, (int, float, str)) and len(str(value)) < 100:
                safe[field] = value
        logger.info("%s", safe)

    await ctx.connect()
    await session.start(room=ctx.room, agent=SmokeAgent(), record=False)
    logger.info(
        "voice_session_started model=%s stt=%s tts=%s at=%s",
        model,
        stt_model,
        tts_model,
        datetime.now(UTC).isoformat(),
    )
    await session.generate_reply(
        instructions=(
            "Briefly greet the caller. Explain this is a technical voice test, "
            "not a clinic service."
        )
    )


def main() -> None:
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))


if __name__ == "__main__":
    main()
