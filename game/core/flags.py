"""Flag helpers for long-form memory (append-only in v2.0)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CHAPTER_SUMMARY = "这一章的故事告一段落。"


def normalize_wrap_up(raw: Any) -> dict[str, Any]:
    """Parse chapter_wrap_up with safe fallbacks."""
    if not isinstance(raw, dict):
        if raw is not None:
            logger.warning("[flags] chapter_wrap_up missing/invalid; using fallback")
        return {"summary": DEFAULT_CHAPTER_SUMMARY, "triggered_flags": []}

    summary = raw.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        logger.warning("[flags] chapter_wrap_up.summary missing; using fallback")
        summary = DEFAULT_CHAPTER_SUMMARY
    else:
        summary = summary.strip()

    triggered = raw.get("triggered_flags") or []
    if not isinstance(triggered, list):
        logger.warning("[flags] chapter_wrap_up.triggered_flags invalid; using []")
        triggered = []
    normalized = [str(item).strip() for item in triggered if str(item).strip()]
    return {"summary": summary, "triggered_flags": normalized}


def apply_triggered_flags(
    existing_flags: dict[str, Any],
    flags_write: list[Any],
    triggered_ids: list[str],
) -> dict[str, Any]:
    """Append-only flag writes. Existing keys are never overwritten."""
    flags = dict(existing_flags or {})
    triggered = set(triggered_ids or [])
    for item in flags_write or []:
        if isinstance(item, str):
            flag_id = item
            trigger = item
            value: Any = True
        elif isinstance(item, dict):
            flag_id = str(item.get("id") or item.get("flag") or "").strip()
            trigger = str(item.get("trigger") or flag_id).strip()
            value = item.get("value", True)
        else:
            continue
        if not flag_id or trigger not in triggered:
            continue
        if flag_id in flags:
            logger.info("[flags] skip existing flag %s (append-only)", flag_id)
            continue
        flags[flag_id] = value
        logger.info("[flags] wrote flag %s=%s", flag_id, value)
    return flags


def format_known_flags_summary(
    flags_read: list[Any],
    flags: dict[str, Any],
) -> str:
    """Natural-language lines for director prompt from flags_read declarations."""
    lines: list[str] = []
    for item in flags_read or []:
        if isinstance(item, str):
            flag_id = item
            label = item
            only_if_set = True
        elif isinstance(item, dict):
            flag_id = str(item.get("id") or item.get("flag") or "").strip()
            label = str(item.get("label") or item.get("summary") or flag_id).strip()
            only_if_set = bool(item.get("only_if_set", True))
        else:
            continue
        if not flag_id:
            continue
        present = flag_id in (flags or {}) and bool(flags.get(flag_id))
        if only_if_set and not present:
            continue
        if present:
            lines.append(f"玩家此前：{label}")
    if not lines:
        return "（暂无需要提醒的已知剧情事实）"
    return "\n".join(f"- {line}" for line in lines)


def format_chapter_summaries_recent(summaries: list[Any], *, limit: int = 3) -> str:
    recent = [str(s).strip() for s in (summaries or []) if str(s).strip()][-limit:]
    if not recent:
        return "（暂无前情摘要）"
    return "\n".join(f"- {item}" for item in recent)
