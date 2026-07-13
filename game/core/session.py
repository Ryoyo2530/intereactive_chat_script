"""In-memory game session store with TTL eviction and concurrency caps (v1.4)."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from game.settings import get_settings

logger = logging.getLogger(__name__)

_sessions: dict[str, dict[str, Any]] = {}


class SessionLimitError(Exception):
    """Raised when concurrent session cap is reached."""


def _now() -> float:
    return time.time()


def _ttl_seconds() -> float:
    return max(get_settings().session_ttl_minutes, 1) * 60


def _max_concurrent() -> int:
    return max(get_settings().session_max_concurrent, 1)


def hard_max_turns() -> int:
    return max(get_settings().session_hard_max_turns, 1)


def effective_max_turns(script_max: int | None) -> int:
    configured = script_max if isinstance(script_max, int) and script_max > 0 else 15
    return min(configured, hard_max_turns())


def active_count() -> int:
    return len(_sessions)


def cleanup_expired() -> int:
    """Remove sessions idle longer than TTL. Returns number removed."""
    ttl = _ttl_seconds()
    now = _now()
    expired = [
        sid
        for sid, data in _sessions.items()
        if now - float(data.get("last_active_at", 0)) > ttl
    ]
    for sid in expired:
        del _sessions[sid]
    if expired:
        logger.info("session_cleanup removed=%s remaining=%s", len(expired), len(_sessions))
    return len(expired)


def create_session(
    script: dict[str, Any],
    llm_config: dict[str, str] | None = None,
    llm_config_director: dict[str, str] | None = None,
    llm_config_roleplay: dict[str, str] | None = None,
    prompt_overrides: dict[str, str] | None = None,
    *,
    flags: dict[str, Any] | None = None,
    chapter_summaries: list[str] | None = None,
    save_id: str | None = None,
    history: list[dict[str, Any]] | None = None,
    stats: dict[str, int] | None = None,
    turn: int | None = None,
    hit_key_point_ids: list[str] | None = None,
    hit_pitfall_ids: list[str] | None = None,
    game_over: bool = False,
    ending_text: str | None = None,
    result: str | None = None,
) -> str:
    cleanup_expired()
    if len(_sessions) >= _max_concurrent():
        logger.warning("session_limit active=%s max=%s", len(_sessions), _max_concurrent())
        raise SessionLimitError("当前体验人数较多，请稍后再试")

    session_id = str(uuid.uuid4())
    initial_stats = stats or {
        name: cfg["initial"]
        for name, cfg in script["stats"].items()
    }
    now = _now()
    work_type = script.get("work_type") or "short_form"
    _sessions[session_id] = {
        "script_id": script["id"],
        "script": script,
        "history": list(history or []),
        "stats": dict(initial_stats),
        "turn": int(turn or 0),
        "game_over": bool(game_over),
        "ending_text": ending_text,
        "result": result,
        "llm_config": llm_config,
        "llm_config_director": llm_config_director or llm_config,
        "llm_config_roleplay": llm_config_roleplay or llm_config,
        "prompt_overrides": prompt_overrides,
        "hit_key_point_ids": list(hit_key_point_ids or []),
        "hit_pitfall_ids": list(hit_pitfall_ids or []),
        # Long-form fields (unused for short_form)
        "work_type": work_type,
        "current_chapter_id": script.get("chapter_id"),
        "flags": dict(flags or {}),
        "chapter_summaries": list(chapter_summaries or []),
        "save_id": save_id,
        "created_at": now,
        "last_active_at": now,
    }
    logger.info(
        "session_create id=%s work=%s type=%s active=%s",
        session_id[:8],
        script["id"],
        work_type,
        len(_sessions),
    )
    return session_id


def get_session(session_id: str) -> dict[str, Any] | None:
    session = _sessions.get(session_id)
    if session is None:
        return None
    ttl = _ttl_seconds()
    if _now() - float(session.get("last_active_at", 0)) > ttl:
        del _sessions[session_id]
        logger.info("session_expired id=%s", session_id[:8])
        return None
    session["last_active_at"] = _now()
    return session


def update_session(session_id: str, updates: dict[str, Any]) -> None:
    if session_id in _sessions:
        _sessions[session_id].update(updates)
        _sessions[session_id]["last_active_at"] = _now()
