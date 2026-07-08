import uuid
from typing import Any

_sessions: dict[str, dict[str, Any]] = {}


def create_session(script: dict[str, Any], llm_config: dict[str, str] | None = None) -> str:
    session_id = str(uuid.uuid4())
    stats = {
        name: cfg["initial"]
        for name, cfg in script["stats"].items()
    }
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
        "hit_key_point_ids": [],
        "hit_pitfall_ids": [],
    }
    return session_id


def get_session(session_id: str) -> dict[str, Any] | None:
    return _sessions.get(session_id)


def update_session(session_id: str, updates: dict[str, Any]) -> None:
    if session_id in _sessions:
        _sessions[session_id].update(updates)
