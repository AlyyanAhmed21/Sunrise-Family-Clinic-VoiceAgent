# Latency measurements

No measurements are claimed until they are collected from the user's LiveKit/Deepgram environment.

## Method

- Run the same short scripted phrases for each candidate LLM and repeat enough times to report sample count, p50 and p95.
- Capture endpoint-of-user-turn (EOU), LLM time-to-first-token (TTFT), TTS time-to-first-byte (TTFB), tool duration and end-to-end response latency where the SDK/provider exposes them.
- Keep transcript text, identifiers, audio and prompt contents out of this report.
- Record the LiveKit project region/configuration and the date/time of each run.
- `step0/region_probe.py` measures TLS connection setup only; do not label it model or end-to-end latency.

## Results

| Test | Model / provider setting | Samples | p50 | p95 | Notes |
|---|---|---:|---:|---:|---|
| LiveKit TLS setup | configured project endpoint | pending | pending | pending | Network-path proxy only |
| Deepgram TLS setup | api.deepgram.com | pending | pending | pending | Network-path proxy only |
| Plain voice turn | `LLM_MODEL` | pending | pending | pending | Pending live call |
| Tool-call voice turn | `LLM_MODEL` | pending | pending | pending | Must invoke `SPIKE_TOOL_OK` |
