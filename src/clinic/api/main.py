from __future__ import annotations

import sqlite3

from fastapi import FastAPI, Response, status

from clinic.config import Settings
from clinic.persistence.db import Database

app = FastAPI(title="Sunrise Family Clinic", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def readiness(response: Response) -> dict[str, str]:
    try:
        settings = Settings()
        settings.require_hash_pepper()
        database = Database(settings.database_path)
        with database.connect() as connection:
            connection.execute("SELECT 1").fetchone()
    except (RuntimeError, sqlite3.Error, OSError) as error:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "reason": type(error).__name__}
    return {"status": "ready"}
