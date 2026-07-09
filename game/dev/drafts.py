"""Server-side draft storage for dev editor (scripts + LLM prompts)."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from game.prompts import manager as prompt_manager

logger = logging.getLogger(__name__)

DRAFTS_ROOT = Path(__file__).resolve().parent.parent.parent / "dev_drafts"
SCRIPT_DRAFTS_DIR = DRAFTS_ROOT / "scripts"
PROMPT_DRAFTS_DIR = DRAFTS_ROOT / "prompts"

PROMPT_TEMPLATE_KEYS = [
    "director/system.txt",
    "director/user.txt",
    "roleplay/system.txt",
    "roleplay/user.txt",
]


def _ensure_dirs() -> None:
    SCRIPT_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    PROMPT_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)


# ── Script drafts ─────────────────────────────────────────────────────────────

def script_draft_path(script_id: str) -> Path:
    return SCRIPT_DRAFTS_DIR / f"{script_id}.json"


def has_script_draft(script_id: str) -> bool:
    return script_draft_path(script_id).is_file()


def load_script_draft(script_id: str) -> dict[str, Any] | None:
    path = script_draft_path(script_id)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_script_draft(script: dict[str, Any]) -> None:
    _ensure_dirs()
    script_id = script.get("id")
    if not script_id:
        raise ValueError("Script must have an id field")
    path = script_draft_path(str(script_id))
    path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("[dev_drafts] saved script draft %s", script_id)


def delete_script_draft(script_id: str) -> None:
    path = script_draft_path(script_id)
    if path.is_file():
        path.unlink()


def list_script_draft_ids() -> list[str]:
    _ensure_dirs()
    return sorted(p.stem for p in SCRIPT_DRAFTS_DIR.glob("*.json"))


# ── Prompt drafts ─────────────────────────────────────────────────────────────

def _prompt_draft_path(key: str) -> Path:
    return PROMPT_DRAFTS_DIR / key


def load_production_prompts() -> dict[str, str]:
    return {key: prompt_manager.load_template(key) for key in PROMPT_TEMPLATE_KEYS}


def has_prompt_drafts() -> bool:
    _ensure_dirs()
    return any(_prompt_draft_path(key).is_file() for key in PROMPT_TEMPLATE_KEYS)


def load_prompt_drafts() -> dict[str, str] | None:
    """Return saved prompt drafts only (None if no draft files exist)."""
    if not has_prompt_drafts():
        return None
    drafts: dict[str, str] = {}
    for key in PROMPT_TEMPLATE_KEYS:
        path = _prompt_draft_path(key)
        if path.is_file():
            drafts[key] = path.read_text(encoding="utf-8")
    return drafts or None


def load_effective_prompt_overrides() -> dict[str, str] | None:
    """Draft prompts merged over production; None if identical to production."""
    production = load_production_prompts()
    drafts = load_prompt_drafts()
    if not drafts:
        return None
    merged = dict(production)
    changed = False
    for key, content in drafts.items():
        if merged.get(key) != content:
            changed = True
        merged[key] = content
    return merged if changed else None


def save_prompt_drafts(prompts: dict[str, str]) -> None:
    _ensure_dirs()
    for key in PROMPT_TEMPLATE_KEYS:
        if key not in prompts:
            continue
        path = _prompt_draft_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(prompts[key], encoding="utf-8")
    logger.info("[dev_drafts] saved prompt drafts")


def delete_prompt_drafts() -> None:
    if PROMPT_DRAFTS_DIR.is_dir():
        shutil.rmtree(PROMPT_DRAFTS_DIR)
    PROMPT_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)


def publish_prompt_drafts() -> None:
    drafts = load_prompt_drafts()
    if not drafts:
        raise ValueError("没有可发布的 Prompt 草稿")
    production_dir = prompt_manager.PROMPTS_DIR
    for key, content in drafts.items():
        target = production_dir / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    delete_prompt_drafts()
    logger.info("[dev_drafts] published prompt drafts to production")


def resolve_simulate_script(
    script_id: str,
    editor_script: dict[str, Any] | None,
    prefer_saved_draft: bool,
) -> dict[str, Any]:
    if prefer_saved_draft:
        saved = load_script_draft(script_id)
        if saved:
            return saved
    if editor_script:
        return editor_script
    raise ValueError("没有可用的剧本草稿，请先在编辑器中保存草稿")


def resolve_simulate_prompts(
    editor_prompts: dict[str, str] | None,
    prefer_saved_draft: bool,
) -> dict[str, str] | None:
    if prefer_saved_draft:
        saved = load_effective_prompt_overrides()
        if saved:
            return saved
    if editor_prompts:
        production = load_production_prompts()
        if any(editor_prompts.get(k, production.get(k)) != production.get(k) for k in PROMPT_TEMPLATE_KEYS):
            return {key: editor_prompts.get(key, production[key]) for key in PROMPT_TEMPLATE_KEYS}
    return None
