"""Extract verified user_id from a Supabase Bearer JWT."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def get_user_id_from_token(token: str | None) -> str | None:
    """Call Supabase Auth to verify `token` and return the user UUID, or None."""
    if not token:
        return None
    try:
        from game.db.supabase_client import get_supabase
        client = get_supabase()
        res = client.auth.get_user(token)
        user = getattr(res, "user", None)
        if user and getattr(user, "id", None):
            return str(user.id)
    except Exception as exc:
        logger.debug("[auth_helper] token verification failed: %s", exc)
    return None
