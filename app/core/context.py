"""Per-request context propagated via a ``ContextVar``.

Holds the current request/correlation id so it can be attached to structured
logs and error responses without threading it through every function signature.
"""

import uuid
from contextvars import ContextVar, Token

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def new_request_id() -> str:
    """Generate a fresh correlation id."""
    return uuid.uuid4().hex


def set_request_id(value: str) -> Token[str | None]:
    """Bind ``value`` as the current request id; returns a reset token."""
    return _request_id.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    """Restore the previous request id using ``token``."""
    _request_id.reset(token)


def get_request_id() -> str | None:
    """Return the current request id, or ``None`` outside a request."""
    return _request_id.get()
