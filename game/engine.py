import logging
from collections.abc import Iterator
from typing import Any

from game import director, llm_client, roleplay, prompt_manager
from game import llm_config
from game import session as session_store
from game import condition_parser
from game import script_repository

logger = logging.getLogger(__name__)


def list_scripts() -> list[dict[str, Any]]:
    return script_repository.list_summary()


def load_script(script_id: str) -> dict[str, Any]:
    return script_repository.load_one(script_id)


def _clamp_stats(stats: dict[str, int], script: dict[str, Any]) -> dict[str, int]:
    clamped = {}
    for name, value in stats.items():
        cfg = script["stats"].get(name, {})
        minimum = cfg.get("min", 0)
        maximum = cfg.get("max", 100)
        clamped[name] = max(minimum, min(maximum, value))
    return clamped


def _evaluate_condition(condition: str, stats: dict[str, int]) -> bool:
    return condition_parser.evaluate(condition, stats)


def _rule_based_end(script: dict[str, Any], stats: dict[str, int], turn: int) -> tuple[bool, str | None, str | None]:
    if _evaluate_condition(script["lose_condition"], stats):
        return True, "lose", "唐晶的愤怒已经彻底爆发，她转身离开，再也不愿听你解释。"
    if _evaluate_condition(script["win_condition"], stats):
        return True, "win", "唐晶的表情渐渐柔和下来，她轻轻叹了口气：「好吧，我相信你。」"
    max_turns = script.get("max_turns", 15)
    if turn >= max_turns:
        return True, "lose", f"对话进行了 {max_turns} 轮仍未化解矛盾，唐晶失去了耐心，游戏结束。"
    return False, None, None


def _session_llm_config(game_session: dict[str, Any]) -> llm_config.LLMConfig:
    stored = game_session.get("llm_config")
    if stored:
        return llm_config.resolve_config(stored)
    return llm_config.resolve_config(None)


def _session_director_config(game_session: dict[str, Any]) -> llm_config.LLMConfig:
    stored = game_session.get("llm_config_director") or game_session.get("llm_config")
    if stored:
        return llm_config.resolve_config(stored)
    return llm_config.resolve_config(None)


def _session_roleplay_config(game_session: dict[str, Any]) -> llm_config.LLMConfig:
    stored = game_session.get("llm_config_roleplay") or game_session.get("llm_config")
    if stored:
        return llm_config.resolve_config(stored)
    return llm_config.resolve_config(None)


def _prepare_turn(game_session: dict[str, Any], message: str) -> str:
    script = game_session["script"]
    game_session["history"].append({
        "role": "user",
        "content": message,
        "character": script["player_character"]["name"],
    })
    game_session["turn"] += 1
    return message


def _apply_stat_changes(game_session: dict[str, Any], stat_changes: dict[str, Any]) -> dict[str, int]:
    script = game_session["script"]
    new_stats = dict(game_session["stats"])
    for name, delta in (stat_changes or {}).items():
        if name in new_stats and isinstance(delta, (int, float)):
            new_stats[name] = int(new_stats[name] + delta)
    new_stats = _clamp_stats(new_stats, script)
    game_session["stats"] = new_stats
    return new_stats


def _normalize_point_id(raw: Any) -> str | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, int):
        return str(raw)
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))
    return None


