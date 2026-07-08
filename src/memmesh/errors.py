"""Exception hierarchy for the MemMesh SDK.

Mirrors the TypeScript SDK's error classes so behavior is consistent across
languages. Every error carries the HTTP ``status_code`` and raw ``body``.
"""

from __future__ import annotations

from typing import Optional


class MemMeshError(Exception):
    """Base class for every error raised by the SDK."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        body: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class AuthenticationError(MemMeshError):
    """401 — missing or invalid API key."""


class AuthorizationError(MemMeshError):
    """403 — the key is valid but lacks permission for this resource."""


class NotFoundError(MemMeshError):
    """404 — the resource does not exist (or isn't visible to this project)."""


class ValidationError(MemMeshError):
    """400 / 422 — the request body or params failed validation."""


class RateLimitError(MemMeshError):
    """429 — too many requests. The client retries these automatically."""


class ServerError(MemMeshError):
    """5xx — something went wrong on the server. Retried automatically."""


class APITimeoutError(MemMeshError):
    """The request exceeded the configured timeout."""


class APIConnectionError(MemMeshError):
    """The request never reached the server (DNS, TLS, connection refused)."""


def error_from_response(status: int, text: str) -> MemMeshError:
    """Map an HTTP status code to the matching exception class."""
    message = text or f"HTTP {status}"
    if status == 401:
        return AuthenticationError(message, status, text)
    if status == 403:
        return AuthorizationError(message, status, text)
    if status == 404:
        return NotFoundError(message, status, text)
    if status in (400, 422):
        return ValidationError(message, status, text)
    if status == 429:
        return RateLimitError(message, status, text)
    if status >= 500:
        return ServerError(message, status, text)
    return MemMeshError(message, status, text)
