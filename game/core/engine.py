import logging
from collections.abc import Iterator
from typing import Any

from game import access as invite_access
from game.content import save_store, script_repository
from game.core import condition_parser, director, exits as exit_resolver, flags as flag_helpers, roleplay
from game.core import session as session_store
from game.llm import client as llm_client
from game.llm import config as llm_config
from game.prompts import manager as prompt_manager

logger = logging.getLogger(__name__)


def list_scripts() -> list[dict[str, Any]]:
    from game.content import work_progress
    from game.content.work_meta import progress_status

    summaries = script_repository.list_summary()
    enriched: list[dict[str, Any]] = []
    for item in summaries:
        row = dict(item)
        work_type = row.get("work_type") or "short_form"
        row["work_type"] = work_type
        if work_type != "long_form":
            enriched.append(row)
            continue

        work_id = row["id"]
        chapter_ids = _chapter_ids_for_work(work_id)
        chapter_count = len(chapter_ids)
        save = save_store.get_active_save_for_work(work_id)
        visited = list((save or {}).get("visited_chapter_ids") or [])
        if save and save.get("current_chapter_id") and save["current_chapter_id"] not in visited:
            visited.append(save["current_chapter_id"])
        status = progress_status(save=save, visited_count=len(visited))
        row["progress_status"] = status
        row["save_id"] = (save or {}).get("id")

        if status == "not_started":
            row["chapter_count"] = None
            row["visited_count"] = 0
            row["current_chapter_index"] = None
        else:
            row["chapter_count"] = chapter_count
            row["visited_count"] = len(visited)
            current_id = (save or {}).get("current_chapter_id")
            if current_id and current_id in chapter_ids:
                row["current_chapter_index"] = chapter_ids.index(current_id) + 1
            else:
                row["current_chapter_index"] = max(len(visited), 1)

        # Ending discovery (cross-run)
        try:
            progress = work_progress.get_progress(work_id)
            discovered = set(progress.get("discovered_endings") or [])
        except Exception:
            discovered = set()
        known = set(_known_endings_for_work(work_id))
        if known:
            row["all_endings_discovered"] = known.issubset(discovered)
        else:
            row["all_endings_discovered"] = False
        enriched.append(row)
    return enriched


def _chapter_ids_for_work(work_id: str) -> list[str]:
    """Resolve ordered chapter ids for a work (file or supabase)."""
    try:
        from game.content.script_repository import _backend, _file_long_forms, _get_cache

        if _backend() == "supabase":
            from game.content import work_repository

            work = work_repository.get_work(work_id)
            if work and work.get("chapter_ids"):
                return [str(x) for x in work["chapter_ids"]]
            chapters = work_repository.get_chapters_for_work(work_id)
            return [str(c["id"]) for c in chapters]
        _get_cache()
        pack = _file_long_forms.get(work_id)
        if pack:
            work = pack["work"]
            ids = work.get("chapter_ids") or list(pack["chapters"].keys())
            return [str(x) for x in ids]
    except Exception as exc:
        logger.warning("[engine] chapter_ids lookup failed for %s: %s", work_id, exc)
    return []


def _known_endings_for_work(work_id: str) -> list[str]:
    from game.content.work_meta import known_ending_chapter_ids

    try:
        from game.content.script_repository import _backend, _file_long_forms, _get_cache

        if _backend() == "supabase":
            from game.content import work_repository

            chapters = work_repository.get_chapters_for_work(work_id)
            return known_ending_chapter_ids(chapters)
        _get_cache()
        pack = _file_long_forms.get(work_id)
        if pack:
            return known_ending_chapter_ids(list(pack["chapters"].values()))
    except Exception as exc:
        logger.warning("[engine] known endings lookup failed for %s: %s", work_id, exc)
    return []


def load_script(script_id: str) -> dict[str, Any]:
    return script_repository.load_one(script_id)


def _is_long_form(game_session: dict[str, Any]) -> bool:
    return (game_session.get("work_type") or game_session.get("script", {}).get("work_type")) == "long_form"


