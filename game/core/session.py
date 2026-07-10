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
) -> str:
    cleanup_expired()
    if len(_sessions) >= _max_concurrent():
        logger.warning("session_limit active=%s max=%s", len(_sessions), _max_concurrent())
        raise SessionLimitError("当前体验人数较多，请稍后再试")

    session_id = str(uuid.uuid4())
    stats = {
        name: cfg["initial"]
        for name, cfg in script["stats"].items()
    }
    now = _now()
    _sessions[session_id] = {
        "script_id": script["id"],
        "script": script,
        "history": [],
        "stats": stats,
        "turn": 0,
        "game_over": False,
        "ending_text": None,
        "result": None,
        "llm_config": llm_config,
        "llm_config_director": llm_config_director or llm_config,
        "llm_config_roleplay": llm_config_roleplay or llm_config,
        "prompt_overrides": prompt_overrides,
        "hit_key_point_ids": [],
        "hit_pitfall_ids": [],
        "created_at": now,
        "last_active_at": now,
    }
    logger.info("session_create id=%s active=%s", session_id[:8], len(_sessions))
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
