import json
import logging
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from game import engine
from game import llm_client
from game import llm_config

load_dotenv()
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


@app.post("/api/session/start")
def start_session(body: StartSessionRequest):
    try:
        override = body.llm_config.model_dump() if body.llm_config else None
        return engine.start_game(body.script_id, llm_override=override)
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
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
