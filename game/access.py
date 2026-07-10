"""Invite-code gate: single shared code + self-verifying signed cookie.

No server-side storage of tokens. The invite code itself is the HMAC key,
so rotating INVITE_CODE invalidates every existing cookie.

Also hosts process-local runtime metrics used by /api/dev/stats.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from fastapi import Cookie, HTTPException, Request

from game.settings import get_settings

logger = logging.getLogger(__name__)

COOKIE_NAME = "ruxi_invite"
TTL_SECONDS = 30 * 24 * 3600  # 30 days


def _sig(exp: int) -> str:
    secret = get_settings().invite_code.encode()
    return hmac.new(secret, str(exp).encode(), hashlib.sha256).hexdigest()[:16]


def issue_token() -> str:
    exp = int(time.time()) + TTL_SECONDS
    return f"{exp}.{_sig(exp)}"


def verify_token(token: str | None) -> bool:
    settings = get_settings()
    if not settings.invite_code:
        return True  # unset = gate disabled
    if not token or "." not in token:
        return False
    exp_str, sig = token.split(".", 1)
    if not exp_str.isdigit() or int(exp_str) < time.time():
        return False
    return hmac.compare_digest(sig, _sig(int(exp_str)))


def verify_code(code: str) -> bool:
    settings = get_settings()
    if not settings.invite_code:
        return True
    return hmac.compare_digest((code or "").strip().encode(), settings.invite_code.encode())


def is_enabled() -> bool:
    return bool(get_settings().invite_code.strip())


def cookie_secure(request: Request) -> bool:
    """HTTPS (incl. Render via X-Forwarded-Proto) → Secure cookie; local HTTP → False."""
    if request.url.scheme == "https":
        return True
    return request.headers.get("x-forwarded-proto", "").lower() == "https"


def require_invite(ruxi_invite: str | None = Cookie(default=None)):
    if not verify_token(ruxi_invite):
        raise HTTPException(status_code=401, detail="需要邀请码")


# ── Runtime metrics (process-local, reset on restart) ────────────


@dataclass
class RuntimeStats:
    started_at: float = field(default_factory=time.time)
    sessions_started_total: int = 0
    sessions_started_today: int = 0
    llm_failures_total: int = 0
    llm_failures_today: int = 0
    _day_key: str = ""
    _latencies_ms: deque[float] = field(default_factory=lambda: deque(maxlen=200))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _roll_day(self) -> None:
        today = time.strftime("%Y-%m-%d", time.localtime())
        if self._day_key != today:
            self._day_key = today
            self.sessions_started_today = 0
            self.llm_failures_today = 0

    def record_session_start(self) -> None:
        with self._lock:
            self._roll_day()
            self.sessions_started_total += 1
            self.sessions_started_today += 1

    def record_llm_failure(self) -> None:
        with self._lock:
            self._roll_day()
            self.llm_failures_total += 1
            self.llm_failures_today += 1

    def record_latency_ms(self, ms: float) -> None:
        with self._lock:
            self._latencies_ms.append(ms)

    def snapshot(self, active_sessions: int) -> dict:
        with self._lock:
            self._roll_day()
            latencies = list(self._latencies_ms)
            avg = round(sum(latencies) / len(latencies), 1) if latencies else None
            return {
                "active_sessions": active_sessions,
                "sessions_started_today": self.sessions_started_today,
                "sessions_started_total": self.sessions_started_total,
                "llm_failures_today": self.llm_failures_today,
                "llm_failures_total": self.llm_failures_total,
                "avg_latency_ms": avg,
                "latency_samples": len(latencies),
                "uptime_seconds": int(time.time() - self.started_at),
                "invite_enabled": is_enabled(),
            }


runtime_stats = RuntimeStats()
