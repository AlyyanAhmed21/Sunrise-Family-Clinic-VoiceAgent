import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
    function_tool,
    inference,
)
from livekit.plugins import deepgram, silero

load_dotenv(".env")
logging.basicConfig(level=logging.INFO)
logging.getLogger("livekit").setLevel(logging.INFO)
logging.getLogger("livekit.agents").setLevel(logging.INFO)
logging.getLogger("livekit.plugins.deepgram").setLevel(logging.INFO)
logging.getLogger("lk.pii").setLevel(logging.WARNING)
logger = logging.getLogger("step0.voice-smoke")
METRICS_FILE = Path("step0/metrics.jsonl")


def write_metric(call_id: str, metric: object) -> None:
    """Persist numeric pipeline metrics only; never persist conversation text."""
    allowed = (
        "end_of_utterance_delay",
        "end_of_turn_delay",
        "transcription_delay",
        "on_user_turn_completed_delay",
        "ttft",
        "ttfb",
        "duration",
        "tokens_per_second",
        "e2e_latency",
    )
    values = {}
    for name in allowed:
        value = getattr(metric, name, None)
        if isinstance(value, (int, float)):
            values[name] = value
    if not values:
        return
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "call_id": call_id,
        "metric_type": type(metric).__name__,
        "values": values,
    }
    METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with METRICS_FILE.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record) + "\n")


class SmokeTestAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You are a voice pipeline test assistant. "
                "Keep replies to one short sentence. "
                "If the caller asks you to run the demo tool, call it. "
                "Do not request or discuss personal information."
            )
        )

    @function_tool
    async def demo_tool(self) -> str:
        """Run the harmless demo tool when the caller asks to test tool execution."""
        logger.info("event=demo_tool_executed")
        return "The demo tool executed successfully."


async def entrypoint(ctx: JobContext) -> None:
    required = (
        "LIVEKIT_URL",
        "LIVEKIT_API_KEY",
        "LIVEKIT_API_SECRET",
        "DEEPGRAM_API_KEY",
    )
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError("Missing required environment configuration: " + ", ".join(missing))
    call_id = ctx.room.name or "step0-unknown"
    logger.info("event=worker_started call_id=%s", call_id)
    await ctx.connect()
    session = AgentSession(
        stt=deepgram.STT(
            model=os.getenv("DEEPGRAM_STT_MODEL", "nova-3"),
            api_key=os.environ["DEEPGRAM_API_KEY"],
            mip_opt_out=True,
        ),
        llm=inference.LLM(model=os.getenv("LLM_MODEL", "openai/gpt-5.4-mini")),
        tts=deepgram.TTS(
            model=os.getenv("DEEPGRAM_TTS_MODEL", "aura-2-andromeda-en"),
            api_key=os.environ["DEEPGRAM_API_KEY"],
            mip_opt_out=True,
        ),
        vad=silero.VAD.load(),
        turn_handling={
            "preemptive_generation": {"enabled": False},
        },
    )

    @session.on("metrics_collected")
    def on_metrics(event: object) -> None:
        metric = getattr(event, "metrics", None)
        if metric is not None:
            write_metric(call_id, metric)

    await session.start(
        room=ctx.room,
        agent=SmokeTestAgent(),
        record=False,
    )
    logger.info(
        "event=session_ready call_id=%s recording=false preemptive_generation=false",
        call_id,
    )
    await session.say(
        "Hello. This is the Sunrise Clinic voice pipeline test. Can you hear me clearly?"
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
