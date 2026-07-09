"""Static hypothetical stat path calculator for dev editor (no LLM)."""

from typing import Any

from game.core import condition_parser
from game.prompts import manager as prompt_manager


def _midpoint_delta(spec: Any) -> int:
    lo, hi = prompt_manager.parse_stat_range(spec)
    return (lo + hi) // 2


def _clamp_stats(stats: dict[str, int], script: dict[str, Any]) -> dict[str, int]:
    stats_cfg = script.get("stats") or {}
    clamped = {}
    for name, value in stats.items():
        cfg = stats_cfg.get(name, {})
        minimum = cfg.get("min", 0)
        maximum = cfg.get("max", 100)
        clamped[name] = max(minimum, min(maximum, int(value)))
    return clamped


def compute_hypothetical(
    script: dict[str, Any],
    selected_key_point_ids: list[str | int],
    selected_pitfall_ids: list[str | int],
) -> dict[str, Any]:
    stats_cfg = script.get("stats") or {}
    stats = {name: int(cfg.get("initial", 0)) for name, cfg in stats_cfg.items()}

    kp_by_id = {str(item["id"]): item for item in script.get("key_points", []) if "id" in item}
    pf_by_id = {str(item["id"]): item for item in script.get("pitfalls", []) if "id" in item}

    applied_kp: list[str] = []
    applied_pf: list[str] = []

    for raw_id in selected_key_point_ids:
        pid = str(raw_id)
        item = kp_by_id.get(pid)
        if not item:
            continue
        applied_kp.append(pid)
        for stat, spec in item.get("hit_stat_changes", {}).items():
            if stat in stats:
                stats[stat] += _midpoint_delta(spec)

    for raw_id in selected_pitfall_ids:
        pid = str(raw_id)
        item = pf_by_id.get(pid)
        if not item:
            continue
        applied_pf.append(pid)
        for stat, spec in item.get("hit_stat_changes", {}).items():
            if stat in stats:
                stats[stat] += _midpoint_delta(spec)

    stats = _clamp_stats(stats, script)

    win_condition = script.get("win_condition", "")
    lose_condition = script.get("lose_condition", "")
    max_turns = int(script.get("max_turns", 15))

    would_win = bool(win_condition) and condition_parser.evaluate(win_condition, stats)
    would_lose = bool(lose_condition) and condition_parser.evaluate(lose_condition, stats)

    if would_win:
        outcome = "win"
    elif would_lose:
        outcome = "lose"
    else:
        outcome = "ongoing"

    min_turns_needed = len(applied_kp)
    turn_margin = max_turns - min_turns_needed

    return {
        "stats": stats,
        "initial_stats": {name: int(cfg.get("initial", 0)) for name, cfg in stats_cfg.items()},
        "applied_key_points": applied_kp,
        "applied_pitfalls": applied_pf,
        "would_win": would_win,
        "would_lose": would_lose,
        "outcome": outcome,
        "min_turns_needed": min_turns_needed,
        "max_turns": max_turns,
        "turn_margin": turn_margin,
        "win_condition": win_condition,
        "lose_condition": lose_condition,
    }
