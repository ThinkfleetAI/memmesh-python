"""HTTP transport — sync (:class:`Transport`) and async
(:class:`AsyncTransport`). Both:

* build URLs as ``{base_url}/api/v1/projects/{project_id}{path}``
* send ``Authorization: Bearer <api_key>``
* retry 429 + 5xx with exponential backoff
* run any request/response interceptors (e.g. to swap the API key for a
  Cognito JWT — see :data:`RequestInterceptor`)
* map HTTP errors to the SDK exception hierarchy

The underlying ``httpx`` client is injectable (pass ``http_client=...``) so a
caller can supply a custom transport, proxy, or a test double
(``httpx.MockTransport``).
"""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, Awaitable, Callable, List, Mapping, Optional, Union

import httpx

from ._version import __version__
from .errors import APIConnectionError, APITimeoutError, error_from_response

_RETRY_STATUS = {429, 500, 502, 503, 504}

#: Called before each request with the built :class:`httpx.Request`. Return a
#: (possibly new) request, or mutate it in place and return ``None``. Use to add
#: headers or swap the ``Authorization`` bearer for a short-lived JWT. In the
#: async transport an interceptor may also be a coroutine function.
RequestInterceptor = Callable[[httpx.Request], Union[httpx.Request, None, Awaitable[Union[httpx.Request, None]]]]

#: Called after each response, before status handling. Return a (possibly new)
#: response, or mutate/inspect it and return ``None``. Async transport awaits
#: coroutine interceptors.
ResponseInterceptor = Callable[[httpx.Response], Union[httpx.Response, None, Awaitable[Union[httpx.Response, None]]]]


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
        *,
        request_interceptors: Optional[List[RequestInterceptor]] = None,
        response_interceptors: Optional[List[ResponseInterceptor]] = None,
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
        self._request_interceptors = list(request_interceptors or [])
        self._response_interceptors = list(response_interceptors or [])

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

    def _build_request(
        self,
        client: Any,
        method: str,
        path: str,
        params: Optional[Mapping[str, Any]],
        json: Any,
        project_id: Optional[str],
    ) -> httpx.Request:
        return client.build_request(
            method,
            self._url(path, project_id),
            headers=self._headers(),
            params=self._clean(params),
            json=json,
        )

    def _handle(self, resp: httpx.Response) -> Any:
        status = resp.status_code
        if status >= 400:
            raise error_from_response(status, resp.text, resp.headers)
        if status == 204 or not resp.content:
            return None
        import json as _json

        return _json.loads(resp.content)


class Transport(_BaseTransport):
    """Synchronous transport backed by ``httpx.Client``."""

    def __init__(
        self,
        api_key: str,
        project_id: str,
        base_url: str,
        timeout: float,
        max_retries: int,
        *,
        request_interceptors: Optional[List[RequestInterceptor]] = None,
        response_interceptors: Optional[List[ResponseInterceptor]] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        super().__init__(
            api_key,
            project_id,
            base_url,
            timeout,
            max_retries,
            request_interceptors=request_interceptors,
            response_interceptors=response_interceptors,
        )
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=self._timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "Transport":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _apply_request_interceptors(self, request: httpx.Request) -> httpx.Request:
        for interceptor in self._request_interceptors:
            result = interceptor(request)
            if result is not None:
                request = result  # type: ignore[assignment]
        return request

    def _apply_response_interceptors(self, response: httpx.Response) -> httpx.Response:
        for interceptor in self._response_interceptors:
            result = interceptor(response)
            if result is not None:
                response = result  # type: ignore[assignment]
        return response

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json: Any = None,
        project_id: Optional[str] = None,
    ) -> Any:
        attempt = 0
        while True:
            request = self._build_request(self._client, method, path, params, json, project_id)
            request = self._apply_request_interceptors(request)
            try:
                resp = self._client.send(request)
            except httpx.TimeoutException as exc:
                raise APITimeoutError(str(exc)) from exc
            except httpx.HTTPError as exc:
                raise APIConnectionError(str(exc)) from exc

            resp = self._apply_response_interceptors(resp)

            if resp.status_code in _RETRY_STATUS and attempt < self._max_retries:
                attempt += 1
                time.sleep(_backoff_seconds(attempt))
                continue
            return self._handle(resp)

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

    def __init__(
        self,
        api_key: str,
        project_id: str,
        base_url: str,
        timeout: float,
        max_retries: int,
        *,
        request_interceptors: Optional[List[RequestInterceptor]] = None,
        response_interceptors: Optional[List[ResponseInterceptor]] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        super().__init__(
            api_key,
            project_id,
            base_url,
            timeout,
            max_retries,
            request_interceptors=request_interceptors,
            response_interceptors=response_interceptors,
        )
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=self._timeout)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "AsyncTransport":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def _apply_request_interceptors(self, request: httpx.Request) -> httpx.Request:
        for interceptor in self._request_interceptors:
            result = interceptor(request)
            if inspect.isawaitable(result):
                result = await result
            if result is not None:
                request = result  # type: ignore[assignment]
        return request

    async def _apply_response_interceptors(self, response: httpx.Response) -> httpx.Response:
        for interceptor in self._response_interceptors:
            result = interceptor(response)
            if inspect.isawaitable(result):
                result = await result
            if result is not None:
                response = result  # type: ignore[assignment]
        return response

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json: Any = None,
        project_id: Optional[str] = None,
    ) -> Any:
        attempt = 0
        while True:
            request = self._build_request(self._client, method, path, params, json, project_id)
            request = await self._apply_request_interceptors(request)
            try:
                resp = await self._client.send(request)
            except httpx.TimeoutException as exc:
                raise APITimeoutError(str(exc)) from exc
            except httpx.HTTPError as exc:
                raise APIConnectionError(str(exc)) from exc

            resp = await self._apply_response_interceptors(resp)

            if resp.status_code in _RETRY_STATUS and attempt < self._max_retries:
                attempt += 1
                await asyncio.sleep(_backoff_seconds(attempt))
                continue
            return self._handle(resp)

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
