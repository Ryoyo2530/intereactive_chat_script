"""Application settings via pydantic-settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = Field(default="doubao", validation_alias="LLM_PROVIDER")
    llm_api_base: str = Field(default="", validation_alias="LLM_API_BASE")
    llm_api_key: str = Field(default="", validation_alias="LLM_API_KEY")
    llm_model: str = Field(default="", validation_alias="LLM_MODEL")
    dev_mode_password: str = Field(default="", validation_alias="DEV_MODE_PASSWORD")
    rate_limit_per_minute: int = Field(default=120, validation_alias="RATE_LIMIT_PER_MINUTE")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
