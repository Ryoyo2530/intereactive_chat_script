"""Supabase client singleton for content asset persistence."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from game.settings import get_settings

logger = logging.getLogger(__name__)


class SupabaseConfigError(RuntimeError):
    """Raised when Supabase is required but URL/key are missing or invalid."""


def is_supabase_configured() -> bool:
    settings = get_settings()
    return bool(settings.supabase_url.strip() and settings.supabase_key.strip())


@lru_cache
def get_supabase() -> Any:
    """Return a cached Supabase client.

    Raises SupabaseConfigError with a clear message when credentials are missing.
    """
    settings = get_settings()
    url = settings.supabase_url.strip()
    key = settings.supabase_key.strip()
    if not url or not key:
        raise SupabaseConfigError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY "
            "(service role key, backend only) in the environment."
        )
    try:
        from supabase import create_client
    except ImportError as exc:
        raise SupabaseConfigError(
            "The 'supabase' package is not installed. Run: pip install supabase"
        ) from exc

    logger.info("[supabase] connecting to %s", url)
    return create_client(url, key)