def _resolve_hit_deltas(
    kp_hits: list[str],
    kp_by_id: dict[str, dict[str, Any]],
    pf_hits: list[str],
    pf_by_id: dict[str, dict[str, Any]],
    director_extra: dict[str, Any],
) -> dict[str, int]:
    ranges_by_stat: dict[str, list[tuple[int, int]]] = {}

    for point_id in kp_hits:
        for stat, spec in kp_by_id[point_id].get("hit_stat_changes", {}).items():
            ranges_by_stat.setdefault(stat, []).append(prompt_manager.parse_stat_range(spec))
    for point_id in pf_hits:
        for stat, spec in pf_by_id[point_id].get("hit_stat_changes", {}).items():
            ranges_by_stat.setdefault(stat, []).append(prompt_manager.parse_stat_range(spec))

    merged: dict[str, int] = {}
    for stat, ranges in ranges_by_stat.items():
        total_lo = sum(r[0] for r in ranges)
        total_hi = sum(r[1] for r in ranges)
        director_value = director_extra.get(stat)
        if isinstance(director_value, (int, float)):
            picked = int(director_value)
            if total_lo <= picked <= total_hi:
                merged[stat] = picked
                continue
        merged[stat] = sum((lo + hi) // 2 for lo, hi in ranges)

    return merged


def _merge_director_stat_changes(
    game_session: dict[str, Any],
    director_result: dict[str, Any],
) -> tuple[dict[str, int], list[str], list[str]]:
    script = game_session["script"]
    hit_kp_ids = [
        pid for pid in (_normalize_point_id(i) for i in (director_result.get("hit_key_points") or []))
        if pid is not None
    ]
    hit_pf_ids = [
        pid for pid in (_normalize_point_id(i) for i in (director_result.get("hit_pitfalls") or []))
        if pid is not None
    ]

    already_kp = set(str(i) for i in game_session.get("hit_key_point_ids", []))
    already_pf = set(str(i) for i in game_session.get("hit_pitfall_ids", []))

    kp_by_id = {str(item["id"]): item for item in script.get("key_points", []) if "id" in item}
    pf_by_id = {str(item["id"]): item for item in script.get("pitfalls", []) if "id" in item}

    validated_kp = [i for i in hit_kp_ids if i in kp_by_id and i not in already_kp]
    validated_pf = [i for i in hit_pf_ids if i in pf_by_id and i not in already_pf]

    director_extra = director_result.get("stat_changes") or {}
    merged: dict[str, int] = {}

    if validated_kp or validated_pf:
        merged = _resolve_hit_deltas(
            validated_kp, kp_by_id, validated_pf, pf_by_id, director_extra
        )

    hit_stats = set(merged.keys())
    claimed_hits = bool(hit_kp_ids or hit_pf_ids)

    if not validated_kp and not validated_pf:
        if not claimed_hits:
            for stat, delta in director_extra.items():
                if isinstance(delta, (int, float)):
                    merged[stat] = merged.get(stat, 0) + int(delta)
    else:
        for stat, delta in director_extra.items():
            if stat not in hit_stats and isinstance(delta, (int, float)):
                merged[stat] = merged.get(stat, 0) + int(delta)

    game_session.setdefault("hit_key_point_ids", [])
    game_session.setdefault("hit_pitfall_ids", [])
    game_session["hit_key_point_ids"].extend(validated_kp)
    game_session["hit_pitfall_ids"].extend(validated_pf)

    return merged, validated_kp, validated_pf


def _process_director_turn(
    game_session: dict[str, Any],
    director_result: dict[str, Any],
) -> tuple[dict[str, int], dict[str, int]]:
    stat_changes, validated_kp, validated_pf = _merge_director_stat_changes(
        game_session, director_result
    )
    stats = _apply_stat_changes(game_session, stat_changes)
    if validated_kp or validated_pf:
        logger.info(
            "[engine] key hits kp=%s pf=%s stat_changes=%s",
            validated_kp,
            validated_pf,
            stat_changes,
        )
    return stats, stat_changes


def _resolve_game_over(
    game_session: dict[str, Any],
    director_result: dict[str, Any],
    stats: dict[str, int],
) -> tuple[bool, str | None, str | None]:
    script = game_session["script"]
    game_over = bool(director_result.get("game_over"))
    outcome = director_result.get("outcome")
    ending_text = director_result.get("ending_text")

    if not game_over:
        game_over, rule_outcome, rule_ending = _rule_based_end(script, stats, game_session["turn"])
        if game_over:
            outcome = rule_outcome
            if not ending_text:
                ending_text = rule_ending

    if game_over and not outcome:
        if _evaluate_condition(script["win_condition"], stats):
            outcome = "win"
        else:
            outcome = "lose"

    return game_over, outcome, ending_text


def _build_response(
    game_session: dict[str, Any],
    reply: str,
    stat_changes: dict[str, Any],
    game_over: bool,
    outcome: str | None,
    ending_text: str | None,
    emotion_tag: str = "",
) -> dict[str, Any]:
    script = game_session["script"]

    if not game_over:
        game_session["history"].append({
            "role": "assistant",
            "content": reply,
            "character": script["ai_character"]["name"],
        })

    if game_over:
        game_session["game_over"] = True
        game_session["ending_text"] = ending_text
        game_session["result"] = outcome
        if reply:
            game_session["history"].append({
                "role": "assistant",
                "content": reply,
                "character": script["ai_character"]["name"],
            })

    return {
        "reply": reply,
        "emotion_tag": emotion_tag,
        "stats": game_session["stats"],
        "stat_changes": stat_changes or {},
        "turn": game_session["turn"],
        "max_turns": script.get("max_turns", 15),
        "game_over": game_over,
        "outcome": outcome,
        "result": outcome,
        "ending_text": ending_text,
    }


def start_game(
    script_id: str,
    llm_override: dict[str, Any] | None = None,
    script_override: dict[str, Any] | None = None,
    prompt_overrides: dict[str, str] | None = None,
    ai_name: str | None = None,
    ai_persona: str | None = None,
) -> dict[str, Any]:
    import copy
    director_cfg, roleplay_cfg = llm_config.resolve_dev_agent_configs(llm_override)
    if script_override:
        script = copy.deepcopy(script_override)
        if not script.get("id"):
            script["id"] = script_id
    else:
        script = copy.deepcopy(load_script(script_id))

    if ai_name and ai_name.strip():
        script["ai_character"]["name"] = ai_name.strip()
    if ai_persona and ai_persona.strip():
        script["ai_character"]["persona"] = ai_persona.strip()

    session_id = session_store.create_session(
        script,
        llm_config=director_cfg.as_dict(),
        llm_config_director=director_cfg.as_dict(),
        llm_config_roleplay=roleplay_cfg.as_dict(),
        prompt_overrides=prompt_overrides,
    )
    game_session = session_store.get_session(session_id)
    opening = script.get("opening_line", "……")
    game_session["history"].append({
        "role": "assistant",
        "content": opening,
        "character": script["ai_character"]["name"],
    })
    return {
        "session_id": session_id,
        "script": {
            "id": script["id"],
            "title": script["title"],
            "objective": script["objective"],
            "max_turns": script.get("max_turns", 15),
            "ai_character_name": script["ai_character"]["name"],
            "player_character_name": script["player_character"]["name"],
            "stats_config": script.get("stats", {}),
            "ending_titles": script.get("ending_titles", {}),
        },
        "opening_line": opening,
        "stats": game_session["stats"],
        "turn": game_session["turn"],
        "llm_config": {
            "director": director_cfg.public_dict(),
            "roleplay": roleplay_cfg.public_dict(),
        },
    }


def process_message(session_id: str, message: str) -> dict[str, Any]:
    game_session = session_store.get_session(session_id)
    if not game_session:
        raise ValueError("Session not found")
    if game_session["game_over"]:
        raise ValueError("Game is already over")

    player_message = _prepare_turn(game_session, message)
    director_cfg = _session_director_config(game_session)
    roleplay_cfg = _session_roleplay_config(game_session)

    director_result = director.judge(game_session, player_message, director_cfg)
    stats, stat_changes = _process_director_turn(game_session, director_result)

    game_over, outcome, ending_text = _resolve_game_over(game_session, director_result, stats)

    if game_over:
        reply = ending_text or "游戏结束。"
        return _build_response(game_session, reply, stat_changes, True, outcome, ending_text)

    reaction = director_result.get("reaction") or {}
    roleplay_result = roleplay.respond(
        game_session,
        player_message,
        reaction,
        roleplay_cfg,
    )
    reply = roleplay_result.get("reply", roleplay.ROLEPLAY_FALLBACK["reply"])
    emotion_tag = roleplay_result.get("emotion_tag", "")
    return _build_response(game_session, reply, stat_changes, False, None, None, emotion_tag)


def _agent_debug_payload(
    result: dict[str, Any] | None,
    meta: dict[str, Any],
    cfg: llm_config.LLMConfig,
) -> dict[str, Any]:
    return {
        "output": result,
        "prompts": meta.get("prompts") or {},
        "ttft_ms": meta.get("ttft_ms"),
        "total_ms": meta.get("total_ms"),
        "usage": meta.get("usage") or {},
        "raw_output": meta.get("raw_output", ""),
        "model": cfg.model,
        "provider": cfg.provider,
        "api_base": cfg.api_base,
    }


def process_message_debug(session_id: str, message: str) -> dict[str, Any]:
    """Same as process_message but includes prompts, timing, tokens in _debug."""
    game_session = session_store.get_session(session_id)
    if not game_session:
        raise ValueError("Session not found")
    if game_session["game_over"]:
        raise ValueError("Game is already over")

    player_message = _prepare_turn(game_session, message)
    director_cfg = _session_director_config(game_session)
    roleplay_cfg = _session_roleplay_config(game_session)

    director_result, director_meta = director.judge_debug(game_session, player_message, director_cfg)
    stats, stat_changes = _process_director_turn(game_session, director_result)

    game_over, outcome, ending_text = _resolve_game_over(game_session, director_result, stats)

    if game_over:
        reply = ending_text or "游戏结束。"
        response = _build_response(game_session, reply, stat_changes, True, outcome, ending_text)
        response["_debug"] = {
            "director": _agent_debug_payload(director_result, director_meta, director_cfg),
            "roleplay": None,
            "llm_config": {
                "director": director_cfg.public_dict(),
                "roleplay": roleplay_cfg.public_dict(),
            },
        }
        return response

    reaction = director_result.get("reaction") or {}
    roleplay_result, roleplay_meta = roleplay.respond_debug(
        game_session, player_message, reaction, roleplay_cfg
    )
    reply = roleplay_result.get("reply", roleplay.ROLEPLAY_FALLBACK["reply"])
    emotion_tag = roleplay_result.get("emotion_tag", "")
    response = _build_response(game_session, reply, stat_changes, False, None, None, emotion_tag)
    response["_debug"] = {
        "director": _agent_debug_payload(director_result, director_meta, director_cfg),
        "roleplay": _agent_debug_payload(roleplay_result, roleplay_meta, roleplay_cfg),
        "llm_config": {
            "director": director_cfg.public_dict(),
            "roleplay": roleplay_cfg.public_dict(),
        },
    }
    return response


def process_message_stream(session_id: str, message: str) -> Iterator[dict[str, Any]]:
    game_session = session_store.get_session(session_id)
    if not game_session:
        raise ValueError("Session not found")
    if game_session["game_over"]:
        raise ValueError("Game is already over")

    player_message = _prepare_turn(game_session, message)
    director_cfg = _session_director_config(game_session)
    roleplay_cfg = _session_roleplay_config(game_session)

    director_result = director.judge(game_session, player_message, director_cfg)
    stats, stat_changes = _process_director_turn(game_session, director_result)

    game_over, outcome, ending_text = _resolve_game_over(game_session, director_result, stats)

    if game_over:
        reply = ending_text or "游戏结束。"
        response = _build_response(game_session, reply, stat_changes, True, outcome, ending_text)
        yield {"type": "done", **response}
        return

    accumulated = ""
    streamed_reply = ""
    streamed_emotion_tag = ""
    gotToken = False
    reaction = director_result.get("reaction") or {}

    for chunk in roleplay.respond_stream(game_session, player_message, reaction, roleplay_cfg):
        accumulated += chunk

        if not streamed_emotion_tag:
            extracted_tag = llm_client.extract_emotion_tag_from_partial_json(accumulated)
            if extracted_tag:
                streamed_emotion_tag = extracted_tag
                yield {"type": "emotion_tag", "emotion_tag": streamed_emotion_tag}

        reply = llm_client.extract_reply_from_partial_json(accumulated)
        if len(reply) > len(streamed_reply):
            yield {"type": "token", "content": reply[len(streamed_reply):]}
            streamed_reply = reply
            gotToken = True

    try:
        parsed = llm_client.parse_json_response(accumulated)
        reply = parsed.get("reply") or streamed_reply or roleplay.ROLEPLAY_FALLBACK["reply"]
        emotion_tag = roleplay._validate_emotion_tag(parsed.get("emotion_tag"), game_session["script"])
    except Exception:
        logger.warning("[roleplay] stream JSON parse failed, using streamed/fallback reply")
        reply = streamed_reply or roleplay.ROLEPLAY_FALLBACK["reply"]
        emotion_tag = ""

    response = _build_response(game_session, reply, stat_changes, False, None, None, emotion_tag)
    yield {"type": "done", **response}
