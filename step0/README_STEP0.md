# Step 0 — Technical spike and feasibility harness

This folder is a **temporary feasibility harness**, not the final application architecture. The production application will live under `src/clinic/` and `src/agent/`; we will not create `step1/`, `step2/`, etc. Build steps are delivery batches, while source folders represent runtime responsibilities.

## Included

- `check_sdk.py`: inspect the installed LiveKit Agents version and relevant method signatures.
- `check_deepgram.py`: prove STT and TTS constructors accept and retain `mip_opt_out=True`; no network request is made.
- `check_inference.py`: construct candidate LiveKit Inference models locally. This does **not** prove remote availability, tool calling or credit.
- `guard.py`: SDK-independent copied-context egress redaction and inbound in-place masking prototype.
- `livekit_guard.py`: LiveKit 1.8.x `GuardedAgent` and `NoModelAgent` adapters.
- `smoke_agent.py`: minimal real-time browser voice loop with Deepgram STT/TTS, LiveKit Inference, Silero VAD and one deterministic tool-call probe. It explicitly sets `record=False`, `mip_opt_out=True` and disables preemptive generation at session and agent level.
- `metrics.py`: content-free latency sample aggregation.
- `region_probe.py`: TLS setup measurements to configured LiveKit and Deepgram endpoints; not end-to-end service latency.
- `tests/`: deterministic helper/metrics tests. These do not substitute for a real LiveKit session privacy test.

## Environment

Use Python 3.12 and `uv` from the repository root. Copy `.env.example` to `.env`, then add your own credentials. Never commit `.env`.

```powershell
uv sync --extra dev
uv run python step0/check_sdk.py
uv run python step0/check_deepgram.py
uv run python step0/check_inference.py
uv run python step0/region_probe.py
uv run pytest -q step0/tests
```

## Run the real voice smoke test

```powershell
uv run python -m step0.smoke_agent dev
```

Open the LiveKit Agent Console and connect to the worker. Speak a few normal test phrases, then ask: **“Please run the test tool and tell me the test token.”** Expected response includes `SPIKE_TOOL_OK`. Do not provide real patient data or any actual personal information; this is a synthetic technical test only.

## Privacy checks that still require live/manual evidence

1. Confirm the `AgentSession.start` call in this harness uses `record=False` (already explicit in code).
2. In LiveKit Cloud project settings, turn **Agent observability OFF**. This is a separate project-level control; the code cannot enforce it. Capture a screenshot or note the exact setting in your local test notes.
3. Confirm both Deepgram constructors run with `mip_opt_out=True` using `check_deepgram.py`. This verifies plugin configuration only, not a BAA or every provider retention practice.
4. Use a controlled test session to confirm the actual SDK's `StopResponse` / `on_end_of_turn` history behavior. Do not use `session.run(user_input=...)` as evidence for `on_user_turn_completed`; it bypasses that hook. Do not send actual identifiers. The production verification agent must be `NoModelAgent`; raw verification turns must never invoke an LLM or emit an LLM metric.
5. Confirm each candidate model by making a real call and asking it to invoke the tool. Check LiveKit dashboard credit usage before and after. Constructor success alone is not model availability.
6. Record region, connection setup, STT/EOU, LLM TTFT, TTS TTFB, tool duration and end-to-end turn timings in `docs/latency.md`. Use enough repeated samples to report p50/p95; state sample counts.

## Important limits

- `guard.py` is a Step 0 prototype, not the complete Step 1 PHI masker. It does not recognize every spoken DOB, phone, email, member ID or provider-specific message structure.
- The `NoModelAgent` adapter raises `StopResponse` if a model node is reached. The actual verification conversation must be deterministic and server-side; do not use an LLM to parse or match verification fields.
- `mip_opt_out=True` is a plugin flag, not a BAA and not proof that no vendor receives audio/transcript data.
- This spike is not a HIPAA certification or a production deployment.
