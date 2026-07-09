from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from game.core import engine
from game.dev import auth as dev_auth
from game.dev import drafts as dev_drafts
from game.dev import prompt_preview

router = APIRouter()


class DevPromptPreviewRequest(BaseModel):
    script: dict[str, Any] | None = None
    script_id: str | None = None
    prompts: dict[str, str] | None = None
    prefer_saved_drafts: bool = False
    player_message: str = "（示例玩家发言，用于预览 Prompt 渲染效果）"


class DevPromptDraftRequest(BaseModel):
    prompts: dict[str, str]


@router.get("/api/dev/prompts", dependencies=[Depends(dev_auth.require_dev_auth)])
def dev_get_prompts():
    production = dev_drafts.load_production_prompts()
    drafts = dev_drafts.load_prompt_drafts()
    return {
        "production": production,
        "draft": drafts,
        "has_draft": dev_drafts.has_prompt_drafts(),
        "keys": dev_drafts.PROMPT_TEMPLATE_KEYS,
    }


@router.put("/api/dev/prompts/draft", dependencies=[Depends(dev_auth.require_dev_auth)])
def dev_save_prompt_draft(body: DevPromptDraftRequest):
    dev_drafts.save_prompt_drafts(body.prompts)
    return {"ok": True, "has_draft": True}


@router.post("/api/dev/prompts/publish", dependencies=[Depends(dev_auth.require_dev_auth)])
def dev_publish_prompts():
    try:
        dev_drafts.publish_prompt_drafts()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.delete("/api/dev/prompts/draft", dependencies=[Depends(dev_auth.require_dev_auth)])
def dev_delete_prompt_draft():
    dev_drafts.delete_prompt_drafts()
    return {"ok": True}


@router.post("/api/dev/prompts/preview", dependencies=[Depends(dev_auth.require_dev_auth)])
def dev_preview_prompts(body: DevPromptPreviewRequest):
    script = body.script
    if not script and body.script_id:
        try:
            script = engine.load_script(body.script_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Script not found")
        if body.prefer_saved_drafts:
            saved = dev_drafts.load_script_draft(body.script_id)
            if saved:
                script = saved
    if not script:
        raise HTTPException(status_code=400, detail="请提供 script 或 script_id")

    prompts = body.prompts
    if body.prefer_saved_drafts and not prompts:
        prompts = dev_drafts.load_effective_prompt_overrides()
    elif prompts:
        production = dev_drafts.load_production_prompts()
        prompts = {key: prompts.get(key, production[key]) for key in dev_drafts.PROMPT_TEMPLATE_KEYS}

    return prompt_preview.preview_prompts(script, prompts, body.player_message)
