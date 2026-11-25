"""LLM evaluation suite: real agents + real LLM in text mode. Costs LiveKit Inference credit,
so it is deselected by default (`-m "not llm"`). Run with `make evals` or
`uv run --env-file .env pytest -m llm tests/evals -s`."""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    load_dotenv()
    if os.environ.get("LIVEKIT_API_KEY"):
        return
    skip = pytest.mark.skip(reason="LIVEKIT_API_KEY not set; evals need the real LLM")
    for item in items:
        if "llm" in item.keywords:
            item.add_marker(skip)
