"""Convert between v1 flat script JSON and v2 work + chapter rows."""

from __future__ import annotations

from typing import Any

# Flat-script keys that live on the work row (not chapter content).
_WORK_KEYS = frozenset({
    "id",
    "title",
    "origin_tag",
    "theme_tags",
    "teaser",
    "player_role_hint",
    "estimated_turns_hint",
    "stats",
})

# Flat-script keys that map to explicit chapter columns.
_CHAPTER_COLUMN_KEYS = frozenset({
    "background",
    "ai_character",
    "player_character",
    "opening_line",
    "max_turns",
    "key_points",
    "pitfalls",
    "win_condition",
    "lose_condition",
})

# Known extras stored in chapters.extras (round-trip fidelity for v1 fields).
_EXTRAS_KEYS = frozenset({
    "objective",
    "briefing",
    "echo_phrases",
    "tone_preset",
    "chapter_title",
    "max_hints",
    "ending_titles",
    "ending_lines",
    "ending_texts",
})


def chapter_id_for_work(work_id: str) -> str:
    """Stable chapter id for short_form works (single chapter)."""
    return f"{work_id}_main"


def script_to_work_chapter(
    script: dict[str, Any],
    *,
    work_type: str = "short_form",
    status: str = "published",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split a flat v1 script dict into (work_row, chapter_row)."""
    work_id = script.get("id")
    if not work_id:
        raise ValueError("Script must have an 'id' field")

    chapter_id = chapter_id_for_work(work_id)
    exits = {
        "type": "terminal",
        "win_condition": script.get("win_condition", ""),
        "lose_condition": script.get("lose_condition", ""),
    }

    extras: dict[str, Any] = {}
    for key in _EXTRAS_KEYS:
        if key in script:
            extras[key] = script[key]
    # Preserve any unknown top-level keys so migration is lossless.
    known = _WORK_KEYS | _CHAPTER_COLUMN_KEYS | _EXTRAS_KEYS | {"id"}
    for key, value in script.items():
        if key not in known:
            extras[key] = value

    work: dict[str, Any] = {
        "id": work_id,
        "type": work_type,
        "title": script.get("title", ""),
        "origin_tag": script.get("origin_tag", ""),
        "theme_tags": script.get("theme_tags", []),
        "teaser": script.get("teaser", script.get("objective", "")),
        "player_role_hint": script.get("player_role_hint", ""),
        "estimated_turns_hint": script.get("estimated_turns_hint", ""),
        "stats_schema": script.get("stats", {}),
        "chapter_ids": [chapter_id],
        "entry_chapter_id": chapter_id,
        "status": status,
    }

    chapter: dict[str, Any] = {
        "id": chapter_id,
        "work_id": work_id,
        "title": script.get("chapter_title") or script.get("title", ""),
        "background": script.get("background", ""),
        "ai_character": script.get("ai_character", {}),
        "player_character": script.get("player_character", {}),
        "opening_line": script.get("opening_line", ""),
        "max_turns": int(script.get("max_turns") or 12),
        "key_points": script.get("key_points", []),
        "pitfalls": script.get("pitfalls", []),
        "flags_read": [],
        "flags_write": [],
        "exits": exits,
        "extras": extras,
    }
    return work, chapter


def _terminal_conditions(chapter: dict[str, Any]) -> tuple[str, str]:
    exits = chapter.get("exits")
    terminal: dict[str, Any] = {}
    if isinstance(exits, list):
        terminal = next(
            (e for e in exits if isinstance(e, dict) and e.get("type") == "terminal"),
            {},
        )
    elif isinstance(exits, dict) and exits.get("type") == "terminal":
        terminal = exits

    extras = chapter.get("extras") if isinstance(chapter.get("extras"), dict) else {}
    win = (
        terminal.get("win_condition")
        or chapter.get("win_condition")
        or extras.get("win_condition")
        or ""
    )
    lose = (
        terminal.get("lose_condition")
        or chapter.get("lose_condition")
        or extras.get("lose_condition")
        or ""
    )
    return str(win), str(lose)


def work_chapter_to_script(work: dict[str, Any], chapter: dict[str, Any]) -> dict[str, Any]:
    """Assemble a playable flat script dict from work + chapter rows."""
    win_condition, lose_condition = _terminal_conditions(chapter)

    extras = chapter.get("extras") or {}
    if not isinstance(extras, dict):
        extras = {}

    script: dict[str, Any] = {
        "id": work["id"],
        "title": work.get("title", ""),
        "origin_tag": work.get("origin_tag", ""),
        "theme_tags": work.get("theme_tags", []),
        "teaser": work.get("teaser", ""),
        "player_role_hint": work.get("player_role_hint", ""),
        "estimated_turns_hint": work.get("estimated_turns_hint", ""),
        "background": chapter.get("background", ""),
        "ai_character": chapter.get("ai_character", {}),
        "player_character": chapter.get("player_character", {}),
        "stats": work.get("stats_schema") or work.get("stats") or {},
        "key_points": chapter.get("key_points", []),
        "pitfalls": chapter.get("pitfalls", []),
        "win_condition": win_condition,
        "lose_condition": lose_condition,
        "max_turns": chapter.get("max_turns", 12),
        "opening_line": chapter.get("opening_line", ""),
        # Long-form metadata (harmless for short_form)
        "work_type": work.get("type", "short_form"),
        "chapter_id": chapter.get("id"),
        "chapter_title": chapter.get("title") or extras.get("chapter_title") or work.get("title", ""),
        "flags_read": chapter.get("flags_read") or [],
        "flags_write": chapter.get("flags_write") or [],
        "exits": chapter.get("exits") if chapter.get("exits") is not None else [],
    }
    for key, value in extras.items():
        if key in ("win_condition", "lose_condition"):
            continue
        if key in _EXTRAS_KEYS or key not in script:
            script[key] = value
    if not script.get("objective"):
        script["objective"] = extras.get("objective") or work.get("teaser") or ""
    return script


def work_to_summary(work: dict[str, Any]) -> dict[str, Any]:
    """Player-facing list card fields."""
    return {
        "id": work["id"],
        "title": work.get("title", ""),
        "origin_tag": work.get("origin_tag", ""),
        "theme_tags": work.get("theme_tags", []),
        "teaser": work.get("teaser", ""),
        "player_role_hint": work.get("player_role_hint", ""),
        "estimated_turns_hint": work.get("estimated_turns_hint", ""),
        "work_type": work.get("type", "short_form"),
    }


def is_long_form_document(data: dict[str, Any]) -> bool:
    return data.get("type") == "long_form" and isinstance(data.get("chapters"), list)


def long_form_document_to_rows(
    data: dict[str, Any],
    *,
    status: str = "published",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Split a long_form file/document into work row + chapter rows."""
    work_id = data.get("id")
    if not work_id:
        raise ValueError("long_form document must have an id")
    chapters_in = data.get("chapters") or []
    if not chapters_in:
        raise ValueError(f"long_form document {work_id} has no chapters")

    chapter_ids: list[str] = []
    chapter_rows: list[dict[str, Any]] = []
    for raw in chapters_in:
        if not isinstance(raw, dict) or not raw.get("id"):
            raise ValueError(f"Invalid chapter in long_form document {work_id}")
        chapter_ids.append(str(raw["id"]))
        extras = {k: v for k, v in raw.items() if k in _EXTRAS_KEYS}
        # Persist chapter-level win/lose into extras when not using terminal exit.
        if "win_condition" in raw:
            extras["win_condition"] = raw["win_condition"]
        if "lose_condition" in raw:
            extras["lose_condition"] = raw["lose_condition"]
        for key, value in raw.items():
            if key in {
                "id", "title", "background", "ai_character", "player_character",
                "opening_line", "max_turns", "key_points", "pitfalls",
                "flags_read", "flags_write", "exits",
                "win_condition", "lose_condition",
            } | _EXTRAS_KEYS:
                continue
            extras[key] = value

        chapter_rows.append({
            "id": str(raw["id"]),
            "work_id": work_id,
            "title": raw.get("title") or data.get("title") or "",
            "background": raw.get("background", ""),
            "ai_character": raw.get("ai_character") or data.get("ai_character") or {},
            "player_character": raw.get("player_character") or data.get("player_character") or {},
            "opening_line": raw.get("opening_line", ""),
            "max_turns": int(raw.get("max_turns") or 8),
            "key_points": raw.get("key_points") or [],
            "pitfalls": raw.get("pitfalls") or [],
            "flags_read": raw.get("flags_read") or [],
            "flags_write": raw.get("flags_write") or [],
            "exits": raw.get("exits") if raw.get("exits") is not None else [],
            "extras": extras,
        })

    entry = data.get("entry_chapter_id") or chapter_ids[0]
    work = {
        "id": work_id,
        "type": "long_form",
        "title": data.get("title", ""),
        "origin_tag": data.get("origin_tag", ""),
        "theme_tags": data.get("theme_tags", []),
        "teaser": data.get("teaser", ""),
        "player_role_hint": data.get("player_role_hint", ""),
        "estimated_turns_hint": data.get("estimated_turns_hint", ""),
        "stats_schema": data.get("stats") or data.get("stats_schema") or {},
        "chapter_ids": chapter_ids,
        "entry_chapter_id": entry,
        "status": status,
        # Keep full document for file-backend chapter switching without DB.
        "_chapters": chapter_rows,
        "_document": data,
    }
    return work, chapter_rows
