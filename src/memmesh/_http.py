"""HTTP transport — sync (:class:`Transport`) and async
(:class:`AsyncTransport`). Both:

* build URLs as ``{base_url}/api/v1/projects/{project_id}{path}``
* send ``Authorization: Bearer <api_key>``
* retry 429 + 5xx with exponential backoff
* map HTTP errors to the SDK exception hierarchy
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Mapping, Optional

import httpx

from ._version import __version__
from .errors import APIConnectionError, APITimeoutError, error_from_response

_RETRY_STATUS = {429, 500, 502, 503, 504}


def _backoff_seconds(attempt: int) -> float:
    return min(0.25 * (2 ** attempt), 8.0)


class _BaseTransport:
    def __init__(
        self,
        api_key: str,
        project_id: str,
        base_url: str,
        timeout: float,
        max_retries: int,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        if not project_id:
            raise ValueError("project_id is required")
        self._api_key = api_key
        self._project_id = project_id
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries

    def _url(self, path: str, project_id: Optional[str]) -> str:
        pid = project_id or self._project_id
        return f"{self._base_url}/api/v1/projects/{pid}{path}"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": f"memmesh-python/{__version__}",
        }

    @staticmethod
    def _clean(params: Optional[Mapping[str, Any]]) -> Optional[dict]:
        if not params:
            return None
        return {k: v for k, v in params.items() if v is not None}

    def _handle(self, status: int, content: bytes, text: str) -> Any:
        if status >= 400:
            raise error_from_response(status, text)
        if status == 204 or not content:
            return None
        import json as _json

        return _json.loads(content)


class Transport(_BaseTransport):
    """Synchronous transport backed by ``httpx.Client``."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._client = httpx.Client(timeout=self._timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Transport":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json: Any = None,
        project_id: Optional[str] = None,
    ) -> Any:
        url = self._url(path, project_id)
        attempt = 0
        while True:
            try:
                resp = self._client.request(
                    method,
                    url,
                    headers=self._headers(),
                    params=self._clean(params),
                    json=json,
                )
            except httpx.TimeoutException as exc:
                raise APITimeoutError(str(exc)) from exc
            except httpx.HTTPError as exc:
                raise APIConnectionError(str(exc)) from exc

            if resp.status_code in _RETRY_STATUS and attempt < self._max_retries:
                attempt += 1
                time.sleep(_backoff_seconds(attempt))
                continue
            return self._handle(resp.status_code, resp.content, resp.text)

    def get(self, path: str, params: Optional[Mapping[str, Any]] = None, project_id: Optional[str] = None) -> Any:
        return self.request("GET", path, params=params, project_id=project_id)

    def post(self, path: str, json: Any = None, project_id: Optional[str] = None) -> Any:
        return self.request("POST", path, json=json, project_id=project_id)

    def put(self, path: str, json: Any = None, project_id: Optional[str] = None) -> Any:
        return self.request("PUT", path, json=json, project_id=project_id)

    def patch(self, path: str, json: Any = None, project_id: Optional[str] = None) -> Any:
        return self.request("PATCH", path, json=json, project_id=project_id)

    def delete(self, path: str, project_id: Optional[str] = None) -> Any:
        return self.request("DELETE", path, project_id=project_id)


class AsyncTransport(_BaseTransport):
    """Asynchronous transport backed by ``httpx.AsyncClient``."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncTransport":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json: Any = None,
        project_id: Optional[str] = None,
    ) -> Any:
        url = self._url(path, project_id)
        attempt = 0
        while True:
            try:
                resp = await self._client.request(
                    method,
                    url,
                    headers=self._headers(),
                    params=self._clean(params),
                    json=json,
                )
            except httpx.TimeoutException as exc:
                raise APITimeoutError(str(exc)) from exc
            except httpx.HTTPError as exc:
                raise APIConnectionError(str(exc)) from exc

            if resp.status_code in _RETRY_STATUS and attempt < self._max_retries:
                attempt += 1
                await asyncio.sleep(_backoff_seconds(attempt))
                continue
            return self._handle(resp.status_code, resp.content, resp.text)

    async def get(self, path: str, params: Optional[Mapping[str, Any]] = None, project_id: Optional[str] = None) -> Any:
        return await self.request("GET", path, params=params, project_id=project_id)

    async def post(self, path: str, json: Any = None, project_id: Optional[str] = None) -> Any:
        return await self.request("POST", path, json=json, project_id=project_id)

    async def put(self, path: str, json: Any = None, project_id: Optional[str] = None) -> Any:
        return await self.request("PUT", path, json=json, project_id=project_id)

    async def patch(self, path: str, json: Any = None, project_id: Optional[str] = None) -> Any:
        return await self.request("PATCH", path, json=json, project_id=project_id)

    async def delete(self, path: str, project_id: Optional[str] = None) -> Any:
        return await self.request("DELETE", path, project_id=project_id)
