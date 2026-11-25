import logging
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_path: Path = Path("data/clinic.sqlite3")
    hash_pepper: SecretStr | None = None
    log_level: str = "INFO"
    allow_time_simulation: bool = False
    # Local demos only, e.g. 2026-11-24T19:00:00-05:00. Ignored unless simulation is allowed.
    demo_now: str | None = None

    @property
    def log_level_number(self) -> int:
        return logging.getLevelNamesMapping().get(self.log_level.upper(), logging.INFO)

    def require_hash_pepper(self) -> str:
        if self.hash_pepper is None or not self.hash_pepper.get_secret_value():
            raise RuntimeError("HASH_PEPPER is required for seeding and verification")
        return self.hash_pepper.get_secret_value()
