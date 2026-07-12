"""Observability middleware and optional tracing/error-tracking hooks.

``RequestContextMiddleware`` assigns (or propagates) an ``X-Request-ID`` and
binds it to the logging context for the duration of the request.
``MetricsMiddleware`` records request counts, in-flight gauge, latency histogram
and 5xx errors into the metrics registry. The tracing and Sentry initialisers
are no-ops unless their optional packages are installed and configured, so the
stack is fully offline by default while remaining production-ready.
"""

import logging
from time import perf_counter

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import Settings
from app.core.context import get_request_id, new_request_id, reset_request_id, set_request_id
from app.core.metrics import get_metrics

_REQUEST_ID_HEADER = "X-Request-ID"
_logger = logging.getLogger("nexus.observability")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign/propagate a correlation id and expose it on the response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(_REQUEST_ID_HEADER) or new_request_id()
        token = set_request_id(request_id)
        try:
            response = await call_next(request)
        finally:
            reset_request_id(token)
        response.headers[_REQUEST_ID_HEADER] = request_id
        return response


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record request throughput, latency, concurrency and error metrics."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        metrics = get_metrics()
        metrics.http_in_flight.inc()
        started = perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            metrics.http_in_flight.dec()
            metrics.http_duration.observe(perf_counter() - started)
            metrics.http_requests.inc(method=request.method, status=str(status))
            if status >= 500:
                metrics.http_errors.inc(method=request.method)


def record_llm_usage(tokens: int, cost_usd: float) -> None:
    """Increment LLM token and cost counters (best-effort, never raises)."""
    try:
        metrics = get_metrics()
        metrics.llm_tokens.inc(float(tokens))
        metrics.llm_cost_usd.inc(float(cost_usd))
    except Exception:  # noqa: BLE001 - metrics must never break a request
        _logger.debug("failed to record llm usage", exc_info=True)


def init_tracing(app: FastAPI, settings: Settings) -> None:
    """Instrument the app with OpenTelemetry if enabled and installed."""
    if not settings.otel_enabled:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        _logger.info("OpenTelemetry tracing enabled")
    except Exception:  # noqa: BLE001 - tracing is optional
        _logger.warning("otel_enabled but instrumentation unavailable")


def init_error_tracking(settings: Settings) -> None:
    """Initialise Sentry error tracking if a DSN is configured and installed."""
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment)
        _logger.info("Sentry error tracking enabled")
    except Exception:  # noqa: BLE001 - error tracking is optional
        _logger.warning("sentry_dsn set but sentry_sdk unavailable")


__all__ = [
    "RequestContextMiddleware",
    "MetricsMiddleware",
    "record_llm_usage",
    "init_tracing",
    "init_error_tracking",
    "get_request_id",
]
