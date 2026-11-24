from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_path: Path = Path("data/clinic.sqlite3")
    hash_pepper: SecretStr | None = None
    allow_time_simulation: bool = False

    def require_hash_pepper(self) -> str:
        if self.hash_pepper is None or not self.hash_pepper.get_secret_value():
            raise RuntimeError("HASH_PEPPER is required for seeding and verification")
        return self.hash_pepper.get_secret_value()
