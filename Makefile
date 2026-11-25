# Convenience targets for Linux/macOS (GNU Make). On Windows, run the same `uv run …`
# commands directly; the README lists them.
.PHONY: setup lock seed test lint format typecheck run-agent run-api show-requests show-audit reset-demo evals report

setup:
	uv sync --extra dev

lock:
	uv lock

seed:
	uv run clinic seed

test:
	uv run pytest -q

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy src/clinic src/agent

# Real LLM in text mode; uses LiveKit Inference credit, so not part of `make test` or CI.
evals:
	uv run --env-file .env pytest -m llm tests/evals -s

report:
	uv run clinic-report

run-agent:
	uv run --env-file .env python -m agent.main dev

run-api:
	uv run --env-file .env uvicorn clinic.api.main:app --host 127.0.0.1 --port 8000

show-requests:
	uv run clinic show-requests

show-audit:
	uv run clinic show-audit

reset-demo:
	uv run clinic reset-demo
