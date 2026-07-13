"""Unified read/write cache for scripts (works + chapters).

Public API is unchanged from v1 so engine / validator / routers stay stable.
Persistence backend is selected via CONTENT_BACKEND:
  - supabase (default when SUPABASE_URL + SUPABASE_KEY are set)
  - file (local scripts/*.json — rollback / offline dev)
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from game.content.work_mapper import (
    is_long_form_document,
    long_form_document_to_rows,
    work_chapter_to_script,
)
from game.settings import get_settings

logger = logging.getLogger(__name__)

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
PENDING_DIR = SCRIPTS_DIR / "pending_review"

_cache: dict[str, dict[str, Any]] | None = None  # {work_id: playable entry script}
# File-backend long_form docs keyed by work id (for chapter switching without DB).
_file_long_forms: dict[str, dict[str, Any]] = {}


def _backend() -> str:
    settings = get_settings()
    explicit = (settings.content_backend or "").strip().lower()
    if explicit in ("file", "supabase"):
        return explicit
    if settings.supabase_url.strip() and settings.supabase_key.strip():
        return "supabase"
    return "file"


# ---------------------------------------------------------------------------
# File backend
# ---------------------------------------------------------------------------

def _build_file_cache() -> dict[str, dict[str, Any]]:
    global _file_long_forms
    result: dict[str, dict[str, Any]] = {}
    _file_long_forms = {}
    for path in sorted(SCRIPTS_DIR.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not data.get("id"):
                continue
            if is_long_form_document(data):
                work, chapters = long_form_document_to_rows(data)
                _file_long_forms[work["id"]] = {
                    "work": {k: v for k, v in work.items() if not k.startswith("_")},
                    "chapters": {c["id"]: c for c in chapters},
                    "document": data,
                }
                entry_id = work["entry_chapter_id"]
                entry = next(c for c in chapters if c["id"] == entry_id)
                result[work["id"]] = work_chapter_to_script(work, entry)
            else:
                # short_form flat script — annotate work_type for engine gating
                data = dict(data)
                data.setdefault("work_type", "short_form")
                data.setdefault("chapter_id", f"{data['id']}_main")
                data.setdefault("flags_read", [])
                data.setdefault("flags_write", [])
                data.setdefault("exits", {
                    "type": "terminal",
                    "win_condition": data.get("win_condition", ""),
                    "lose_condition": data.get("lose_condition", ""),
                })
                result[data["id"]] = data
        except Exception as exc:
            logger.warning("[script_repository] skip %s: %s", path, exc)
            continue
    return result


def resolve_path(script_id: str) -> Path | None:
    """Find the file path of an existing script by id (file backend only)."""
    for path in SCRIPTS_DIR.rglob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("id") == script_id:
                return path
        except Exception:
            continue
    return None


def _atomic_write(target: Path, text: str) -> None:
    """Write via temp file + os.replace to avoid truncated JSON on crash."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _file_save(script: dict[str, Any]) -> None:
    script_id = script.get("id")
    if not script_id:
        raise ValueError("Script must have an 'id' field")
    if script.get("work_type") == "long_form" or is_long_form_document(script):
        raise ValueError("Use dedicated long_form document save for multi-chapter works")

    existing = resolve_path(script_id)
    if existing:
        target = existing
    else:
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        target = PENDING_DIR / f"{script_id}.json"

    _atomic_write(target, json.dumps(script, ensure_ascii=False, indent=2))
    logger.info("[script_repository] saved %s → %s (file)", script_id, target)


def _file_delete(script_id: str) -> None:
    path = resolve_path(script_id)
    if not path:
        raise FileNotFoundError(f"Script not found: {script_id}")
    path.unlink()
    logger.info("[script_repository] deleted %s (file)", script_id)


# ---------------------------------------------------------------------------
# Cache + public API
# ---------------------------------------------------------------------------

def invalidate_cache() -> None:
    global _cache, _file_long_forms
    _cache = None
    _file_long_forms = {}