def _persist_save(game_session: dict[str, Any]) -> None:
    """Best-effort save sync for long_form (memory or Supabase)."""
    if not _is_long_form(game_session):
        return
    save_id = game_session.get("save_id")
    payload = {
        "current_chapter_id": game_session.get("current_chapter_id")
        or game_session["script"].get("chapter_id"),
        "current_turn": game_session.get("turn", 0),
        "stats": game_session.get("stats") or {},
        "flags": game_session.get("flags") or {},
        "chapter_summaries": game_session.get("chapter_summaries") or [],
        "hit_key_point_ids": game_session.get("hit_key_point_ids") or [],
        "hit_pitfall_ids": game_session.get("hit_pitfall_ids") or [],
        "conversation_history": game_session.get("history") or [],
        "game_over": bool(game_session.get("game_over")),
        "outcome": game_session.get("result"),
        "visited_chapter_ids": game_session.get("visited_chapter_ids") or [],
        "had_branch_choice": bool(game_session.get("had_branch_choice")),
    }
    if game_session.get("user_id"):
        payload["user_id"] = game_session["user_id"]
    try:
        if save_id:
            save_store.update_save(save_id, payload)
        else:
            created = save_store.create_save({
                "work_id": game_session["script_id"],
                **payload,
            })
            game_session["save_id"] = created["id"]
    except Exception as exc:
        logger.warning("[engine] persist save failed: %s", exc)


def _clamp_stats(stats: dict[str, int], script: dict[str, Any]) -> dict[str, int]:
    clamped = {}
    for name, value in stats.items():
        cfg = script["stats"].get(name, {})
        minimum = cfg.get("min", 0)
        maximum = cfg.get("max", 100)
        clamped[name] = max(minimum, min(maximum, value))
    return clamped


def _evaluate_condition(
    condition: str,
    stats: dict[str, int],
    flags: dict[str, Any] | None = None,
) -> bool:
    return condition_parser.evaluate(condition, stats, flags=flags)


def _script_ending_text(
    script: dict[str, Any],
    outcome: str,
    *,
    timeout: bool = False,
) -> str:
    """Resolve fallback ending copy from script JSON (ending_lines > ending_titles)."""
    lines = script.get("ending_lines") or script.get("ending_texts") or {}
    titles = script.get("ending_titles") or {}
    ai_name = (script.get("ai_character") or {}).get("name") or "对方"
    max_turns = session_store.effective_max_turns(script.get("max_turns", 15))
    if timeout:
        text = lines.get("timeout") or titles.get("timeout")
        if text:
            return str(text)
        return f"对话进行了 {max_turns} 轮仍未明朗收场，{ai_name}失去了耐心。"

    key = outcome if outcome in ("win", "lose") else "lose"
    text = lines.get(key) or titles.get(key)
    if text:
        return str(text)

    if key == "win":
        return "你成功达成了目标。"
    return "未能达成目标，对局结束。"


def _rule_based_end(
    script: dict[str, Any],
    stats: dict[str, int],
    turn: int,
    flags: dict[str, Any] | None = None,
) -> tuple[bool, str | None, str | None]:
    if _evaluate_condition(script.get("lose_condition", ""), stats, flags):
        return True, "lose", _script_ending_text(script, "lose")
    if _evaluate_condition(script.get("win_condition", ""), stats, flags):
        return True, "win", _script_ending_text(script, "win")
    max_turns = session_store.effective_max_turns(script.get("max_turns", 15))
    if turn >= max_turns:
        return True, "lose", _script_ending_text(script, "lose", timeout=True)
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
    max_turns = session_store.effective_max_turns(script.get("max_turns", 15))
    if game_session["turn"] >= max_turns:
        raise ValueError("本局轮次已达上限")
    # Cap history growth even if a client keeps posting after soft end.
    if len(game_session["history"]) >= max_turns * 2 + 4:
        raise ValueError("本局记录过长，请重新开局")
    game_session["history"].append({
        "role": "user",
        "content": message,
        "character": script["player_character"]["name"],
    })
    game_session["turn"] += 1
    logger.info(
        "turn_start session=%s turn=%s history_len=%s msg_len=%s",
        game_session.get("script_id", "")[:24],
        game_session["turn"],
        len(game_session["history"]),
        len(message or ""),
    )
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
    flags = game_session.get("flags") or {}
    game_over = bool(director_result.get("game_over"))
    outcome = director_result.get("outcome")
    ending_text = director_result.get("ending_text")

    if not game_over:
        game_over, rule_outcome, rule_ending = _rule_based_end(
            script, stats, game_session["turn"], flags=flags
        )
        if game_over:
            outcome = rule_outcome
            if not ending_text:
                ending_text = rule_ending

    if game_over and not outcome:
        if _evaluate_condition(script.get("win_condition", ""), stats, flags):
            outcome = "win"
        else:
            outcome = "lose"

    return game_over, outcome, ending_text


