"""Database client helpers (Supabase / Postgres)."""

from game.db.supabase_client import get_supabase, is_supabase_configured

__all__ = ["get_supabase", "is_supabase_configured"]
