"""Exception hierarchy for the MemMesh SDK.

Mirrors the TypeScript SDK's error classes so behavior is consistent across
languages. Every error carries the HTTP ``status_code`` and raw ``body``; where
the server returns a JSON error envelope (``{message, code, params}``) those are
surfaced on ``code`` / ``params`` too.
"""

from __future__ import annotations

import json as _json
from typing import Any, Mapping, Optional


class MemMeshError(Exception):
    """Base class for every error raised by the SDK."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        body: Optional[str] = None,
        *,
        code: Optional[str] = None,
        params: Optional[dict] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body
        self.code = code
        self.params = params


class AuthenticationError(MemMeshError):
    """401 — missing or invalid API key."""


class AuthorizationError(MemMeshError):
    """403 — the key is valid but lacks permission for this resource."""


class NotFoundError(MemMeshError):
    """404 — the resource does not exist (or isn't visible to this project)."""


class ValidationError(MemMeshError):
    """400 / 422 — the request body or params failed validation. Field-level
    detail (when the server sends it) is on :attr:`params`."""


class RateLimitError(MemMeshError):
    """429 — too many requests. The client retries these automatically.

    :attr:`retry_after` is the ``Retry-After`` hint in seconds (``None`` when the
    server didn't send one).
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        body: Optional[str] = None,
        *,
        code: Optional[str] = None,
        params: Optional[dict] = None,
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(message, status_code, body, code=code, params=params)
        self.retry_after = retry_after


class ServerError(MemMeshError):
    """5xx — something went wrong on the server. Retried automatically."""


class APITimeoutError(MemMeshError):
    """The request exceeded the configured timeout."""


class APIConnectionError(MemMeshError):
    """The request never reached the server (DNS, TLS, connection refused)."""


def _parse_body(text: str) -> tuple[str, Optional[str], Optional[dict]]:
    """Pull ``message`` / ``code`` / ``params`` out of a JSON error envelope,
    mirroring the TS client. Falls back to the raw text as the message."""
    message = text
    code: Optional[str] = None
    params: Optional[dict] = None
    if text:
        try:
            parsed = _json.loads(text)
        except (ValueError, TypeError):
            return text, None, None
        if isinstance(parsed, dict):
            message = parsed.get("message") or parsed.get("error") or text
            raw_code = parsed.get("code")
            code = raw_code if isinstance(raw_code, str) else None
            raw_params = parsed.get("params")
            params = raw_params if isinstance(raw_params, dict) else None
    return message, code, params


def _retry_after_seconds(headers: Optional[Mapping[str, Any]]) -> Optional[float]:
    if not headers:
        return None
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def error_from_response(
    status: int,
    text: str,
    headers: Optional[Mapping[str, Any]] = None,
) -> MemMeshError:
    """Map an HTTP status code (+ optional body/headers) to the matching
    exception class."""
    parsed_message, code, params = _parse_body(text)
    message = parsed_message or f"HTTP {status}"
    if status == 401:
        return AuthenticationError(message, status, text, code=code, params=params)
    if status == 403:
        return AuthorizationError(message, status, text, code=code, params=params)
    if status == 404:
        return NotFoundError(message, status, text, code=code, params=params)
    if status in (400, 422):
        return ValidationError(message, status, text, code=code, params=params)
    if status == 429:
        return RateLimitError(
            message,
            status,
            text,
            code=code,
            params=params,
            retry_after=_retry_after_seconds(headers),
        )
    if status >= 500:
        return ServerError(message, status, text, code=code, params=params)
    return MemMeshError(message, status, text, code=code, params=params)