def _advance_to_chapter(
    game_session: dict[str, Any],
    next_chapter_id: str,
    *,
    summary: str,
    from_chapter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Switch session to next chapter after wrap-up; returns opening payload fields."""
    from game.content.work_meta import chapter_has_branching_exits

    work_id = game_session["script_id"]
    if chapter_has_branching_exits(from_chapter):
        game_session["had_branch_choice"] = True

    next_script = script_repository.load_chapter(work_id, next_chapter_id)
    summaries = list(game_session.get("chapter_summaries") or [])
    if summary:
        summaries.append(summary)

    visited = list(game_session.get("visited_chapter_ids") or [])
    if next_chapter_id not in visited:
        visited.append(next_chapter_id)
    game_session["visited_chapter_ids"] = visited

    game_session["script"] = next_script
    game_session["current_chapter_id"] = next_chapter_id
    game_session["turn"] = 0
    game_session["hit_key_point_ids"] = []
    game_session["hit_pitfall_ids"] = []
    game_session["history"] = []
    game_session["chapter_summaries"] = summaries
    game_session["game_over"] = False
    game_session["ending_text"] = None
    game_session["result"] = None
    # Reset pending state and snapshot stats for the new chapter
    game_session["pending_next_chapter_id"] = None
    game_session["pending_chapter_summary"] = None
    game_session["pending_flags"] = None
    game_session["chapter_start_stats"] = dict(game_session.get("stats") or {})

    opening = next_script.get("opening_line", "……")
    game_session["history"].append({
        "role": "assistant",
        "content": opening,
        "character": next_script["ai_character"]["name"],
    })
    _persist_save(game_session)
    return {
        "next_chapter_id": next_chapter_id,
        "next_opening_line": opening,
        "chapter_title": next_script.get("chapter_title") or next_script.get("title"),
        "max_turns": session_store.effective_max_turns(next_script.get("max_turns", 15)),
        "visited_chapter_ids": visited,
        "had_branch_choice": bool(game_session.get("had_branch_choice")),
    }


def _stat_changes_summary(
    start: dict[str, int],
    current: dict[str, int],
) -> list[dict[str, Any]]:
    """Return only the stats that changed between chapter start and now."""
    result = []
    for name, current_val in current.items():
        start_val = start.get(name, current_val)
        if start_val != current_val:
            result.append({"stat": name, "from": start_val, "to": current_val})
    return result


def _handle_long_form_chapter_end(
    game_session: dict[str, Any],
    director_result: dict[str, Any],
    outcome: str | None,
    ending_text: str | None,
    director_cfg: llm_config.LLMConfig,
) -> dict[str, Any]:
    """Compute wrap-up and exits; for non-terminal chapters store pending advance state.

    No longer calls _advance_to_chapter() immediately — that is deferred until the
    player confirms on the chapter settlement screen via the /chapters/advance endpoint.
    """
    from game.content import work_progress

    wrap = flag_helpers.normalize_wrap_up(director_result.get("chapter_wrap_up"))
    script = game_session["script"]
    leaving_chapter = dict(script)

    new_flags = flag_helpers.apply_triggered_flags(
        game_session.get("flags") or {},
        script.get("flags_write") or [],
        wrap["triggered_flags"],
    )
    game_session["flags"] = new_flags

    exits = exit_resolver.normalize_exits(script.get("exits"))
    next_chapter_id = exit_resolver.resolve_next_chapter(
        exits,
        stats=game_session.get("stats") or {},
        flags=new_flags,
        chapter_summary=wrap["summary"],
        config=director_cfg,
    )

    # Build stat-changes summary for the settlement screen
    start_stats = game_session.get("chapter_start_stats") or {}
    stat_summary = _stat_changes_summary(start_stats, game_session.get("stats") or {})

    if next_chapter_id:
        # Non-terminal: store pending state, block further turns, persist.
        from game.content.work_meta import chapter_has_branching_exits
        if chapter_has_branching_exits(leaving_chapter):
            game_session["had_branch_choice"] = True

        game_session["game_over"] = True  # blocks further messages until advance confirmed
        game_session["pending_next_chapter_id"] = next_chapter_id
        game_session["pending_chapter_summary"] = wrap["summary"]
        game_session["pending_flags"] = new_flags
        _persist_save(game_session)

        return {
            "chapter_completed": True,
            "work_completed": False,
            "pending_advance": True,
            "next_chapter_id": next_chapter_id,
            "chapter_summary": wrap["summary"],
            "stat_changes_summary": stat_summary,
            "flags": new_flags,
            "visited_chapter_ids": game_session.get("visited_chapter_ids") or [],
            "had_branch_choice": bool(game_session.get("had_branch_choice")),
        }

    # Terminal chapter → work completed
    summaries = list(game_session.get("chapter_summaries") or [])
    summaries.append(wrap["summary"])
    game_session["chapter_summaries"] = summaries
    game_session["game_over"] = True
    game_session["ending_text"] = ending_text
    game_session["result"] = outcome
    ending_id = game_session.get("current_chapter_id") or script.get("chapter_id")
    is_new_ending = False
    user_id = game_session.get("user_id")
    try:
        if ending_id:
            work_progress.record_ending(game_session["script_id"], str(ending_id))
            if user_id:
                from game.content import user_progress
                is_new_ending = user_progress.record_ending(
                    user_id, game_session["script_id"], str(ending_id)
                )
    except Exception as exc:
        logger.warning("[engine] record ending failed: %s", exc)
    _persist_save(game_session)
    ending_tone = leaving_chapter.get("ending_tone") or "bittersweet"
    return {
        "chapter_completed": True,
        "work_completed": True,
        "pending_advance": False,
        "next_chapter_id": None,
        "chapter_summary": wrap["summary"],
        "stat_changes_summary": stat_summary,
        "flags": new_flags,
        "visited_chapter_ids": game_session.get("visited_chapter_ids") or [],
        "had_branch_choice": bool(game_session.get("had_branch_choice")),
        "ending_tone": ending_tone,
        "is_new_ending": is_new_ending,
    }


def _build_response(
    game_session: dict[str, Any],
    reply: str,
    stat_changes: dict[str, Any],
    game_over: bool,
    outcome: str | None,
    ending_text: str | None,
    emotion_tag: str = "",
    hit_key_points: list | None = None,
    hit_pitfalls: list | None = None,
    *,
    long_form_extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    script = game_session["script"]
    extras = long_form_extras or {}
    # pending_advance=True means chapter done but awaiting player confirmation —
    # never auto-advance anymore; the frontend drives that via /chapters/advance.
    advancing = False

    if advancing:
        # Chapter advanced: opening already in history; expose it as reply.
        reply = extras.get("next_opening_line") or reply
        game_over = False
        outcome = None
        ending_text = None
    elif not game_over and reply:
        game_session["history"].append({
            "role": "assistant",
            "content": reply,
            "character": script["ai_character"]["name"],
        })

    if game_over and not advancing:
        game_session["game_over"] = True
        game_session["ending_text"] = ending_text
        game_session["result"] = outcome

    if _is_long_form(game_session) and not game_over and not advancing:
        _persist_save(game_session)

    response = {
        "reply": "" if game_over else reply,
        "emotion_tag": emotion_tag,
        "stats": game_session["stats"],
        "stat_changes": stat_changes or {},
        "hit_key_points": hit_key_points or [],
        "hit_pitfalls": hit_pitfalls or [],
        "turn": game_session["turn"],
        "max_turns": session_store.effective_max_turns(script.get("max_turns", 15)),
        "game_over": game_over,
        "outcome": outcome,
        "result": outcome,
        "ending_text": ending_text,
    }
    if _is_long_form(game_session) or extras:
        response.update({
            "work_type": "long_form" if _is_long_form(game_session) else "short_form",
            "save_id": game_session.get("save_id"),
            "current_chapter_id": game_session.get("current_chapter_id")
            or script.get("chapter_id"),
            "flags": game_session.get("flags") or {},
            "chapter_completed": extras.get("chapter_completed", False),
            "work_completed": extras.get("work_completed", False),
            "pending_advance": extras.get("pending_advance", False),
            "next_chapter_id": extras.get("next_chapter_id"),
            "chapter_summary": extras.get("chapter_summary"),
            "stat_changes_summary": extras.get("stat_changes_summary") or [],
            "ending_tone": extras.get("ending_tone"),
            "is_new_ending": extras.get("is_new_ending", False),
            "chapter_title": extras.get("chapter_title")
            or script.get("chapter_title")
            or script.get("title"),
            "visited_chapter_ids": extras.get("visited_chapter_ids")
            or game_session.get("visited_chapter_ids")
            or [],
            "had_branch_choice": bool(
                extras.get("had_branch_choice", game_session.get("had_branch_choice"))
            ),
        })
        if extras.get("max_turns"):
            response["max_turns"] = extras["max_turns"]
    return response


def _finish_after_director(
    game_session: dict[str, Any],
    director_result: dict[str, Any],
    stats: dict[str, int],
    stat_changes: dict[str, Any],
    director_cfg: llm_config.LLMConfig,
    roleplay_cfg: llm_config.LLMConfig,
    player_message: str,
    *,
    debug: bool = False,
    director_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Shared post-director path for process_message / process_message_debug."""
    game_over, outcome, ending_text = _resolve_game_over(game_session, director_result, stats)
    hit_kp = director_result.get("hit_key_points") or []
    hit_pf = director_result.get("hit_pitfalls") or []

    long_form_extras: dict[str, Any] | None = None
    if game_over and _is_long_form(game_session):
        # Ensure wrap_up exists even if director omitted it (rule-based end).
        if not director_result.get("chapter_wrap_up"):
            director_result["chapter_wrap_up"] = flag_helpers.normalize_wrap_up(None)
        long_form_extras = _handle_long_form_chapter_end(
            game_session, director_result, outcome, ending_text, director_cfg
        )
        work_done = bool(long_form_extras.get("work_completed"))
        pending = bool(long_form_extras.get("pending_advance"))
        response = _build_response(
            game_session,
            "",  # no reply text — settlement screen shown instead
            stat_changes,
            work_done or pending,
            outcome if work_done else None,
            ending_text if work_done else None,
            hit_key_points=hit_kp,
            hit_pitfalls=hit_pf,
            long_form_extras=long_form_extras,
        )
        if debug:
            response["_debug"] = {
                "director": _agent_debug_payload(director_result, director_meta or {}, director_cfg),
                "roleplay": None,
                "llm_config": {
                    "director": director_cfg.public_dict(),
                    "roleplay": roleplay_cfg.public_dict(),
                },
            }
        return response

    if game_over:
        response = _build_response(
            game_session, "", stat_changes, True, outcome, ending_text,
            hit_key_points=hit_kp, hit_pitfalls=hit_pf,
        )
        # Record short-form play history for logged-in users.
        if not _is_long_form(game_session):
            user_id = game_session.get("user_id")
            if user_id:
                try:
                    from game.content import short_play_records
                    short_play_records.record_play(
                        user_id, game_session["script_id"], outcome or "lose"
                    )
                except Exception as exc:
                    logger.warning("[engine] short_play record failed: %s", exc)
        if debug:
            response["_debug"] = {
                "director": _agent_debug_payload(director_result, director_meta or {}, director_cfg),
                "roleplay": None,
                "llm_config": {
                    "director": director_cfg.public_dict(),
                    "roleplay": roleplay_cfg.public_dict(),
                },
            }
        return response

    if debug:
        roleplay_result, roleplay_meta = roleplay.respond_debug(
            game_session, player_message, director_result.get("reaction") or {}, roleplay_cfg
        )
    else:
        roleplay_result = roleplay.respond(
            game_session,
            player_message,
            director_result.get("reaction") or {},
            roleplay_cfg,
        )
        roleplay_meta = None

    reply = roleplay_result.get("reply", roleplay.ROLEPLAY_FALLBACK["reply"])
    emotion_tag = roleplay_result.get("emotion_tag", "")
    response = _build_response(
        game_session, reply, stat_changes, False, None, None, emotion_tag,
        hit_key_points=hit_kp, hit_pitfalls=hit_pf,
    )
    if debug:
        response["_debug"] = {
            "director": _agent_debug_payload(director_result, director_meta or {}, director_cfg),
            "roleplay": _agent_debug_payload(roleplay_result, roleplay_meta or {}, roleplay_cfg),
            "llm_config": {
                "director": director_cfg.public_dict(),
                "roleplay": roleplay_cfg.public_dict(),
            },
        }
    return response


def start_game(
    script_id: str,
    llm_override: dict[str, Any] | None = None,
    script_override: dict[str, Any] | None = None,
    prompt_overrides: dict[str, str] | None = None,
    ai_name: str | None = None,
    ai_persona: str | None = None,
    save_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    import copy
    director_cfg, roleplay_cfg = llm_config.resolve_dev_agent_configs(llm_override)

    resume_save: dict[str, Any] | None = None
    if save_id:
        resume_save = save_store.get_save(save_id)
        if not resume_save:
            raise ValueError(f"Save not found: {save_id}")
        if resume_save.get("work_id") != script_id:
            raise ValueError("save_id does not belong to this work")

    if script_override:
        script = copy.deepcopy(script_override)
        if not script.get("id"):
            script["id"] = script_id
    elif resume_save:
        chapter_id = resume_save.get("current_chapter_id")
        script = copy.deepcopy(
            script_repository.load_chapter(script_id, chapter_id)
            if chapter_id
            else load_script(script_id)
        )
    else:
        script = copy.deepcopy(load_script(script_id))

    if ai_name and ai_name.strip():
        script["ai_character"]["name"] = ai_name.strip()
    if ai_persona and ai_persona.strip():
        script["ai_character"]["persona"] = ai_persona.strip()

    work_type = script.get("work_type") or "short_form"
    session_kwargs: dict[str, Any] = {
        "llm_config": director_cfg.as_dict(),
        "llm_config_director": director_cfg.as_dict(),
        "llm_config_roleplay": roleplay_cfg.as_dict(),
        "prompt_overrides": prompt_overrides,
    }

    if resume_save:
        session_kwargs.update({
            "flags": resume_save.get("flags") or {},
            "chapter_summaries": resume_save.get("chapter_summaries") or [],
            "save_id": resume_save["id"],
            "history": resume_save.get("conversation_history") or [],
            "stats": resume_save.get("stats") or None,
            "turn": resume_save.get("current_turn") or 0,
            "hit_key_point_ids": [str(x) for x in (resume_save.get("hit_key_point_ids") or [])],
            "hit_pitfall_ids": [str(x) for x in (resume_save.get("hit_pitfall_ids") or [])],
            "game_over": bool(resume_save.get("game_over")),
            "ending_text": None,
            "result": resume_save.get("outcome"),
            "visited_chapter_ids": list(resume_save.get("visited_chapter_ids") or []),
            "had_branch_choice": bool(resume_save.get("had_branch_choice")),
        })

    session_id = session_store.create_session(script, **session_kwargs, user_id=user_id)
    invite_access.runtime_stats.record_session_start()
    game_session = session_store.get_session(session_id)

    opening = script.get("opening_line", "……")
    if not resume_save or not game_session["history"]:
        game_session["history"].append({
            "role": "assistant",
            "content": opening,
            "character": script["ai_character"]["name"],
        })
    else:
        # Resume: opening_line is last assistant line if present, else chapter opening.
        for entry in reversed(game_session["history"]):
            if entry.get("role") == "assistant":
                opening = entry.get("content") or opening
                break

    if work_type == "long_form" and not resume_save:
        created = save_store.create_save({
            "work_id": script_id,
            "current_chapter_id": script.get("chapter_id"),
            "current_turn": 0,
            "stats": game_session["stats"],
            "flags": {},
            "chapter_summaries": [],
            "hit_key_point_ids": [],
            "hit_pitfall_ids": [],
            "conversation_history": game_session["history"],
            "game_over": False,
            "outcome": None,
            "visited_chapter_ids": game_session.get("visited_chapter_ids") or [],
            "had_branch_choice": False,
            "user_id": game_session.get("user_id"),
        })
        game_session["save_id"] = created["id"]

    max_turns = session_store.effective_max_turns(script.get("max_turns", 15))
    result = {
        "session_id": session_id,
        "script": {
            "id": script["id"],
            "title": script["title"],
            "objective": script.get("objective", ""),
            "max_turns": max_turns,
            "ai_character_name": script["ai_character"]["name"],
            "player_character_name": script["player_character"]["name"],
            "stats_config": script.get("stats", {}),
            "ending_titles": script.get("ending_titles", {}),
            "echo_phrases": script.get("echo_phrases"),
            "tone_preset": script.get("tone_preset", "从容"),
            "chapter_title": script.get("chapter_title", script["title"]),
            "max_hints": script.get("max_hints", 3),
            "origin_tag": script.get("origin_tag", ""),
            "work_type": work_type,
            "chapter_id": script.get("chapter_id"),
        },
        "opening_line": opening,
        "stats": game_session["stats"],
        "turn": game_session["turn"],
        "llm_config": {
            "director": director_cfg.public_dict(),
            "roleplay": roleplay_cfg.public_dict(),
        },
        "history": game_session["history"] if resume_save else None,
    }
    if work_type == "long_form":
        result.update({
            "save_id": game_session.get("save_id"),
            "flags": game_session.get("flags") or {},
            "chapter_summaries": game_session.get("chapter_summaries") or [],
            "current_chapter_id": game_session.get("current_chapter_id") or script.get("chapter_id"),
            "visited_chapter_ids": game_session.get("visited_chapter_ids") or [],
            "had_branch_choice": bool(game_session.get("had_branch_choice")),
            "resumed": bool(resume_save),
        })
    return result


def process_message(session_id: str, message: str) -> dict[str, Any]:
    game_session = session_store.get_session(session_id)
    if not game_session:
        raise ValueError("Session not found")
    if game_session["game_over"] and not game_session.get("pending_next_chapter_id"):
        raise ValueError("Game is already over")
    if game_session["game_over"] and game_session.get("pending_next_chapter_id"):
        raise ValueError("章节结算中，请先翻到下一章")

    player_message = _prepare_turn(game_session, message)
    director_cfg = _session_director_config(game_session)
    roleplay_cfg = _session_roleplay_config(game_session)

    director_result = director.judge(game_session, player_message, director_cfg)
    stats, stat_changes = _process_director_turn(game_session, director_result)
    return _finish_after_director(
        game_session,
        director_result,
        stats,
        stat_changes,
        director_cfg,
        roleplay_cfg,
        player_message,
    )


def advance_chapter(session_id: str) -> dict[str, Any]:
    """Confirm the pending chapter advance after the settlement screen.

    Called when the player clicks "翻到下一章". Mutates the session to the next
    chapter and persists the save. Raises ValueError if no advance is pending.
    """
    game_session = session_store.get_session(session_id)
    if not game_session:
        raise ValueError("Session not found")
    if not _is_long_form(game_session):
        raise ValueError("Not a long-form session")

    next_chapter_id = game_session.get("pending_next_chapter_id")
    if not next_chapter_id:
        raise ValueError("No pending chapter advance")

    summary = game_session.get("pending_chapter_summary") or ""
    script = game_session["script"]

    advanced = _advance_to_chapter(
        game_session,
        next_chapter_id,
        summary=summary,
        from_chapter=dict(script),
    )
    return {
        "session_id": session_id,
        "chapter_title": advanced.get("chapter_title") or "",
        "next_opening_line": advanced.get("next_opening_line") or "",
        "max_turns": advanced.get("max_turns") or session_store.effective_max_turns(
            game_session["script"].get("max_turns", 15)
        ),
        "stats": game_session.get("stats") or {},
        "visited_chapter_ids": advanced.get("visited_chapter_ids") or [],
        "had_branch_choice": bool(advanced.get("had_branch_choice")),
        "save_id": game_session.get("save_id"),
    }


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
    if game_session["game_over"] and not game_session.get("pending_next_chapter_id"):
        raise ValueError("Game is already over")
    if game_session["game_over"] and game_session.get("pending_next_chapter_id"):
        raise ValueError("章节结算中，请先翻到下一章")

    player_message = _prepare_turn(game_session, message)
    director_cfg = _session_director_config(game_session)
    roleplay_cfg = _session_roleplay_config(game_session)

    director_result, director_meta = director.judge_debug(game_session, player_message, director_cfg)
    stats, stat_changes = _process_director_turn(game_session, director_result)
    return _finish_after_director(
        game_session,
        director_result,
        stats,
        stat_changes,
        director_cfg,
        roleplay_cfg,
        player_message,
        debug=True,
        director_meta=director_meta,
    )


def process_message_stream(session_id: str, message: str) -> Iterator[dict[str, Any]]:
    game_session = session_store.get_session(session_id)
    if not game_session:
        raise ValueError("Session not found")
    if game_session["game_over"] and not game_session.get("pending_next_chapter_id"):
        raise ValueError("Game is already over")
    if game_session["game_over"] and game_session.get("pending_next_chapter_id"):
        raise ValueError("章节结算中，请先翻到下一章")

    player_message = _prepare_turn(game_session, message)
    director_cfg = _session_director_config(game_session)
    roleplay_cfg = _session_roleplay_config(game_session)

    try:
        director_result = director.judge(game_session, player_message, director_cfg)
    except Exception as exc:
        logger.warning("[engine] director failed: %s", type(exc).__name__)
        yield {
            "type": "done",
            "reply": llm_client.NETWORK_FALLBACK_MESSAGE,
            "emotion_tag": "",
            "stats": game_session["stats"],
            "stat_changes": {},
            "hit_key_points": [],
            "hit_pitfalls": [],
            "turn": game_session["turn"],
            "max_turns": session_store.effective_max_turns(game_session["script"].get("max_turns", 15)),
            "game_over": False,
            "outcome": None,
            "result": None,
            "ending_text": None,
        }
        return

    stats, stat_changes = _process_director_turn(game_session, director_result)

    game_over, outcome, ending_text = _resolve_game_over(game_session, director_result, stats)
    hit_kp = director_result.get("hit_key_points") or []
    hit_pf = director_result.get("hit_pitfalls") or []

    if game_over:
        if _is_long_form(game_session):
            if not director_result.get("chapter_wrap_up"):
                director_result["chapter_wrap_up"] = flag_helpers.normalize_wrap_up(None)
            extras = _handle_long_form_chapter_end(
                game_session, director_result, outcome, ending_text, director_cfg
            )
            work_done = bool(extras.get("work_completed"))
            response = _build_response(
                game_session,
                "" if work_done else (extras.get("next_opening_line") or ""),
                stat_changes,
                work_done,
                outcome if work_done else None,
                ending_text if work_done else None,
                hit_key_points=hit_kp,
                hit_pitfalls=hit_pf,
                long_form_extras=extras,
            )
        else:
            response = _build_response(
                game_session, "", stat_changes, True, outcome, ending_text,
                hit_key_points=hit_kp, hit_pitfalls=hit_pf,
            )
        yield {"type": "done", **response}
        return

    accumulated = ""
    streamed_reply = ""
    streamed_emotion_tag = ""
    gotToken = False
    reaction = director_result.get("reaction") or {}

    try:
        stream_iter = roleplay.respond_stream(game_session, player_message, reaction, roleplay_cfg)
        for chunk in stream_iter:
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
    except Exception as exc:
        logger.warning("[engine] roleplay stream failed: %s", type(exc).__name__)
        reply = streamed_reply or llm_client.NETWORK_FALLBACK_MESSAGE
        emotion_tag = streamed_emotion_tag
        response = _build_response(
            game_session, reply, stat_changes, False, None, None, emotion_tag,
            hit_key_points=hit_kp, hit_pitfalls=hit_pf,
        )
        yield {"type": "done", **response}
        return

    try:
        parsed = llm_client.parse_json_response(accumulated)
        reply = parsed.get("reply") or streamed_reply or roleplay.ROLEPLAY_FALLBACK["reply"]
        emotion_tag = roleplay._validate_emotion_tag(parsed.get("emotion_tag"), game_session["script"])
    except Exception:
        logger.warning("[roleplay] stream JSON parse failed, using streamed/fallback reply")
        reply = streamed_reply or roleplay.ROLEPLAY_FALLBACK["reply"]
        emotion_tag = ""

    response = _build_response(
        game_session, reply, stat_changes, False, None, None, emotion_tag,
        hit_key_points=hit_kp, hit_pitfalls=hit_pf,
    )
    yield {"type": "done", **response}


def get_hint(session_id: str) -> dict[str, Any]:
    game_session = session_store.get_session(session_id)
    if not game_session:
        raise ValueError("Session not found")
    if game_session["game_over"]:
        raise ValueError("对局已结束")

    max_hints = game_session["script"].get("max_hints", 3)
    hints_used = game_session.get("hints_used", 0)
    if hints_used >= max_hints:
        raise ValueError("本局提示次数已用完")

    script = game_session["script"]
    cfg = _session_llm_config(game_session)
    overrides = game_session.get("prompt_overrides")
    system_prompt = prompt_manager.render("hint/system.txt", overrides=overrides)
    user_prompt = prompt_manager.render(
        "hint/user.txt",
        overrides=overrides,
        script_title=script["title"],
        objective=script.get("objective", ""),
        current_turn=str(game_session["turn"]),
        max_turns=str(script.get("max_turns", 15)),
        current_stats=prompt_manager.format_stats(game_session["stats"]),
        conversation_history=prompt_manager.format_history(game_session["history"][-6:]),
        pending_key_points=prompt_manager.format_pending_key_points(
            script, game_session.get("hit_key_point_ids", [])
        ),
        pending_pitfalls=prompt_manager.format_pending_pitfalls(
            script, game_session.get("hit_pitfall_ids", [])
        ),
    )

    try:
        hint_text = llm_client.chat_completion(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            cfg,
            temperature=0.6,
        ).strip()
    except Exception as exc:
        logger.warning("[hint] LLM call failed: %s", exc)
        raise ValueError("暂时无法生成提示，请稍后再试") from exc

    if not hint_text:
        hint_text = "试着从对方最在意的情绪入手，用真诚、具体的话回应。"

    game_session["hints_used"] = hints_used + 1
    return {
        "hint": hint_text,
        "hints_used": game_session["hints_used"],
        "hints_remaining": max_hints - game_session["hints_used"],
    }
