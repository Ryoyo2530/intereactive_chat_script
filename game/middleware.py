"""HTTP middleware: rate limiting, static cache headers."""

import logging
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

STATIC_CACHE_PATHS = ("/echoes/", "/vendor/", "/style.css", "/app.js", "/favicon.ico")
STATIC_CACHE_CONTROL = "public, max-age=86400"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory per-IP rate limiter for API routes."""

    def __init__(self, app, requests_per_minute: int = 120):
        super().__init__(app)
        self.limit = max(requests_per_minute, 1)
        self._hits: dict[str, list[float]] = defaultdict(list)

    def _client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        now = time.time()
        ip = self._client_ip(request)
        window = self._hits[ip]
        window[:] = [t for t in window if now - t < 60]
        if len(window) >= self.limit:
            logger.warning("rate_limit ip=%s path=%s", ip, path)
            return JSONResponse(
                {"detail": "请求过于频繁，请稍后再试"},
                status_code=429,
            )
        window.append(now)
        return await call_next(request)


class StaticCacheMiddleware(BaseHTTPMiddleware):
    """Add cache headers for versioned static assets."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        path = request.url.path
        if response.status_code == 200 and any(path.startswith(p) or path.endswith(p) for p in STATIC_CACHE_PATHS):
            if "cache-control" not in response.headers:
                response.headers["Cache-Control"] = STATIC_CACHE_CONTROL
        return response
