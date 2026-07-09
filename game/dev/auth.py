"""Simple single-user dev mode authentication via password + signed session token."""

import hashlib
import hmac
import secrets
import time

from fastapi import Cookie, HTTPException

from game.settings import get_settings

TOKEN_TTL_SECONDS = 7 * 24 * 3600


def _password() -> str | None:
    pw = get_settings().dev_mode_password.strip()
    return pw or None


def _secret() -> bytes:
    pw = _password() or ""
    return hashlib.sha256(f"ruxi-dev:{pw}".encode()).digest()


def is_enabled() -> bool:
    return bool(_password())


def check_password(pw: str) -> bool:
    expected = _password()
    if not expected:
        return False
    return secrets.compare_digest(pw.encode(), expected.encode())


def create_token() -> str:
    nonce = secrets.token_hex(16)
    ts = int(time.time())
    payload = f"{nonce}.{ts}"
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def validate_token(token: str | None) -> bool:
    if not token or not is_enabled():
        return False
    parts = token.split(".")
    if len(parts) != 3:
        return False
    _nonce, ts_str, sig = parts
    try:
        ts = int(ts_str)
    except ValueError:
        return False
    if time.time() - ts > TOKEN_TTL_SECONDS:
        return False
    payload = f"{_nonce}.{ts_str}"
    expected = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return secrets.compare_digest(sig, expected)


def revoke_all() -> None:
    """No-op: tokens are stateless and expire by TTL."""


def require_dev_auth(dev_token: str | None = Cookie(default=None)):
    if not validate_token(dev_token):
        raise HTTPException(status_code=401, detail="未授权，请先登录开发者模式")
