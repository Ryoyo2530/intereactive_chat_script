import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from game import llm_client
from game import llm_config
from game import session as session_store

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def list_scripts() -> list[dict[str, str]]:
    scripts = []
    for path in sorted(SCRIPTS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        scripts.append({
            "id": data["id"],
            "title": data["title"],
            "objective": data.get("objective", ""),
        })
    return scripts


def load_script(script_id: str) -> dict[str, Any]:
    path = SCRIPTS_DIR / f"{script_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Script not found: {script_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _clamp_stats(stats: dict[str, int], script: dict[str, Any]) -> dict[str, int]:
    clamped = {}
    for name, value in stats.items():
        cfg = script["stats"].get(name, {})
        minimum = cfg.get("min", 0)
        maximum = cfg.get("max", 100)
        clamped[name] = max(minimum, min(maximum, value))
    return clamped


def _evaluate_condition(condition: str, stats: dict[str, int]) -> bool:
    parts = re.split(r"\s*且\s*", condition.strip())
    for part in parts:
        match = re.match(r"(.+?)\s*(<=|>=|<|>|==)\s*(-?\d+)", part.strip())
        if not match:
            continue
        stat_name, op, raw_value = match.groups()
        stat_name = stat_name.strip()
        value = stats.get(stat_name, 0)
        threshold = int(raw_value)
        if op == "<=" and not (value <= threshold):
            return False
        if op == ">=" and not (value >= threshold):
            return False
        if op == "<" and not (value < threshold):
            return False
        if op == ">" and not (value > threshold):
            return False
        if op == "==" and not (value == threshold):
            return False
    return True


def _check_game_end(script: dict[str, Any], stats: dict[str, int], turn: int) -> tuple[bool, str | None, str | None]:
    if _evaluate_condition(script["lose_condition"], stats):
        return True, "lose", "唐晶的愤怒已经彻底爆发，她转身离开，再也不愿听你解释。"
    if _evaluate_condition(script["win_condition"], stats):
        return True, "win", "唐晶的表情渐渐柔和下来，她轻轻叹了口气：「好吧，我相信你。」"
    max_turns = script.get("max_turns", 15)
    if turn >= max_turns:
        return True, "lose", f"对话进行了 {max_turns} 轮仍未化解矛盾，唐晶失去了耐心，游戏结束。"
    return False, None, None


def _build_system_prompt(script: dict[str, Any], stats: dict[str, int]) -> str:
    stat_lines = "\n".join(f"- {name}: {value}" for name, value in stats.items())
    return f"""你是一款互动文字游戏的 AI 角色扮演引擎。

【剧本背景】
{script["background"]}

【AI 角色】
姓名：{script["ai_character"]["name"]}
人设：{script["ai_character"]["persona"]}

【玩家角色】
姓名：{script["player_character"]["name"]}

【游戏目标】
{script["objective"]}

【当前数值状态】
{stat_lines}

【规则】
1. 以 {script["ai_character"]["name"]} 的身份回复玩家，保持角色说话风格。
2. 根据玩家的话合理调整数值（怀疑值、愤怒值等），变化幅度通常在 -15 到 +15 之间。
3. 只返回 JSON，不要有任何其他文字。格式如下：
{{
  "reply": "角色回复文本",
  "stat_changes": {{"怀疑值": -5, "愤怒值": 10}},
  "game_over": false,
  "ending_text": null
}}
4. 如果对话自然达到结局，可设置 game_over 为 true 并填写 ending_text；否则 game_over 为 false。
5. stat_changes 只包含发生变化的数值，没变化的可以省略或为 0。"""


def _build_messages(game_session: dict[str, Any]) -> list[dict[str, str]]:
    script = game_session["script"]
    messages = [{"role": "system", "content": _build_system_prompt(script, game_session["stats"])}]
    for entry in game_session["history"]:
        role = "assistant" if entry["role"] == "assistant" else "user"
        prefix = f"[{entry.get('character', '')}] " if entry.get("character") else ""
        messages.append({"role": role, "content": prefix + entry["content"]})
    return messages


def _default_fallback() -> dict[str, Any]:
    return {
        "reply": "（唐晶沉默了一会儿，似乎在思考你说的话。）",
        "stat_changes": {},
        "game_over": False,
        "ending_text": None,
    }


def _finalize_turn(
    game_session: dict[str, Any],
    result: dict[str, Any],
    reply_override: str | None = None,
) -> dict[str, Any]:
    script = game_session["script"]
    fallback = _default_fallback()
    reply = reply_override or result.get("reply", fallback["reply"])
    stat_changes = result.get("stat_changes") or {}

    new_stats = dict(game_session["stats"])
    for name, delta in stat_changes.items():
        if name in new_stats and isinstance(delta, (int, float)):
            new_stats[name] = int(new_stats[name] + delta)
    new_stats = _clamp_stats(new_stats, script)
    game_session["stats"] = new_stats

    game_session["history"].append({
        "role": "assistant",
        "content": reply,
        "character": script["ai_character"]["name"],
    })

    game_over = bool(result.get("game_over"))
    ending_text = result.get("ending_text")
    result_type = None

    if not game_over:
        game_over, result_type, rule_ending = _check_game_end(script, new_stats, game_session["turn"])
        if game_over and not ending_text:
            ending_text = rule_ending

    if game_over:
        game_session["game_over"] = True
        game_session["ending_text"] = ending_text
        if result_type is None:
            if _evaluate_condition(script["win_condition"], new_stats):
                result_type = "win"
            else:
                result_type = "lose"
        game_session["result"] = result_type

    return {
        "reply": reply,
        "stats": new_stats,
        "stat_changes": stat_changes,
        "turn": game_session["turn"],
        "max_turns": script.get("max_turns", 15),
        "game_over": game_over,
        "result": result_type,
        "ending_text": ending_text,
    }


def _prepare_turn(game_session: dict[str, Any], message: str) -> list[dict[str, str]]:
    script = game_session["script"]
    game_session["history"].append({
        "role": "user",
        "content": message,
        "character": script["player_character"]["name"],
    })
    game_session["turn"] += 1
    return _build_messages(game_session)


def _session_llm_config(game_session: dict[str, Any]):
    return llm_config.resolve_config(game_session.get("llm_config"))


def start_game(script_id: str, llm_override: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = llm_config.resolve_config(llm_override)
    script = load_script(script_id)
    session_id = session_store.create_session(script, llm_config=cfg.as_dict())
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
        },
        "opening_line": opening,
        "stats": game_session["stats"],
        "turn": game_session["turn"],
    }


