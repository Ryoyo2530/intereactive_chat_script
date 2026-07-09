from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from game.core import engine
from game.dev import auth as dev_auth
from game.dev import drafts as dev_drafts

router = APIRouter()


class DevSimulateStartRequest(BaseModel):
    llm_config: dict[str, Any] | None = None
    script: dict[str, Any] | None = None
    prompt_overrides: dict[str, str] | None = None
    prefer_saved_drafts: bool = True


class DevSimulateMessageRequest(BaseModel):
    session_id: str
    message: str


@router.post("/api/dev/scripts/{script_id}/simulate/start", dependencies=[Depends(dev_auth.require_dev_auth)])
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


@router.post("/api/dev/scripts/{script_id}/simulate/message", dependencies=[Depends(dev_auth.require_dev_auth)])
def dev_simulate_message(script_id: str, body: DevSimulateMessageRequest):
    try:
        return engine.process_message_debug(body.session_id, body.message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
