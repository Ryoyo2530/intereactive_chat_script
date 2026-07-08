"""Simple single-user dev mode authentication via password + session token."""

import os
import secrets

_tokens: set[str] = set()


def _password() -> str | None:
    return os.environ.get("DEV_MODE_PASSWORD") or None


def is_enabled() -> bool:
    return bool(_password())


def check_password(pw: str) -> bool:
    expected = _password()
    if not expected:
        return False
    return secrets.compare_digest(pw.encode(), expected.encode())


def create_token() -> str:
    token = secrets.token_hex(32)
    _tokens.add(token)
    return token


def validate_token(token: str | None) -> bool:
    if not token:
        return False
    return token in _tokens


def revoke_all() -> None:
    _tokens.clear()
