import io
import json
import logging
import zipfile
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Cookie, Depends, FastAPI, HTTPException, UploadFile, File
from fastapi.responses import Response, StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from game import engine
from game import llm_client
from game import llm_config
from game import dev_auth
from game import dev_drafts
from game import path_calculator
from game import prompt_preview
from game import script_repository
from game import validator as script_validator

load_dotenv(Path(__file__).resolve().parent / ".env")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="入戏")

FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" rx="8" fill="#c97862"/>'
    '<text x="16" y="22" text-anchor="middle" font-size="16" fill="white">戏</text>'
    '</svg>'
)


class LLMConfigRequest(BaseModel):
    provider: str = "doubao"
    api_base: str = ""
    api_key: str = ""
    model: str = ""


class StartSessionRequest(BaseModel):
    script_id: str
    llm_config: LLMConfigRequest | None = None
    ai_name: str | None = None
    ai_persona: str | None = None


class MessageRequest(BaseModel):
    session_id: str
    message: str


@app.get("/favicon.ico")
def favicon():
    return Response(content=FAVICON_SVG, media_type="image/svg+xml")


@app.get("/api/config/llm")
def get_llm_config_status():
    return llm_config.get_status()


@app.post("/api/config/llm/test")
def test_llm_config(body: LLMConfigRequest):
    try:
        cfg = llm_config.resolve_config(body.model_dump())
        result = llm_client.test_connection(cfg)
        return {"ok": True, **result, "model": cfg.model, "provider": cfg.provider}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"连接失败: {exc}")


@app.get("/api/scripts")
def get_scripts():
    return {"scripts": engine.list_scripts()}


