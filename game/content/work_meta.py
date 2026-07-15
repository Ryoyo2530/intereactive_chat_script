"""Helpers for long-form product metadata (endings, progress cards)."""

from __future__ import annotations

from typing import Any

from game.core import exits as exit_resolver


def is_terminal_chapter(chapter: dict[str, Any]) -> bool:
    raw = chapter.get("exits")
    if raw is None:
        return True
    if isinstance(raw, dict):
        return raw.get("type") == "terminal" or not raw.get("next_chapter")
    if isinstance(raw, list):
        normalized = exit_resolver.normalize_exits(raw)
        if not normalized:
            return True
        return all(e.get("type") == "terminal" for e in normalized)
    return True


def known_ending_chapter_ids(chapters: list[dict[str, Any]]) -> list[str]:
    return [str(ch["id"]) for ch in chapters if ch.get("id") and is_terminal_chapter(ch)]


def chapter_has_branching_exits(chapter: dict[str, Any] | None) -> bool:
    if not chapter:
        return False
    normalized = exit_resolver.normalize_exits(chapter.get("exits"))
    routable = [
        e for e in normalized
        if e.get("type") in ("hard_condition", "ai_choice") and (
            e.get("next_chapter") or e.get("candidates") or e.get("fallback_next_chapter")
        )
    ]
    if len(routable) >= 2:
        return True
    for e in routable:
        if e.get("type") == "ai_choice" and len(e.get("candidates") or []) >= 2:
            return True
    return False


def progress_status(
    *,
    save: dict[str, Any] | None,
    visited_count: int = 0,
) -> str:
    if not save:
        return "not_started"
    if save.get("game_over"):
        return "completed"
    if visited_count > 0 or save.get("current_turn", 0) > 0 or save.get("conversation_history"):
        return "in_progress"
    # Save exists at chapter entry with opening only
    return "in_progress"