def _build_cache() -> dict[str, dict[str, Any]]:
    backend = _backend()
    if backend == "supabase":
        from game.content import work_repository

        try:
            return work_repository.load_all_scripts(status=None)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load scripts from Supabase: {exc}. "
                "Check SUPABASE_URL / SUPABASE_KEY and that migrations have been applied."
            ) from exc
    return _build_file_cache()


def _get_cache() -> dict[str, dict[str, Any]]:
    global _cache
    if _cache is None:
        backend = _backend()
        logger.info("[script_repository] loading cache via backend=%s", backend)
        _cache = _build_cache()
    return _cache


def load_all() -> dict[str, dict[str, Any]]:
    """Return all scripts as {id: full_dict}. Cached."""
    return _get_cache()


def load_one(script_id: str) -> dict[str, Any]:
    """Return playable script for work id (entry chapter for long_form)."""
    cache = _get_cache()
    if script_id not in cache:
        raise FileNotFoundError(f"Script not found: {script_id}")
    return cache[script_id]


def load_chapter(work_id: str, chapter_id: str) -> dict[str, Any]:
    """Load a specific chapter as a playable script dict."""
    backend = _backend()
    if backend == "supabase":
        from game.content import work_repository

        return work_repository.load_script(work_id, chapter_id=chapter_id)

    # Ensure file cache (and _file_long_forms) is warm.
    _get_cache()
    pack = _file_long_forms.get(work_id)
    if not pack:
        # short_form: only one chapter
        script = load_one(work_id)
        if script.get("chapter_id") == chapter_id or chapter_id.endswith("_main"):
            return script
        raise FileNotFoundError(f"Chapter not found: {work_id}/{chapter_id}")
    chapter = pack["chapters"].get(chapter_id)
    if not chapter:
        raise FileNotFoundError(f"Chapter not found: {work_id}/{chapter_id}")
    return work_chapter_to_script(pack["work"], chapter)


def save(script: dict[str, Any]) -> None:
    """Persist short_form script and invalidate cache."""
    script_id = script.get("id")
    if not script_id:
        raise ValueError("Script must have an 'id' field")

    backend = _backend()
    if backend == "supabase":
        from game.content import work_repository

        try:
            if is_long_form_document(script):
                work_repository.save_long_form_document(script, status="published")
            else:
                work_repository.save_script(script, status="published")
        except Exception as exc:
            raise RuntimeError(
                f"Failed to save script '{script_id}' to Supabase: {exc}"
            ) from exc
        logger.info("[script_repository] saved %s (supabase)", script_id)
    else:
        _file_save(script)

    invalidate_cache()


def delete(script_id: str) -> None:
    """Delete script and invalidate cache. Raises FileNotFoundError if missing."""
    backend = _backend()
    if backend == "supabase":
        from game.content import work_repository

        try:
            work_repository.delete_script(script_id)
        except FileNotFoundError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Failed to delete script '{script_id}' from Supabase: {exc}"
            ) from exc
    else:
        _file_delete(script_id)

    invalidate_cache()


def list_summary() -> list[dict[str, Any]]:
    """Return trimmed summary dicts suitable for the player-facing script list."""
    backend = _backend()
    if backend == "supabase":
        from game.content import work_repository

        try:
            return work_repository.list_script_summaries()
        except Exception as exc:
            raise RuntimeError(
                f"Failed to list scripts from Supabase: {exc}. "
                "Check SUPABASE_URL / SUPABASE_KEY and that migrations have been applied."
            ) from exc

    summaries = []
    for data in _get_cache().values():
        summaries.append({
            "id": data["id"],
            "title": data["title"],
            "origin_tag": data.get("origin_tag", ""),
            "theme_tags": data.get("theme_tags", []),
            "teaser": data.get("teaser", data.get("objective", "")),
            "player_role_hint": data.get("player_role_hint", ""),
            "estimated_turns_hint": data.get("estimated_turns_hint", ""),
            "work_type": data.get("work_type", "short_form"),
        })
    return summaries
