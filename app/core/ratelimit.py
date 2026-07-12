"""In-process fixed-window rate limiting middleware.

Keys each caller by their bearer token (authenticated) or client IP and caps
requests per rolling fixed window. State lives on the middleware instance, so a
freshly built app starts with an empty limiter. Health and docs endpoints are
exempt so orchestrator probes are never throttled. Limits are read from settings
on each request so they can be tuned (and tested) without rebuilding the app.
"""

import hashlib
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.errors import error_body

_EXEMPT_PREFIXES = (
    "/healthz",
    "/readyz",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Cap requests per client within a fixed time window."""

    def __init__(self, app) -> None:  # noqa: ANN001 - Starlette app callable
        super().__init__(app)
        self._hits: dict[str, tuple[int, int]] = {}

    @staticmethod
    def _client_key(request: Request) -> str:
        auth = request.headers.get("authorization")
        if auth:
            digest = hashlib.sha256(auth.encode("utf-8")).hexdigest()[:16]
            return f"u:{digest}"
        client = request.client
        return f"ip:{client.host if client else 'unknown'}"

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        settings = get_settings()
        path = request.url.path
        if not settings.rate_limit_enabled or path.startswith(_EXEMPT_PREFIXES):
            return await call_next(request)

        window_seconds = settings.rate_limit_window_seconds
        limit = settings.rate_limit_requests
        now = time.monotonic()
        window = int(now // window_seconds)
        key = self._client_key(request)

        stored_window, count = self._hits.get(key, (window, 0))
        count = count + 1 if stored_window == window else 1
        self._hits[key] = (window, count)

        if count > limit:
            retry_after = window_seconds - int(now % window_seconds)
            return JSONResponse(
                error_body("rate_limited", "Rate limit exceeded"),
                status_code=429,
                headers={"Retry-After": str(max(retry_after, 1))},
            )
        return await call_next(request)