@app.get("/api/scripts/{script_id}/detail")
def get_script_detail(script_id: str):
    try:
        script = engine.load_script(script_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Script not found")
    ai = script.get("ai_character", {})
    player = script.get("player_character", {})
    return {
        "id": script["id"],
        "title": script["title"],
        "origin_tag": script.get("origin_tag", ""),
        "briefing": script.get("briefing", script.get("teaser", "")),
        "objective": script.get("objective", ""),
        "ai_character": {
            "name": ai.get("name", ""),
            "intro": ai.get("intro", ""),
        },
        "player_character": {
            "name": player.get("name", ""),
            "persona": player.get("persona", ""),
        },
    }


@app.post("/api/session/start")
def start_session(body: StartSessionRequest):
    try:
        override = body.llm_config.model_dump() if body.llm_config else None
        return engine.start_game(
            body.script_id,
            llm_override=override,
            ai_name=body.ai_name,
            ai_persona=body.ai_persona,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Script not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/session/message")
def send_message(body: MessageRequest):
    try:
        return engine.process_message(body.session_id, body.message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/session/message/stream")
def send_message_stream(body: MessageRequest):
    try:
        def event_generator():
            for event in engine.process_message_stream(body.session_id, body.message):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


static_dir = Path(__file__).resolve().parent / "static"
dev_static_dir = static_dir / "dev"


# ── Dev auth ─────────────────────────────────────────────────────────────────

def require_dev_auth(dev_token: str | None = Cookie(default=None)):
    if not dev_auth.validate_token(dev_token):
        raise HTTPException(status_code=401, detail="未授权，请先登录开发者模式")


# ── Dev routes ────────────────────────────────────────────────────────────────

class DevLoginRequest(BaseModel):
    password: str


class DevSimulateStartRequest(BaseModel):
    llm_config: dict[str, Any] | None = None
    script: dict[str, Any] | None = None
    prompt_overrides: dict[str, str] | None = None
    prefer_saved_drafts: bool = True


class DevPromptPreviewRequest(BaseModel):
    script: dict[str, Any] | None = None
    script_id: str | None = None
    prompts: dict[str, str] | None = None
    prefer_saved_drafts: bool = False
    player_message: str = "（示例玩家发言，用于预览 Prompt 渲染效果）"


class DevPromptDraftRequest(BaseModel):
    prompts: dict[str, str]


class DevSimulateMessageRequest(BaseModel):
    session_id: str
    message: str


@app.get("/dev")
async def serve_dev():
    return FileResponse(dev_static_dir / "index.html", headers={"Cache-Control": "no-store"})


@app.post("/api/dev/login")
def dev_login(body: DevLoginRequest):
    if not dev_auth.is_enabled():
        raise HTTPException(status_code=403, detail="Dev mode not enabled (DEV_MODE_PASSWORD not set)")
    if not dev_auth.check_password(body.password):
        raise HTTPException(status_code=401, detail="密码错误")
    token = dev_auth.create_token()
    response = JSONResponse({"ok": True})
    response.set_cookie("dev_token", token, httponly=True, samesite="strict")
    return response


@app.get("/api/dev/scripts", dependencies=[Depends(require_dev_auth)])
def dev_list_scripts():
    return {"scripts": list(script_repository.load_all().values())}


@app.get("/api/dev/scripts/{script_id}", dependencies=[Depends(require_dev_auth)])
def dev_get_script(script_id: str):
    try:
        return script_repository.load_one(script_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Script not found")


@app.post("/api/dev/scripts", dependencies=[Depends(require_dev_auth)])
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


@app.post("/api/dev/scripts/{script_id}/validate", dependencies=[Depends(require_dev_auth)])
def dev_validate_script(script_id: str, body: dict):
    return script_validator.validate(body)


@app.put("/api/dev/scripts/{script_id}", dependencies=[Depends(require_dev_auth)])
def dev_save_script(script_id: str, body: dict):
    if body.get("id") != script_id:
        raise HTTPException(status_code=400, detail="Body id must match URL id")
    result = script_validator.validate(body)
    if result["errors"]:
        raise HTTPException(status_code=422, detail={"errors": result["errors"], "warnings": result["warnings"]})
    script_repository.save(body)
    dev_drafts.delete_script_draft(script_id)
    return {"ok": True, "warnings": result["warnings"]}


@app.delete("/api/dev/scripts/{script_id}", dependencies=[Depends(require_dev_auth)])
def dev_delete_script(script_id: str):
    try:
        script_repository.delete(script_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Script not found")
    dev_drafts.delete_script_draft(script_id)
    return {"ok": True}


@app.post("/api/dev/scripts/{script_id}/simulate/start", dependencies=[Depends(require_dev_auth)])
def dev_simulate_start(script_id: str, body: DevSimulateStartRequest | None = None):
    try:
        req = body or DevSimulateStartRequest()
        llm_override = req.llm_config
        prefer = req.prefer_saved_drafts
        script = dev_drafts.resolve_simulate_script(script_id, req.script, prefer)
        prompt_overrides = dev_drafts.resolve_simulate_prompts(req.prompt_overrides, prefer)
        return engine.start_game(
            script_id,
            llm_override=llm_override,
            script_override=script,
            prompt_overrides=prompt_overrides,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Script not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/dev/scripts/{script_id}/simulate/message", dependencies=[Depends(require_dev_auth)])
def dev_simulate_message(script_id: str, body: DevSimulateMessageRequest):
    try:
        return engine.process_message_debug(body.session_id, body.message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/dev/scripts/{script_id}/export", dependencies=[Depends(require_dev_auth)])
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


@app.get("/api/dev/export", dependencies=[Depends(require_dev_auth)])
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


@app.post("/api/dev/scripts/import", dependencies=[Depends(require_dev_auth)])
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


@app.post("/api/dev/scripts/import/overwrite", dependencies=[Depends(require_dev_auth)])
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


# ── Dev drafts: scripts ───────────────────────────────────────────────────────

@app.get("/api/dev/drafts/scripts/{script_id}", dependencies=[Depends(require_dev_auth)])
def dev_get_script_draft(script_id: str):
    draft = dev_drafts.load_script_draft(script_id)
    if not draft:
        raise HTTPException(status_code=404, detail="No script draft")
    return {"draft": draft, "has_draft": True}


@app.put("/api/dev/drafts/scripts/{script_id}", dependencies=[Depends(require_dev_auth)])
def dev_save_script_draft(script_id: str, body: dict):
    if body.get("id") != script_id:
        raise HTTPException(status_code=400, detail="Body id must match URL id")
    dev_drafts.save_script_draft(body)
    return {"ok": True, "has_draft": True}


@app.delete("/api/dev/drafts/scripts/{script_id}", dependencies=[Depends(require_dev_auth)])
def dev_delete_script_draft(script_id: str):
    dev_drafts.delete_script_draft(script_id)
    return {"ok": True}


@app.get("/api/dev/drafts/scripts/{script_id}/compare", dependencies=[Depends(require_dev_auth)])
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


# ── Dev drafts: prompts ─────────────────────────────────────────────────────

@app.get("/api/dev/prompts", dependencies=[Depends(require_dev_auth)])
def dev_get_prompts():
    production = dev_drafts.load_production_prompts()
    drafts = dev_drafts.load_prompt_drafts()
    return {
        "production": production,
        "draft": drafts,
        "has_draft": dev_drafts.has_prompt_drafts(),
        "keys": dev_drafts.PROMPT_TEMPLATE_KEYS,
    }


@app.put("/api/dev/prompts/draft", dependencies=[Depends(require_dev_auth)])
def dev_save_prompt_draft(body: DevPromptDraftRequest):
    dev_drafts.save_prompt_drafts(body.prompts)
    return {"ok": True, "has_draft": True}


@app.post("/api/dev/prompts/publish", dependencies=[Depends(require_dev_auth)])
def dev_publish_prompts():
    try:
        dev_drafts.publish_prompt_drafts()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@app.delete("/api/dev/prompts/draft", dependencies=[Depends(require_dev_auth)])
def dev_delete_prompt_draft():
    dev_drafts.delete_prompt_drafts()
    return {"ok": True}


@app.post("/api/dev/prompts/preview", dependencies=[Depends(require_dev_auth)])
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


@app.get("/")
async def serve_index():
    return FileResponse(
        static_dir / "index.html",
        headers={"Cache-Control": "no-store"},
    )


app.mount("/", StaticFiles(directory=str(static_dir)), name="static")
