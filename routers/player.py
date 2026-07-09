import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from game.core import engine
from game.llm import client as llm_client
from game.llm import config as llm_config

router = APIRouter()

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


class MessageRequest(BaseModel):
    session_id: str
    message: str


@router.get("/favicon.ico")
def favicon():
    return Response(content=FAVICON_SVG, media_type="image/svg+xml")


@router.get("/api/config/llm")
def get_llm_config_status():
    return llm_config.get_status()


@router.post("/api/config/llm/test")
def test_llm_config(body: LLMConfigRequest):
    try:
        cfg = llm_config.resolve_config(body.model_dump())
        result = llm_client.test_connection(cfg)
        return {"ok": True, **result, "model": cfg.model, "provider": cfg.provider}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"连接失败: {exc}")


@router.get("/api/scripts")
def get_scripts():
    return {"scripts": engine.list_scripts()}


@router.get("/api/scripts/{script_id}/detail")
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


@router.post("/api/session/start")
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


@router.post("/api/session/message")
def send_message(body: MessageRequest):
    try:
        return engine.process_message(body.session_id, body.message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/session/message/stream")
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


@router.get("/")
async def serve_index():
    return FileResponse(
        static_dir / "index.html",
        headers={"Cache-Control": "no-store"},
    )
