"""Preview rendered LLM prompts for dev editor."""

from __future__ import annotations

import copy
from typing import Any

from game.core import director, roleplay


def build_preview_session(script: dict[str, Any], player_message: str) -> dict[str, Any]:
    stats = {
        name: cfg["initial"]
        for name, cfg in script.get("stats", {}).items()
    }
    history = []
    opening = script.get("opening_line", "")
    if opening:
        history.append({
            "role": "assistant",
            "content": opening,
            "character": script.get("ai_character", {}).get("name", "AI"),
        })
    return {
        "script": copy.deepcopy(script),
        "stats": stats,
        "history": history,
        "turn": 1,
        "hit_key_point_ids": [],
        "hit_pitfall_ids": [],
    }


def preview_prompts(
    script: dict[str, Any],
    prompt_overrides: dict[str, str] | None = None,
    player_message: str = "（示例玩家发言，用于预览 Prompt 渲染效果）",
) -> dict[str, Any]:
    session = build_preview_session(script, player_message)
    session["prompt_overrides"] = prompt_overrides

    director_messages = director._build_messages(session, player_message)
    reaction = {"tone": "冷静", "intensity": "中", "focus": "回应玩家"}
    roleplay_messages = roleplay._build_messages(session, player_message, reaction)

    def _split(msgs: list[dict[str, str]]) -> dict[str, str]:
        out = {"system": "", "user": ""}
        for msg in msgs:
            if msg["role"] in out:
                out[msg["role"]] = msg["content"]
        return out

    return {
        "director": _split(director_messages),
        "roleplay": _split(roleplay_messages),
        "player_message": player_message,
    }
