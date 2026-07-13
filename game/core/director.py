import logging
from typing import Any

from game.core import flags as flag_helpers
from game.llm import client as llm_client
from game.llm.config import LLMConfig
from game.prompts import manager as prompt_manager

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
    "chapter_wrap_up": None,
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


def _flag_candidates_instruction(script: dict[str, Any]) -> str:
    items = script.get("flags_write") or []
    if not items:
        return ""
    lines = []
    for item in items:
        if isinstance(item, str):
            lines.append(f"- {item}")
        elif isinstance(item, dict):
            flag_id = item.get("id") or item.get("flag") or ""
            trigger = item.get("trigger") or flag_id
            label = item.get("label") or flag_id
            lines.append(f"- id/trigger `{trigger}`：{label}")
    if not lines:
        return ""
    return (
        "\n【本章可触发的 flag 候选】\n"
        + "\n".join(lines)
        + "\n若本章确已满足某条触发条件，将对应 id 写入 chapter_wrap_up.triggered_flags。"
    )


def _build_messages(game_session: dict[str, Any], player_message: str) -> list[dict[str, str]]:
    script = game_session["script"]
    overrides = game_session.get("prompt_overrides")
    work_type = game_session.get("work_type") or script.get("work_type") or "short_form"
    is_long = work_type == "long_form"

    known_flags = (
        flag_helpers.format_known_flags_summary(
            script.get("flags_read") or [],
            game_session.get("flags") or {},
        )
        if is_long
        else ""
    )
    summaries = (
        flag_helpers.format_chapter_summaries_recent(game_session.get("chapter_summaries") or [])
        if is_long
        else ""
    )
    wrap_instruction = ""
    if is_long:
        wrap_instruction = (
            "若本轮判定 game_over=true，必须额外输出 chapter_wrap_up："
            '{"summary":"30-50字摘要","triggered_flags":[...]}。'
            + _flag_candidates_instruction(script)
        )

    system = prompt_manager.render("director/system.txt", overrides=overrides)
    user = prompt_manager.render(
        "director/user.txt",
        overrides=overrides,
        background=script["background"],
        objective=script.get("objective", ""),
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
        known_flags_summary=known_flags or "（本局不使用跨章节事实）",
        chapter_summaries_recent=summaries or "（本局不使用前情摘要）",
        win_condition=script.get("win_condition", ""),
        lose_condition=script.get("lose_condition", ""),
        current_turn=str(game_session["turn"]),
        max_turns=str(script.get("max_turns", 15)),
        chapter_wrap_up_instruction=wrap_instruction,
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

    if result.get("game_over"):
        result["chapter_wrap_up"] = flag_helpers.normalize_wrap_up(result.get("chapter_wrap_up"))
    else:
        result["chapter_wrap_up"] = None
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
