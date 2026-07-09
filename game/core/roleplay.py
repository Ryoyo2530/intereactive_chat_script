import logging
from collections.abc import Iterator
from typing import Any

from game.llm import client as llm_client
from game.llm.config import LLMConfig
from game.prompts import manager as prompt_manager

logger = logging.getLogger(__name__)

ROLEPLAY_FALLBACK = {"reply": "……（唐晶一时语塞，似乎在整理思绪。）", "emotion_tag": ""}


def _validate_emotion_tag(tag: Any, script: dict[str, Any]) -> str:
    vocab: list[str] = script.get("ai_character", {}).get("emotion_vocabulary", [])
    if isinstance(tag, str) and tag.strip() in vocab:
        return tag.strip()
    return ""


def _build_messages(
    game_session: dict[str, Any],
    player_message: str,
    reaction: dict[str, str],
) -> list[dict[str, str]]:
    script = game_session["script"]
    overrides = game_session.get("prompt_overrides")
    system = prompt_manager.render(
        "roleplay/system.txt",
        overrides=overrides,
        ai_character_name=script["ai_character"]["name"],
        ai_character_persona=script["ai_character"]["persona"],
        background=script["background"],
    )
    user = prompt_manager.render(
        "roleplay/user.txt",
        overrides=overrides,
        conversation_history=prompt_manager.format_history(game_session["history"]),
        player_character_name=script["player_character"]["name"],
        player_message=player_message,
        reaction_tone=reaction.get("tone", "冷静"),
        reaction_intensity=reaction.get("intensity", "中"),
        reaction_focus=reaction.get("focus", "回应玩家"),
        emotion_vocabulary=prompt_manager.format_emotion_vocabulary(script),
        ai_character_name=script["ai_character"]["name"],
    )
    logger.info("[roleplay] system prompt:\n%s", system)
    logger.info("[roleplay] user prompt:\n%s", user)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def respond(
    game_session: dict[str, Any],
    player_message: str,
    reaction: dict[str, str],
    config: LLMConfig,
) -> dict[str, Any]:
    result, _meta = respond_debug(game_session, player_message, reaction, config)
    return result


def respond_debug(
    game_session: dict[str, Any],
    player_message: str,
    reaction: dict[str, str],
    config: LLMConfig,
) -> tuple[dict[str, Any], dict[str, Any]]:
    messages = _build_messages(game_session, player_message, reaction)
    try:
        result, meta = llm_client.chat_json_stream_debug(messages, config, ROLEPLAY_FALLBACK)
    except Exception as exc:
        logger.warning("[roleplay] LLM call failed: %s", exc)
        return dict(ROLEPLAY_FALLBACK), {
            "prompts": llm_client._prompts_from_messages(messages),
            "ttft_ms": 0,
            "total_ms": 0,
            "usage": {"input_tokens": None, "output_tokens": None},
            "raw_output": "",
        }

    if not result.get("reply"):
        logger.warning("[roleplay] JSON parse failed or empty reply, using fallback")
        return dict(ROLEPLAY_FALLBACK), meta

    result["emotion_tag"] = _validate_emotion_tag(result.get("emotion_tag"), game_session["script"])
    return result, meta


def respond_stream(
    game_session: dict[str, Any],
    player_message: str,
    reaction: dict[str, str],
    config: LLMConfig,
) -> Iterator[str]:
    messages = _build_messages(game_session, player_message, reaction)
    for chunk in llm_client.chat_stream(messages, config):
        yield chunk
