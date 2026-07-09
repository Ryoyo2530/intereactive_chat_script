from fastapi import APIRouter, Depends, HTTPException

from game.content import script_repository
from game.dev import auth as dev_auth
from game.dev import drafts as dev_drafts

router = APIRouter()


@router.get("/api/dev/drafts/scripts/{script_id}", dependencies=[Depends(dev_auth.require_dev_auth)])
def dev_get_script_draft(script_id: str):
    draft = dev_drafts.load_script_draft(script_id)
    if not draft:
        raise HTTPException(status_code=404, detail="No script draft")
    return {"draft": draft, "has_draft": True}


@router.put("/api/dev/drafts/scripts/{script_id}", dependencies=[Depends(dev_auth.require_dev_auth)])
def dev_save_script_draft(script_id: str, body: dict):
    if body.get("id") != script_id:
        raise HTTPException(status_code=400, detail="Body id must match URL id")
    dev_drafts.save_script_draft(body)
    return {"ok": True, "has_draft": True}


@router.delete("/api/dev/drafts/scripts/{script_id}", dependencies=[Depends(dev_auth.require_dev_auth)])
def dev_delete_script_draft(script_id: str):
    dev_drafts.delete_script_draft(script_id)
    return {"ok": True}


@router.get("/api/dev/drafts/scripts/{script_id}/compare", dependencies=[Depends(dev_auth.require_dev_auth)])
def dev_compare_script_draft(script_id: str):
    try:
        production = script_repository.load_one(script_id)
    except FileNotFoundError:
        production = None
    draft = dev_drafts.load_script_draft(script_id)
    return {
        "production": production,
        "draft": draft,
        "has_draft": draft is not None,
        "has_production": production is not None,
    }
