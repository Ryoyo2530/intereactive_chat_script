"""Evaluate chapter exit conditions (hard_condition + ai_choice)."""

from __future__ import annotations

import logging
import re
from typing import Any

from game.core import condition_parser
from game.llm import client as llm_client
from game.llm.config import LLMConfig

logger = logging.getLogger(__name__)


def normalize_exits(raw: Any) -> list[dict[str, Any]]:
    """Normalize chapter exits to a list of exit dicts.

    short_form uses a single terminal object; long_form uses a list.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return [e for e in raw if isinstance(e, dict)]
    if isinstance(raw, dict):
        if raw.get("type") == "terminal":
            return []
        return [raw]
    return []


def evaluate_hard_exits(
    exits: list[dict[str, Any]],
    stats: dict[str, int],
    flags: dict[str, Any],
) -> str | None:
    """Return first hard_condition next_chapter that matches, else None."""
    for exit_def in exits:
        if exit_def.get("type") != "hard_condition":
            continue
        condition = str(exit_def.get("condition") or "").strip()
        next_chapter = exit_def.get("next_chapter")
        if not condition or not next_chapter:
            continue
        if condition_parser.evaluate(condition, stats, flags=flags):
            logger.info(
                "[exits] hard_condition matched → %s (condition=%s)",
                next_chapter,
                condition,
            )
            return str(next_chapter)
    return None


def _extract_chapter_id(raw: Any, candidates: list[str]) -> str | None:
    if isinstance(raw, dict):
        for key in ("next_chapter", "chapter_id", "choice", "id"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip() in candidates:
                return value.strip()
        return None
    if isinstance(raw, str):
        text = raw.strip()
        if text in candidates:
            return text
        # Tolerate prose that mentions a candidate id.
        for candidate in candidates:
            if re.search(rf"\b{re.escape(candidate)}\b", text):
                return candidate
    return None


def resolve_ai_choice(
    exit_def: dict[str, Any],
    *,
    chapter_summary: str,
    stats: dict[str, int],
    flags: dict[str, Any],
    config: LLMConfig,
) -> str:
    """Pick next chapter from ai_choice candidates; always returns a chapter id."""
    candidates = [str(c) for c in (exit_def.get("candidates") or []) if c]
    fallback = str(exit_def.get("fallback_next_chapter") or "").strip()
    if not fallback and candidates:
        fallback = candidates[0]
    if not fallback:
        raise RuntimeError("ai_choice exit missing fallback_next_chapter and candidates")

    if not candidates:
        logger.warning("[exits] ai_choice has empty candidates; using fallback=%s", fallback)
        return fallback

    guidance = str(exit_def.get("selection_guidance") or "根据玩家本章整体表现选择最合理的下一章。")
    flag_text = "、".join(f"{k}={v}" for k, v in (flags or {}).items()) or "（无）"
    stats_text = "、".join(f"{k}={v}" for k, v in (stats or {}).items()) or "（无）"

    system = (
        "你是互动小说的剧情调度器。你只能从给定候选章节 id 中选择一个作为下一章。"
        "输出严格 JSON：{\"next_chapter\": \"候选id之一\"}。不要输出其它文字。"
    )
    user = (
        f"【选择指引】\n{guidance}\n\n"
        f"【本章摘要】\n{chapter_summary or '（无）'}\n\n"
        f"【当前数值】\n{stats_text}\n\n"
        f"【已有剧情事实(flags)】\n{flag_text}\n\n"
        f"【候选章节】\n{', '.join(candidates)}\n"
    )

    try:
        result = llm_client.chat_json(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            config,
            fallback={"next_chapter": fallback},
        )
        picked = _extract_chapter_id(result, candidates)
        if picked:
            logger.info("[exits] ai_choice selected %s", picked)
            return picked
        logger.warning(
            "[exits] ai_choice parse invalid or out of pool (%s); fallback=%s",
            result,
            fallback,
        )
    except Exception as exc:
        logger.warning("[exits] ai_choice LLM failed (%s); fallback=%s", type(exc).__name__, fallback)

    return fallback


def resolve_next_chapter(
    exits: list[dict[str, Any]],
    *,
    stats: dict[str, int],
    flags: dict[str, Any],
    chapter_summary: str,
    config: LLMConfig,
) -> str | None:
    """hard_condition first, then ai_choice. None means work completed (no exits)."""
    if not exits:
        return None

    hard_hit = evaluate_hard_exits(exits, stats, flags)
    if hard_hit:
        return hard_hit

    for exit_def in exits:
        if exit_def.get("type") != "ai_choice":
            continue
        return resolve_ai_choice(
            exit_def,
            chapter_summary=chapter_summary,
            stats=stats,
            flags=flags,
            config=config,
        )

    # Exits exist but none matched / no ai_choice → treat as terminal.
    logger.info("[exits] no matching exit; treating chapter as work endpoint")
    return None
