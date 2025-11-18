"""
Shared API error classes and handlers.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.logging_config import get_logger

logger = get_logger(__name__)


class APIError(Exception):
    """Base API error with HTTP semantics."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        code: str = "INTERNAL_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details or {}
        super().__init__(message)


class ValidationError(APIError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, status_code=400, code="VALIDATION_ERROR", details=details)


class NotFoundError(APIError):
    def __init__(self, resource: str, identifier: Any) -> None:
        super().__init__(
            f"{resource} with id {identifier} not found",
            status_code=404,
            code="NOT_FOUND",
            details={"resource": resource, "id": identifier},
        )


class ForbiddenError(APIError):
    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__(message, status_code=403, code="FORBIDDEN")


class RateLimitError(APIError):
    def __init__(self, retry_after: int = 60) -> None:
        super().__init__(
            "Rate limit exceeded",
            status_code=429,
            code="RATE_LIMIT",
            details={"retry_after": retry_after},
        )


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    logger.error(
        "API error: %s %s",
        exc.code,
        exc.message,
        extra={"path": request.url.path, "status": exc.status_code},
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, HTTPException):
        # Let FastAPI handle native HTTP exceptions
        raise exc
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "Unexpected server error"}},
    )