def process_message(session_id: str, message: str) -> dict[str, Any]:
    game_session = session_store.get_session(session_id)
    if not game_session:
        raise ValueError("Session not found")
    if game_session["game_over"]:
        raise ValueError("Game is already over")

    messages = _prepare_turn(game_session, message)
    fallback = _default_fallback()
    cfg = _session_llm_config(game_session)
    result = llm_client.chat_json(messages, cfg, fallback)
    return _finalize_turn(game_session, result)


def process_message_stream(session_id: str, message: str) -> Iterator[dict[str, Any]]:
    game_session = session_store.get_session(session_id)
    if not game_session:
        raise ValueError("Session not found")
    if game_session["game_over"]:
        raise ValueError("Game is already over")

    messages = _prepare_turn(game_session, message)
    fallback = _default_fallback()
    cfg = _session_llm_config(game_session)
    accumulated = ""
    streamed_reply = ""

    for chunk in llm_client.chat_stream(messages, cfg):
        accumulated += chunk
        reply = llm_client.extract_reply_from_partial_json(accumulated)
        if len(reply) > len(streamed_reply):
            yield {"type": "token", "content": reply[len(streamed_reply):]}
            streamed_reply = reply

    try:
        result = llm_client.parse_json_response(accumulated)
    except Exception:
        result = dict(fallback)
        if streamed_reply:
            result["reply"] = streamed_reply

    response = _finalize_turn(
        game_session,
        result,
        reply_override=streamed_reply or result.get("reply", fallback["reply"]),
    )
    yield {"type": "done", **response}
