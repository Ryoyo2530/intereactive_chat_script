"""CRUD for works + chapters tables in Supabase."""

from __future__ import annotations

import logging
from typing import Any

from game.content.work_mapper import (
    chapter_id_for_work,
    long_form_document_to_rows,
    script_to_work_chapter,
    work_chapter_to_script,
    work_to_summary,
)
from game.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_WORK_COLUMNS = (
    "id, type, title, origin_tag, theme_tags, teaser, player_role_hint, "
    "estimated_turns_hint, stats_schema, chapter_ids, entry_chapter_id, status, "
    "created_at, updated_at"
)
_CHAPTER_COLUMNS = (
    "id, work_id, title, background, ai_character, player_character, opening_line, "
    "max_turns, key_points, pitfalls, flags_read, flags_write, exits, extras, "
    "created_at, updated_at"
)


def _raise_from_response(action: str, response: Any) -> None:
    error = getattr(response, "error", None)
    if error:
        raise RuntimeError(f"Supabase {action} failed: {error}")


def list_works(*, status: str | None = "published") -> list[dict[str, Any]]:
    """Return work rows, optionally filtered by status."""
    client = get_supabase()
    query = client.table("works").select(_WORK_COLUMNS).order("id")
    if status:
        query = query.eq("status", status)
    response = query.execute()
    _raise_from_response("list works", response)
    return list(response.data or [])


def get_work(work_id: str) -> dict[str, Any] | None:
    client = get_supabase()
    response = (
        client.table("works")
        .select(_WORK_COLUMNS)
        .eq("id", work_id)
        .limit(1)
        .execute()
    )
    _raise_from_response(f"get work {work_id}", response)
    rows = response.data or []
    return rows[0] if rows else None


def get_chapter(chapter_id: str) -> dict[str, Any] | None:
    client = get_supabase()
    response = (
        client.table("chapters")
        .select(_CHAPTER_COLUMNS)
        .eq("id", chapter_id)
        .limit(1)
        .execute()
    )
    _raise_from_response(f"get chapter {chapter_id}", response)
    rows = response.data or []
    return rows[0] if rows else None


def get_chapters_for_work(work_id: str) -> list[dict[str, Any]]:
    client = get_supabase()
    response = (
        client.table("chapters")
        .select(_CHAPTER_COLUMNS)
        .eq("work_id", work_id)
        .execute()
    )
    _raise_from_response(f"list chapters for {work_id}", response)
    return list(response.data or [])


def load_script(work_id: str, chapter_id: str | None = None) -> dict[str, Any]:
    """Load work + chapter and assemble a playable flat script dict."""
    work = get_work(work_id)
    if not work:
        raise FileNotFoundError(f"Script not found: {work_id}")
    target_id = chapter_id or work.get("entry_chapter_id") or chapter_id_for_work(work_id)
    chapter = get_chapter(target_id)
    if not chapter:
        chapters = get_chapters_for_work(work_id)
        if not chapters:
            raise FileNotFoundError(f"Script chapter not found for work: {work_id}")
        chapter = chapters[0]
    return work_chapter_to_script(work, chapter)


def save_long_form_document(data: dict[str, Any], *, status: str = "published") -> None:
    """Upsert a multi-chapter long_form document into works + chapters."""
    work, chapters = long_form_document_to_rows(data, status=status)
    # Strip file-only helper keys before upsert.
    work_row = {k: v for k, v in work.items() if not k.startswith("_")}
    client = get_supabase()
    work_resp = client.table("works").upsert(work_row, on_conflict="id").execute()
    _raise_from_response(f"upsert work {work_row['id']}", work_resp)
    for chapter in chapters:
        chapter_resp = client.table("chapters").upsert(chapter, on_conflict="id").execute()
        _raise_from_response(f"upsert chapter {chapter['id']}", chapter_resp)
    logger.info(
        "[work_repository] saved long_form work=%s chapters=%s",
        work_row["id"],
        len(chapters),
    )


def load_all_scripts(*, status: str | None = None) -> dict[str, dict[str, Any]]:
    """Load all works (any status by default for dev) as flat script dicts."""
    works = list_works(status=status)
    if not works:
        return {}

    client = get_supabase()
    work_ids = [w["id"] for w in works]
    # PostgREST `in` filter; batch if the list grows large later.
    response = (
        client.table("chapters")
        .select(_CHAPTER_COLUMNS)
        .in_("work_id", work_ids)
        .execute()
    )
    _raise_from_response("list chapters", response)
    chapters_by_work: dict[str, list[dict[str, Any]]] = {}
    for ch in response.data or []:
        chapters_by_work.setdefault(ch["work_id"], []).append(ch)

    result: dict[str, dict[str, Any]] = {}
    for work in works:
        chapters = chapters_by_work.get(work["id"], [])
        entry_id = work.get("entry_chapter_id")
        chapter = next((c for c in chapters if c["id"] == entry_id), None)
        if chapter is None and chapters:
            chapter = chapters[0]
        if chapter is None:
            logger.warning("[work_repository] work %s has no chapters; skipping", work["id"])
            continue
        result[work["id"]] = work_chapter_to_script(work, chapter)
    return result


def list_script_summaries() -> list[dict[str, Any]]:
    """Published works only — player script picker."""
    return [work_to_summary(w) for w in list_works(status="published")]


def save_script(script: dict[str, Any], *, status: str = "published") -> None:
    """Upsert work + chapter from a flat script dict (short_form)."""
    work, chapter = script_to_work_chapter(script, work_type="short_form", status=status)
    client = get_supabase()

    work_resp = client.table("works").upsert(work, on_conflict="id").execute()
    _raise_from_response(f"upsert work {work['id']}", work_resp)

    chapter_resp = client.table("chapters").upsert(chapter, on_conflict="id").execute()
    _raise_from_response(f"upsert chapter {chapter['id']}", chapter_resp)

    logger.info("[work_repository] saved work=%s chapter=%s", work["id"], chapter["id"])


def delete_script(work_id: str) -> None:
    """Delete a work (chapters cascade). Raises FileNotFoundError if missing."""
    if not get_work(work_id):
        raise FileNotFoundError(f"Script not found: {work_id}")
    client = get_supabase()
    response = client.table("works").delete().eq("id", work_id).execute()
    _raise_from_response(f"delete work {work_id}", response)
    logger.info("[work_repository] deleted work %s", work_id)
