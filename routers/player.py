import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from game.access import require_invite
from game.core import engine
from game.core import session as session_store
from game.llm import client as llm_client
from game.llm import config as llm_config

# Public: index + favicon (no invite gate)
router = APIRouter()

# Player APIs: gated by invite cookie when INVITE_CODE is set
api_router = APIRouter(dependencies=[Depends(require_invite)])

static_dir = Path(__file__).resolve().parent.parent / "static"

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
    save_id: str | None = None


class MessageRequest(BaseModel):
    session_id: str
    message: str


class HintRequest(BaseModel):
    session_id: str


class AdvanceChapterRequest(BaseModel):
    session_id: str


@api_router.get("/api/config/supabase")
def get_supabase_config():
    from game.settings import get_settings
    s = get_settings()
    return {
        "supabase_url": s.supabase_url or "",
        "supabase_anon_key": s.supabase_anon_key or "",
    }


@api_router.post("/api/works/{work_id}/chapters/advance")
def advance_chapter(work_id: str, body: AdvanceChapterRequest, request: Request):
    from game.content.auth_helper import get_user_id_from_token
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else None
    user_id = get_user_id_from_token(token)
    # Attach user_id to session before advancing so save is scoped correctly.
    game_session = session_store.get_session(body.session_id)
    if game_session and user_id and not game_session.get("user_id"):
        session_store.update_session(body.session_id, {"user_id": user_id})
    try:
        return engine.advance_chapter(body.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.get("/api/me/history")
def get_my_history(request: Request):
    from game.content.auth_helper import get_user_id_from_token
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else None
    user_id = get_user_id_from_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    from game.content import short_play_records
    from game.content import user_progress
    short_records = short_play_records.list_for_user(user_id)
    long_records = user_progress.list_long_form_progress(user_id)
    return {"short_play_records": short_records, "long_form_progress": long_records}
def favicon():
    return Response(content=FAVICON_SVG, media_type="image/svg+xml")


@router.get("/")
async def serve_index():
    return FileResponse(
        static_dir / "index.html",
        headers={"Cache-Control": "no-store"},
    )


@api_router.get("/api/config/llm")
def get_llm_config_status():
    return llm_config.get_status()


@api_router.post("/api/config/llm/test")
def test_llm_config(body: LLMConfigRequest):
    try:
        cfg = llm_config.resolve_config(body.model_dump())
        result = llm_client.test_connection(cfg)
        return {"ok": True, **result, "model": cfg.model, "provider": cfg.provider}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"连接失败: {exc}")


@api_router.get("/api/scripts")
def get_scripts():
    return {"scripts": engine.list_scripts()}


@api_router.get("/api/scripts/{script_id}/detail")
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
        "echo_phrases": script.get("echo_phrases"),
        "tone_preset": script.get("tone_preset", "从容"),
        "chapter_title": script.get("chapter_title", script["title"]),
    }


@api_router.post("/api/session/start")
def start_session(body: StartSessionRequest, request: Request):
    from game.content.auth_helper import get_user_id_from_token
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else None
    user_id = get_user_id_from_token(token)
    try:
        override = body.llm_config.model_dump() if body.llm_config else None
        return engine.start_game(
            body.script_id,
            llm_override=override,
            ai_name=body.ai_name,
            ai_persona=body.ai_persona,
            save_id=body.save_id,
            user_id=user_id,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Script not found")
    except session_store.SessionLimitError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail="开局失败，请稍后再试") from exc


@api_router.post("/api/session/message")
def send_message(body: MessageRequest):
    try:
        return engine.process_message(body.session_id, body.message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.post("/api/session/message/stream")
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


@api_router.post("/api/session/hint")
def request_hint(body: HintRequest):
    try:
        return engine.get_hint(body.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
