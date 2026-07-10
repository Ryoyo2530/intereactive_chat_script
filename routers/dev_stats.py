"""Dev-only runtime stats endpoint (v1.4)."""

from fastapi import APIRouter, Depends

from game import access as invite_access
from game.core import session as session_store
from game.dev import auth as dev_auth

router = APIRouter()


@router.get("/api/dev/stats", dependencies=[Depends(dev_auth.require_dev_auth)])
def dev_stats():
    return invite_access.runtime_stats.snapshot(session_store.active_count())
