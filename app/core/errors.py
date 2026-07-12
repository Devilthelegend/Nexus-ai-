"""Consistent error envelope and exception handlers.

Every error response shares one shape — ``code``, ``message``, ``request_id``
and ``details`` — so clients can handle failures uniformly and correlate them
with logs via the request id. Handlers preserve the original status code and any
security-relevant headers (e.g. ``WWW-Authenticate``, ``Retry-After``).
"""

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from app.core.context import get_request_id

_logger = logging.getLogger("nexus.errors")

_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
}


def error_body(code: str, message: str, details: object | None = None) -> dict:
    """Build the standard error envelope for the current request."""
    return {
        "code": code,
        "message": message,
        "request_id": get_request_id(),
        "details": details,
    }


def _code_for(status_code: int) -> str:
    if status_code in _STATUS_CODES:
        return _STATUS_CODES[status_code]
    return "server_error" if status_code >= 500 else "http_error"


async def _http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(_code_for(exc.status_code), str(exc.detail)),
        headers=getattr(exc, "headers", None),
    )


async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_body(
            "validation_error",
            "Request validation failed",
            jsonable_encoder(exc.errors()),
        ),
    )


async def _unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    _logger.exception("unhandled exception")
    return JSONResponse(
        status_code=500,
        content=error_body("server_error", "Internal server error"),
    )


def install_error_handlers(app: FastAPI) -> None:
    """Register the envelope handlers on the application."""
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(
        RequestValidationError, _validation_exception_handler
    )
    app.add_exception_handler(Exception, _unhandled_exception_handler)
