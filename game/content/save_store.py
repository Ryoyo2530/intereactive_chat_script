"""Save persistence with Supabase primary + in-memory fallback for local/dev."""

from __future__ import annotations

import logging
import uuid
from copy import deepcopy
from typing import Any

from game.db.supabase_client import is_supabase_configured

logger = logging.getLogger(__name__)

_memory_saves: dict[str, dict[str, Any]] = {}


def _use_db() -> bool:
    return is_supabase_configured()


def create_save(payload: dict[str, Any]) -> dict[str, Any]:
    if _use_db():
        from game.content import save_repository

        return save_repository.create_save(payload)

    save_id = str(payload.get("id") or uuid.uuid4())
    row = {
        "id": save_id,
        "work_id": payload["work_id"],
        "current_chapter_id": payload["current_chapter_id"],
        "current_turn": payload.get("current_turn", 0),
        "stats": deepcopy(payload.get("stats") or {}),
        "flags": deepcopy(payload.get("flags") or {}),
        "chapter_summaries": deepcopy(payload.get("chapter_summaries") or []),
        "hit_key_point_ids": list(payload.get("hit_key_point_ids") or []),
        "hit_pitfall_ids": list(payload.get("hit_pitfall_ids") or []),
        "conversation_history": deepcopy(payload.get("conversation_history") or []),
        "game_over": bool(payload.get("game_over", False)),
        "outcome": payload.get("outcome"),
    }
    # Single save slot per work: replace any prior in-memory save.
    for existing_id, existing in list(_memory_saves.items()):
        if existing.get("work_id") == row["work_id"]:
            del _memory_saves[existing_id]
    _memory_saves[save_id] = row
    logger.info("[save_store] memory save created %s work=%s", save_id[:8], row["work_id"])
    return deepcopy(row)


def get_save(save_id: str) -> dict[str, Any] | None:
    if _use_db():
        from game.content import save_repository

        return save_repository.get_save(save_id)
    row = _memory_saves.get(save_id)
    return deepcopy(row) if row else None


def update_save(save_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    if _use_db():
        from game.content import save_repository

        return save_repository.update_save(save_id, updates)

    row = _memory_saves.get(save_id)
    if not row:
        raise FileNotFoundError(f"Save not found: {save_id}")
    allowed = {
        "current_chapter_id",
        "current_turn",
        "stats",
        "flags",
        "chapter_summaries",
        "hit_key_point_ids",
        "hit_pitfall_ids",
        "conversation_history",
        "game_over",
        "outcome",
    }
    for key, value in updates.items():
        if key in allowed:
            row[key] = deepcopy(value) if isinstance(value, (dict, list)) else value
    return deepcopy(row)


def get_active_save_for_work(work_id: str) -> dict[str, Any] | None:
    """Return the newest non-completed save for a work (single-slot semantics)."""
    if _use_db():
        from game.content import save_repository

        saves = save_repository.list_saves_for_work(work_id)
        for row in saves:
            if not row.get("game_over"):
                return row
        return saves[0] if saves else None

    matches = [s for s in _memory_saves.values() if s.get("work_id") == work_id]
    if not matches:
        return None
    active = [s for s in matches if not s.get("game_over")]
    chosen = active[0] if active else matches[0]
    return deepcopy(chosen)


def clear_memory_saves() -> None:
    """Test helper."""
    _memory_saves.clear()
