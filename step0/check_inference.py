"""Check LiveKit Inference constructor compatibility for candidate model IDs.

Construction is local and does not prove provider availability, tool calling,
latency, or remaining credit. Those require a real voice call and dashboard.
"""

from __future__ import annotations

import inspect
import os
import sys

CANDIDATES = (
    "openai/gpt-5.4-mini",
    "google/gemma-4-31b-it",
    "google/gemini-3.5-flash-lite",
)


def main() -> int:
    try:
        from livekit.plugins import inference
    except ImportError as exc:
        print(f"LiveKit Inference import failed: {exc}", file=sys.stderr)
        return 2

    print("inference.LLM signature:", inspect.signature(inference.LLM))
    selected = os.getenv("LLM_MODEL", CANDIDATES[0])
    constructed = 0
    for model in CANDIDATES:
        try:
            instance = inference.LLM(model=model)
        except Exception as exc:  # report only class, never exception text/config
            print(f"CONSTRUCTOR FAIL {model}: {type(exc).__name__}")
            continue
        constructed += 1
        print(f"CONSTRUCTOR PASS {model}: {type(instance).__name__}")
    print(f"Configured LLM_MODEL: {selected}")
    print("A constructor pass is not proof that the model is enabled or has credit.")
    return 0 if constructed else 1


if __name__ == "__main__":
    raise SystemExit(main())
