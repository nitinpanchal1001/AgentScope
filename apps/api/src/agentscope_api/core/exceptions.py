from typing import Any


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class AuthenticationError(AppError):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__("AUTHENTICATION_REQUIRED", message, status_code=401)


class PermissionDeniedError(AppError):
    def __init__(self) -> None:
        super().__init__("PERMISSION_DENIED", "You do not have permission", status_code=403)


class NotFoundError(AppError):
    def __init__(self, resource: str) -> None:
        super().__init__("RESOURCE_NOT_FOUND", f"{resource} not found", status_code=404)


class ConflictError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("RESOURCE_CONFLICT", message, status_code=409)


class IngestionError(AppError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__("INVALID_TELEMETRY", message, status_code=422, details=details)


class PayloadTooLargeError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("PAYLOAD_TOO_LARGE", message, status_code=413)


class RateLimitError(AppError):
    def __init__(self) -> None:
        super().__init__("RATE_LIMITED", "Ingestion rate limit exceeded", status_code=429)
