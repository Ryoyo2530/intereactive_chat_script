"""Invite-code access routes (v1.4): single shared code → signed cookie."""

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from game import access
from game.settings import get_settings

router = APIRouter()


class VerifyRequest(BaseModel):
    code: str


@router.post("/api/access/verify")
def verify(body: VerifyRequest, request: Request, response: Response):
    if not get_settings().invite_code.strip():
        return {"ok": True}

    if not access.verify_code(body.code):
        raise HTTPException(status_code=403, detail="邀请码不对")

    response.set_cookie(
        access.COOKIE_NAME,
        access.issue_token(),
        max_age=access.TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=access.cookie_secure(request),
        path="/",
    )
    return {"ok": True}
