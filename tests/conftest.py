from __future__ import annotations

from pathlib import Path

import pytest

from clinic.persistence.db import Database
from clinic.persistence.seed import seed_database

TEST_PEPPER = "step1-deterministic-test-pepper"


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "clinic.sqlite3")
    db.create_schema()
    seed_database(db, TEST_PEPPER)
    return db
