import logging
from typing import Any

from game import llm_client, prompt_manager
from game.llm_config import LLMConfig

logger = logging.getLogger(__name__)

DEFAULT_REACTION = {
    "tone": "冷静",
    "intensity": "中",
    "focus": "听完玩家说法",
}

DIRECTOR_FALLBACK: dict[str, Any] = {
    "hit_key_points": [],
    "hit_pitfalls": [],
    "stat_changes": {},
    "reaction": dict(DEFAULT_REACTION),
    "game_over": False,
    "outcome": None,
    "ending_text": None,
}


def _normalize_reaction(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {
            "tone": str(raw.get("tone") or DEFAULT_REACTION["tone"]),
            "intensity": str(raw.get("intensity") or DEFAULT_REACTION["intensity"]),
            "focus": str(raw.get("focus") or DEFAULT_REACTION["focus"]),
        }
    if isinstance(raw, str) and raw.strip():
        return {
            "tone": DEFAULT_REACTION["tone"],
            "intensity": DEFAULT_REACTION["intensity"],
            "focus": raw.strip()[:15],
        }
    return dict(DEFAULT_REACTION)


def _build_messages(game_session: dict[str, Any], player_message: str) -> list[dict[str, str]]:
    script = game_session["script"]
    overrides = game_session.get("prompt_overrides")
    system = prompt_manager.render("director/system.txt", overrides=overrides)
    user = prompt_manager.render(
        "director/user.txt",
        overrides=overrides,
        background=script["background"],
        objective=script["objective"],
        ai_character_name=script["ai_character"]["name"],
        ai_character_persona=script["ai_character"]["persona"],
        emotion_vocabulary=prompt_manager.format_emotion_vocabulary(script),
        player_character_name=script["player_character"]["name"],
        current_stats=prompt_manager.format_stats(game_session["stats"]),
        conversation_history=prompt_manager.format_history(game_session["history"]),
        player_message=player_message,
        pending_key_points=prompt_manager.format_pending_key_points(
            script, game_session.get("hit_key_point_ids", [])
        ),
        pending_pitfalls=prompt_manager.format_pending_pitfalls(
            script, game_session.get("hit_pitfall_ids", [])
        ),
        win_condition=script["win_condition"],
        lose_condition=script["lose_condition"],
        current_turn=str(game_session["turn"]),
        max_turns=str(script.get("max_turns", 15)),
    )
    logger.info("[director] system prompt:\n%s", system)
    logger.info("[director] user prompt:\n%s", user)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _normalize_hit_ids(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    ids: list[str] = []
    for item in raw:
        if isinstance(item, bool):
            continue
        if isinstance(item, str) and item.strip():
            ids.append(item.strip())
        elif isinstance(item, int):
            ids.append(str(item))
        elif isinstance(item, float) and item.is_integer():
            ids.append(str(int(item)))
    return ids


def _normalize_result(result: dict[str, Any]) -> dict[str, Any]:
    result["hit_key_points"] = _normalize_hit_ids(result.get("hit_key_points"))
    result["hit_pitfalls"] = _normalize_hit_ids(result.get("hit_pitfalls"))
    if not isinstance(result.get("stat_changes"), dict):
        result["stat_changes"] = {}

    reaction = result.get("reaction")
    if reaction is None and result.get("reaction_instruction"):
        reaction = result["reaction_instruction"]
    result["reaction"] = _normalize_reaction(reaction)

    result.setdefault("game_over", False)
    result.setdefault("outcome", None)
    result.setdefault("ending_text", None)
    return result


def judge(game_session: dict[str, Any], player_message: str, config: LLMConfig) -> dict[str, Any]:
    result, _meta = judge_debug(game_session, player_message, config)
    return result


def judge_debug(
    game_session: dict[str, Any],
    player_message: str,
    config: LLMConfig,
) -> tuple[dict[str, Any], dict[str, Any]]:
    messages = _build_messages(game_session, player_message)
    try:
        result, meta = llm_client.chat_json_stream_debug(messages, config, DIRECTOR_FALLBACK)
    except Exception as exc:
        logger.warning("[director] LLM call failed: %s", exc)
        return dict(DIRECTOR_FALLBACK), {
            "prompts": llm_client._prompts_from_messages(messages),
            "ttft_ms": 0,
            "total_ms": 0,
            "usage": {"input_tokens": None, "output_tokens": None},
            "raw_output": "",
        }

    return _normalize_result(result), meta
