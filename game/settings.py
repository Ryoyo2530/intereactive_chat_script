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
    llm_timeout_seconds: float = Field(default=40.0, validation_alias="LLM_TIMEOUT_SECONDS")
    dev_mode_password: str = Field(default="", validation_alias="DEV_MODE_PASSWORD")
    invite_code: str = Field(default="", validation_alias="INVITE_CODE")
    rate_limit_per_minute: int = Field(default=120, validation_alias="RATE_LIMIT_PER_MINUTE")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    session_ttl_minutes: int = Field(default=30, validation_alias="SESSION_TTL_MINUTES")
    session_max_concurrent: int = Field(default=200, validation_alias="SESSION_MAX_CONCURRENT")
    session_hard_max_turns: int = Field(default=50, validation_alias="SESSION_HARD_MAX_TURNS")
    # Content persistence (v2.0). Leave URL/KEY empty to keep local scripts/*.json.
    supabase_url: str = Field(default="", validation_alias="SUPABASE_URL")
    supabase_key: str = Field(default="", validation_alias="SUPABASE_KEY")
    # file | supabase | "" (auto: supabase when credentials present, else file)
    content_backend: str = Field(default="", validation_alias="CONTENT_BACKEND")
    # Supabase anon key — exposed to frontend for Auth JS SDK
    supabase_anon_key: str = Field(default="", validation_alias="SUPABASE_ANON_KEY")


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
