"""Verify Deepgram plugin privacy flags and model constructor settings offline."""

from __future__ import annotations

import inspect
import sys


def main() -> int:
    try:
        from livekit.plugins import deepgram
    except ImportError as exc:
        print(f"Deepgram plugin import failed: {exc}", file=sys.stderr)
        return 2

    failures: list[str] = []
    for label, constructor, kwargs in (
        ("STT", deepgram.STT, {"api_key": "step0-placeholder", "mip_opt_out": True}),
        ("TTS", deepgram.TTS, {"api_key": "step0-placeholder", "mip_opt_out": True}),
    ):
        signature = inspect.signature(constructor)
        print(f"{label} signature: {signature}")
        if "mip_opt_out" not in signature.parameters:
            failures.append(f"{label} constructor has no mip_opt_out parameter")
            continue
        instance = constructor(**kwargs)
        options = getattr(instance, "_opts", None)
        configured = getattr(options, "mip_opt_out", None)
        if configured is not True:
            failures.append(f"{label} did not retain mip_opt_out=True")
        else:
            print(f"PASS: {label} configured with mip_opt_out=True (no network request made).")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
