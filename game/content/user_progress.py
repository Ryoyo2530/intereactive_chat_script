"""User-scoped discovered endings for long-form works."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from game.db.supabase_client import is_supabase_configured

logger = logging.getLogger(__name__)

_memory: dict[tuple[str, str], list[str]] = {}  # (user_id, work_id) -> ending ids


def _use_db() -> bool:
    return is_supabase_configured()


def get_discovered(user_id: str, work_id: str) -> list[str]:
    if _use_db():
        try:
            from game.db.supabase_client import get_supabase
            from game.db.supabase_retry import supabase_execute
            client = get_supabase()
            response = supabase_execute(
                client.table("user_work_progress")
                .select("discovered_endings")
                .eq("user_id", user_id)
                .eq("work_id", work_id)
                .limit(1),
                action=f"get user_work_progress {user_id[:8]}/{work_id}",
            )
            rows = response.data or []
            return list(rows[0].get("discovered_endings") or []) if rows else []
        except Exception as exc:
            logger.warning("[user_progress] get failed: %s", exc)
            return []
    return list(_memory.get((user_id, work_id), []))


def record_ending(user_id: str, work_id: str, ending_chapter_id: str) -> bool:
    """Upsert discovered ending. Returns True when this is the user's first time."""
    if not user_id or not work_id or not ending_chapter_id:
        return False
    current = get_discovered(user_id, work_id)
    is_new = ending_chapter_id not in current
    if is_new:
        current = current + [ending_chapter_id]
    if _use_db():
        try:
            from game.db.supabase_client import get_supabase
            from game.db.supabase_retry import supabase_execute
            client = get_supabase()
            supabase_execute(
                client.table("user_work_progress").upsert(
                    {"user_id": user_id, "work_id": work_id, "discovered_endings": current},
                    on_conflict="user_id,work_id",
                ),
                action=f"upsert user_work_progress {user_id[:8]}/{work_id}",
            )
            logger.info(
                "[user_progress] recorded ending user=%s work=%s chapter=%s new=%s",
                user_id[:8], work_id, ending_chapter_id, is_new,
            )
        except Exception as exc:
            logger.warning("[user_progress] upsert failed: %s", exc)
    else:
        _memory[(user_id, work_id)] = current
    return is_new


def list_long_form_progress(user_id: str) -> list[dict[str, Any]]:
    """Return all user_work_progress rows for a user (for history view)."""
    if _use_db():
        try:
            from game.db.supabase_client import get_supabase
            from game.db.supabase_retry import supabase_execute
            client = get_supabase()
            response = supabase_execute(
                client.table("user_work_progress")
                .select("work_id, discovered_endings, updated_at")
                .eq("user_id", user_id)
                .order("updated_at", desc=True),
                action=f"list user_work_progress {user_id[:8]}",
            )
            return list(response.data or [])
        except Exception as exc:
            logger.warning("[user_progress] list failed: %s", exc)
            return []
    return [
        {"work_id": wid, "discovered_endings": deepcopy(ends)}
        for (uid, wid), ends in _memory.items()
        if uid == user_id
    ]


def clear_memory() -> None:
    _memory.clear()
