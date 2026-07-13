"""Retry transient Supabase / HTTP network failures."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_DEFAULT_ATTEMPTS = 3
_DEFAULT_BASE_DELAY_S = 0.5


def _is_retryable(exc: BaseException) -> bool:
    """Return True for flaky network errors worth retrying."""
    try:
        import httpx
    except ImportError:
        httpx = None  # type: ignore[assignment]

    if httpx is not None:
        if isinstance(
            exc,
            (
                httpx.ConnectError,
                httpx.ReadTimeout,
                httpx.WriteTimeout,
                httpx.ConnectTimeout,
                httpx.PoolTimeout,
                httpx.RemoteProtocolError,
            ),
        ):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in (408, 425, 429, 500, 502, 503, 504)

    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        # macOS ECONNRESET=54, ETIMEDOUT=60; also cover generic resets.
        errno = getattr(exc, "errno", None)
        if errno in (54, 60, 61, 104, 110):
            return True
        message = str(exc).lower()
        if "connection reset" in message or "timed out" in message:
            return True

    cause = exc.__cause__
    if cause is not None and cause is not exc:
        return _is_retryable(cause)

    return False


def call_with_retry(
    fn: Callable[[], T],
    *,
    action: str,
    max_attempts: int = _DEFAULT_ATTEMPTS,
    base_delay_s: float = _DEFAULT_BASE_DELAY_S,
) -> T:
    """Run ``fn`` with exponential backoff on transient network errors."""
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except BaseException as exc:
            last_exc = exc
            if attempt >= max_attempts or not _is_retryable(exc):
                raise
            delay = base_delay_s * (2 ** (attempt - 1))
            logger.warning(
                "[supabase_retry] %s failed (attempt %s/%s): %s; retrying in %.1fs",
                action,
                attempt,
                max_attempts,
                exc,
                delay,
            )
            time.sleep(delay)
    raise RuntimeError(f"{action} failed after retries") from last_exc


def supabase_execute(builder: Any, *, action: str, max_attempts: int = _DEFAULT_ATTEMPTS) -> Any:
    """Call ``builder.execute()`` with retries on transient network errors."""
    return call_with_retry(
        builder.execute,
        action=action,
        max_attempts=max_attempts,
    )
