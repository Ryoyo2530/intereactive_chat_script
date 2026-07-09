import io
import json
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from game.content import script_repository
from game.content import validator as script_validator
from game.dev import auth as dev_auth
from game.dev import drafts as dev_drafts

router = APIRouter()

dev_static_dir = Path(__file__).resolve().parent.parent / "static" / "dev"


class DevLoginRequest(BaseModel):
    password: str


@router.get("/dev")
async def serve_dev():
    return FileResponse(dev_static_dir / "index.html", headers={"Cache-Control": "no-store"})


@router.post("/api/dev/login")
def dev_login(body: DevLoginRequest):
    if not dev_auth.is_enabled():
        raise HTTPException(status_code=403, detail="Dev mode not enabled (DEV_MODE_PASSWORD not set)")
    if not dev_auth.check_password(body.password):
        raise HTTPException(status_code=401, detail="密码错误")
    token = dev_auth.create_token()
    response = JSONResponse({"ok": True})
    response.set_cookie(
        "dev_token",
        token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=dev_auth.TOKEN_TTL_SECONDS,
    )
    return response


@router.get("/api/dev/scripts", dependencies=[Depends(dev_auth.require_dev_auth)])
def dev_list_scripts():
    return {"scripts": list(script_repository.load_all().values())}


@router.get("/api/dev/scripts/{script_id}", dependencies=[Depends(dev_auth.require_dev_auth)])
def dev_get_script(script_id: str):
    try:
        return script_repository.load_one(script_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Script not found")


@router.post("/api/dev/scripts", dependencies=[Depends(dev_auth.require_dev_auth)])
def dev_create_script(body: dict):
    script_id = body.get("id", "")
    if not script_id:
        raise HTTPException(status_code=400, detail="Script must have an id field")
    existing = script_repository.load_all()
    if script_id in existing:
        raise HTTPException(status_code=409, detail=f"Script id already exists: {script_id}")
    result = script_validator.validate(body)
    if result["errors"]:
        raise HTTPException(status_code=422, detail={"errors": result["errors"], "warnings": result["warnings"]})
    script_repository.save(body)
    dev_drafts.delete_script_draft(script_id)
    return {"ok": True, "id": script_id, "warnings": result["warnings"]}


@router.post("/api/dev/scripts/{script_id}/validate", dependencies=[Depends(dev_auth.require_dev_auth)])
def dev_validate_script(script_id: str, body: dict):
    return script_validator.validate(body)


@router.put("/api/dev/scripts/{script_id}", dependencies=[Depends(dev_auth.require_dev_auth)])
def dev_save_script(script_id: str, body: dict):
    if body.get("id") != script_id:
        raise HTTPException(status_code=400, detail="Body id must match URL id")
    result = script_validator.validate(body)
    if result["errors"]:
        raise HTTPException(status_code=422, detail={"errors": result["errors"], "warnings": result["warnings"]})
    script_repository.save(body)
    dev_drafts.delete_script_draft(script_id)
    return {"ok": True, "warnings": result["warnings"]}


@router.delete("/api/dev/scripts/{script_id}", dependencies=[Depends(dev_auth.require_dev_auth)])
def dev_delete_script(script_id: str):
    try:
        script_repository.delete(script_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Script not found")
    dev_drafts.delete_script_draft(script_id)
    return {"ok": True}


@router.get("/api/dev/scripts/{script_id}/export", dependencies=[Depends(dev_auth.require_dev_auth)])
def dev_export_script(script_id: str):
    try:
        script = script_repository.load_one(script_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Script not found")
    content = json.dumps(script, ensure_ascii=False, indent=2).encode("utf-8")
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{script_id}.json"'},
    )


@router.get("/api/dev/export", dependencies=[Depends(dev_auth.require_dev_auth)])
def dev_export_all():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for sid, script in script_repository.load_all().items():
            zf.writestr(f"{sid}.json", json.dumps(script, ensure_ascii=False, indent=2))
    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="scripts.zip"'},
    )


@router.post("/api/dev/scripts/import", dependencies=[Depends(dev_auth.require_dev_auth)])
async def dev_import_script(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="无法解析 JSON 文件")
    if not data.get("id"):
        raise HTTPException(status_code=400, detail="Script must have an id field")
    result = script_validator.validate(data)
    if result["errors"]:
        raise HTTPException(status_code=422, detail={"errors": result["errors"], "warnings": result["warnings"]})
    existing = script_repository.load_all()
    if data["id"] in existing:
        return JSONResponse({"conflict": True, "existing_id": data["id"], "warnings": result["warnings"]})
    script_repository.save(data)
    return {"ok": True, "id": data["id"], "warnings": result["warnings"]}


@router.post("/api/dev/scripts/import/overwrite", dependencies=[Depends(dev_auth.require_dev_auth)])
async def dev_import_overwrite(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="无法解析 JSON 文件")
    if not data.get("id"):
        raise HTTPException(status_code=400, detail="Script must have an id field")
    result = script_validator.validate(data)
    if result["errors"]:
        raise HTTPException(status_code=422, detail={"errors": result["errors"], "warnings": result["warnings"]})
    script_repository.save(data)
    return {"ok": True, "id": data["id"], "warnings": result["warnings"]}
