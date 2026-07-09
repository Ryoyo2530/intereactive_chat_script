"""Unified read/write cache for script JSON files.

All access to scripts/ goes through this module. engine.py and dev routes
both use these functions — never read the filesystem directly.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
PENDING_DIR = SCRIPTS_DIR / "pending_review"

_cache: dict[str, dict[str, Any]] | None = None  # {script_id: full_dict}


def _build_cache() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(SCRIPTS_DIR.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not data.get("id"):
                continue
            result[data["id"]] = data
        except Exception:
            continue
    return result


def invalidate_cache() -> None:
    global _cache
    _cache = None


def _get_cache() -> dict[str, dict[str, Any]]:
    global _cache
    if _cache is None:
        _cache = _build_cache()
    return _cache


def load_all() -> dict[str, dict[str, Any]]:
    """Return all scripts as {id: full_dict}. Cached."""
    return _get_cache()


def load_one(script_id: str) -> dict[str, Any]:
    """Return full script dict for given id. Raises FileNotFoundError if missing."""
    cache = _get_cache()
    if script_id not in cache:
        raise FileNotFoundError(f"Script not found: {script_id}")
    return cache[script_id]


def resolve_path(script_id: str) -> Path | None:
    """Find the file path of an existing script by id."""
    for path in SCRIPTS_DIR.rglob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("id") == script_id:
                return path
        except Exception:
            continue
    return None


def save(script: dict[str, Any]) -> None:
    """Write script to disk and invalidate cache.

    If the script already exists on disk, overwrites in place.
    New scripts go to scripts/pending_review/{id}.json.
    """
    script_id = script.get("id")
    if not script_id:
        raise ValueError("Script must have an 'id' field")

    existing = resolve_path(script_id)
    if existing:
        target = existing
    else:
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        target = PENDING_DIR / f"{script_id}.json"

    target.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("[script_repository] saved %s → %s", script_id, target)
    invalidate_cache()


def delete(script_id: str) -> None:
    """Delete script file and invalidate cache. Raises FileNotFoundError if missing."""
    path = resolve_path(script_id)
    if not path:
        raise FileNotFoundError(f"Script not found: {script_id}")
    path.unlink()
    logger.info("[script_repository] deleted %s", script_id)
    invalidate_cache()


def list_summary() -> list[dict[str, Any]]:
    """Return trimmed summary dicts suitable for the player-facing script list."""
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
        })
    return summaries
