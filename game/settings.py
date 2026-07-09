"""Application settings via pydantic-settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = "doubao"
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    dev_mode_password: str = ""
    rate_limit_per_minute: int = 120
    log_level: str = "INFO"


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
