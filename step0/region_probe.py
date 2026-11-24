"""Measure TLS connection setup to configured provider endpoints.

This is a network-path sanity check, not a substitute for end-to-end voice
latency or a definitive cloud-region measurement.
"""

from __future__ import annotations

import asyncio
import os
import ssl
import statistics
import time
from urllib.parse import urlparse


async def _sample(host: str, port: int = 443) -> float:
    started = time.perf_counter()
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port, ssl=ssl.create_default_context(), server_hostname=host),
        timeout=8,
    )
    writer.close()
    await writer.wait_closed()
    return (time.perf_counter() - started) * 1000


async def _probe(label: str, host: str, count: int = 8) -> None:
    samples: list[float] = []
    for _ in range(count):
        try:
            samples.append(await _sample(host))
        except (OSError, TimeoutError, ssl.SSLError) as exc:
            print(f"{label}: connection failed ({type(exc).__name__})")
            return
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, round((len(ordered) - 1) * 0.95))]
    print(
        f"{label} host={host} samples={len(samples)} "
        f"median_tls_ms={statistics.median(samples):.1f} p95_tls_ms={p95:.1f}"
    )


async def main() -> None:
    livekit_url = os.getenv("LIVEKIT_URL", "")
    if livekit_url:
        host = urlparse(livekit_url).hostname
        if host:
            await _probe("livekit", host)
        else:
            print("LIVEKIT_URL is not a valid URL")
    else:
        print("LIVEKIT_URL is not configured; skipping LiveKit endpoint probe")
    await _probe("deepgram", "api.deepgram.com")
    print("NOTE: TLS latency is a network proxy, not real voice latency.")


if __name__ == "__main__":
    asyncio.run(main())
