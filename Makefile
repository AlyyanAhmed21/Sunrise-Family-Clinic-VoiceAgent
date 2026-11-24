.PHONY: setup lock seed test lint format typecheck run-agent region-probe step0-checks

setup:
	uv sync --extra dev

lock:
	uv lock

seed:
	uv run python -c "import sys; sys.path.insert(0, 'src'); from clinic.config import Settings; from clinic.persistence.db import Database; from clinic.persistence.seed import seed_database; s=Settings(); seed_database(Database(s.database_path), s.require_hash_pepper())"

test:
	uv run pytest -q

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy step0

run-agent:
	uv run python -m step0.smoke_agent dev

region-probe:
	uv run python step0/region_probe.py

step0-checks:
	uv run python step0/check_sdk.py
	uv run python step0/check_deepgram.py
	uv run python step0/check_inference.py
