"""Cross-run work progress (discovered endings) for long-form product UI."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from game.db.supabase_client import is_supabase_configured

logger = logging.getLogger(__name__)

_memory: dict[str, dict[str, Any]] = {}


def _use_db() -> bool:
    return is_supabase_configured()


def get_progress(work_id: str) -> dict[str, Any]:
    if _use_db():
        from game.db.supabase_client import get_supabase
        from game.db.supabase_retry import supabase_execute

        client = get_supabase()
        response = supabase_execute(
            client.table("work_progress")
            .select("work_id, discovered_endings, updated_at")
            .eq("work_id", work_id)
            .limit(1),
            action=f"get work_progress {work_id}",
        )
        rows = response.data or []
        if rows:
            return rows[0]
        return {"work_id": work_id, "discovered_endings": []}

    row = _memory.get(work_id)
    return deepcopy(row) if row else {"work_id": work_id, "discovered_endings": []}


def record_ending(work_id: str, ending_chapter_id: str) -> dict[str, Any]:
    """Append-only: add a terminal chapter id to discovered endings."""
    if not work_id or not ending_chapter_id:
        return get_progress(work_id)

    if _use_db():
        from game.db.supabase_client import get_supabase
        from game.db.supabase_retry import supabase_execute

        current = get_progress(work_id)
        endings = list(current.get("discovered_endings") or [])
        if ending_chapter_id not in endings:
            endings.append(ending_chapter_id)
        client = get_supabase()
        response = supabase_execute(
            client.table("work_progress").upsert(
                {"work_id": work_id, "discovered_endings": endings},
                on_conflict="work_id",
            ),
            action=f"upsert work_progress {work_id}",
        )
        rows = response.data or [{"work_id": work_id, "discovered_endings": endings}]
        logger.info(
            "[work_progress] recorded ending work=%s chapter=%s total=%s",
            work_id,
            ending_chapter_id,
            len(endings),
        )
        return rows[0]

    row = _memory.setdefault(work_id, {"work_id": work_id, "discovered_endings": []})
    endings = list(row.get("discovered_endings") or [])
    if ending_chapter_id not in endings:
        endings.append(ending_chapter_id)
        row["discovered_endings"] = endings
    return deepcopy(row)


def clear_memory() -> None:
    _memory.clear()
