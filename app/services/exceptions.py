"""Domain-level service exceptions, decoupled from the HTTP layer."""


class ServiceError(Exception):
    """Base class for recoverable service-layer errors."""


class EmailAlreadyExists(ServiceError):
    """Raised when registering an email that is already in use."""


class InvalidCredentials(ServiceError):
    """Raised when authentication fails."""


class NotFoundError(ServiceError):
    """Raised when a requested entity does not exist."""


class PermissionDenied(ServiceError):
    """Raised when the caller lacks the required role for an action."""
