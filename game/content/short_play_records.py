"""Repository for completed short-form play records (logged-in users only)."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from game.db.supabase_client import is_supabase_configured

logger = logging.getLogger(__name__)

_memory: list[dict[str, Any]] = []


def _use_db() -> bool:
    return is_supabase_configured()


def record_play(user_id: str, work_id: str, outcome: str) -> None:
    if not user_id or not work_id:
        return
    safe_outcome = outcome if outcome in ("win", "lose", "timeout") else "lose"
    if _use_db():
        try:
            from game.db.supabase_client import get_supabase
            from game.db.supabase_retry import supabase_execute
            client = get_supabase()
            supabase_execute(
                client.table("short_play_records").insert(
                    {"user_id": user_id, "work_id": work_id, "outcome": safe_outcome}
                ),
                action="insert short_play_record",
            )
            logger.info(
                "[short_play_records] recorded user=%s work=%s outcome=%s",
                user_id[:8], work_id, safe_outcome,
            )
        except Exception as exc:
            logger.warning("[short_play_records] record failed: %s", exc)
        return
    _memory.append({"user_id": user_id, "work_id": work_id, "outcome": safe_outcome})


def list_for_user(user_id: str) -> list[dict[str, Any]]:
    if _use_db():
        try:
            from game.db.supabase_client import get_supabase
            from game.db.supabase_retry import supabase_execute
            client = get_supabase()
            response = supabase_execute(
                client.table("short_play_records")
                .select("work_id, outcome, completed_at")
                .eq("user_id", user_id)
                .order("completed_at", desc=True),
                action=f"list short_play_records user={user_id[:8]}",
            )
            return list(response.data or [])
        except Exception as exc:
            logger.warning("[short_play_records] list failed: %s", exc)
            return []
    return [deepcopy(r) for r in _memory if r.get("user_id") == user_id]


def clear_memory() -> None:
    _memory.clear()
