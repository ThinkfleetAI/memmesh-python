"""Client-infra tests: retry/backoff, typed errors, interceptors, injectable
transport, and the pagination helpers. No live server (respx / MockTransport)."""

import httpx
import pytest
import respx

from memmesh import (
    AsyncMemMesh,
    MemMesh,
    RateLimitError,
    ValidationError,
    apaginate,
    apaginate_cursor,
    paginate,
    paginate_cursor,
)
from memmesh._http import _backoff_seconds

BASE = "https://app.memmesh.ai"
PROJ = "proj_test"
PREFIX = f"{BASE}/api/v1/projects/{PROJ}"


def client(**kw) -> MemMesh:
    kw.setdefault("max_retries", 2)
    return MemMesh(api_key="sk-test", project_id=PROJ, **kw)


# ── retry / backoff ─────────────────────────────────────────────────────────


def test_backoff_is_exponential_and_capped():
    assert _backoff_seconds(1) == 0.5
    assert _backoff_seconds(2) == 1.0
    assert _backoff_seconds(3) == 2.0
    assert _backoff_seconds(100) == 8.0  # capped


@respx.mock
def test_5xx_retried_then_succeeds(monkeypatch):
    monkeypatch.setattr("memmesh._http.time.sleep", lambda *_: None)  # no real waiting
    route = respx.post(f"{PREFIX}/admin/memory/search").mock(
        side_effect=[
            httpx.Response(503, text="try later"),
            httpx.Response(503, text="try later"),
            httpx.Response(200, json=[{"id": "m1"}]),
        ]
    )
    with client(max_retries=2) as mm:
        hits = mm.search("x")
    assert hits == [{"id": "m1"}]
    assert route.call_count == 3  # 1 + 2 retries


@respx.mock
def test_retries_are_bounded_by_max_retries(monkeypatch):
    monkeypatch.setattr("memmesh._http.time.sleep", lambda *_: None)
    route = respx.post(f"{PREFIX}/admin/memory/search").mock(
        return_value=httpx.Response(429, text="slow down", headers={"Retry-After": "7"})
    )
    with client(max_retries=1) as mm:
        with pytest.raises(RateLimitError) as ei:
            mm.search("x")
    assert route.call_count == 2  # 1 + 1 retry, then raise
    assert ei.value.retry_after == 7.0  # parsed off the header
    assert ei.value.status_code == 429


# ── typed errors ────────────────────────────────────────────────────────────


@respx.mock
def test_422_raises_validation_with_parsed_envelope():
    respx.post(f"{PREFIX}/admin/memory/search").mock(
        return_value=httpx.Response(
            422,
            json={"message": "bad query", "code": "INVALID", "params": {"field": "query"}},
        )
    )
    with client(max_retries=0) as mm:
        with pytest.raises(ValidationError) as ei:
            mm.search("x")
    err = ei.value
    assert str(err) == "bad query"
    assert err.code == "INVALID"
    assert err.params == {"field": "query"}
    assert err.status_code == 422


# ── interceptors + injectable transport ─────────────────────────────────────


@respx.mock
def test_request_interceptor_swaps_auth_header():
    route = respx.post(f"{PREFIX}/admin/memory/search").mock(
        return_value=httpx.Response(200, json=[])
    )

    def use_jwt(request: httpx.Request) -> None:
        request.headers["Authorization"] = "Bearer jwt-from-cognito"

    with client(request_interceptors=[use_jwt]) as mm:
        mm.search("x")
    assert route.calls.last.request.headers["authorization"] == "Bearer jwt-from-cognito"


@respx.mock
def test_response_interceptor_observes_each_response():
    respx.post(f"{PREFIX}/admin/memory/search").mock(return_value=httpx.Response(200, json=[]))
    seen = []

    def record(response: httpx.Response) -> None:
        seen.append(response.status_code)

    with client(response_interceptors=[record]) as mm:
        mm.search("x")
    assert seen == [200]


def test_injected_http_client_is_used():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/admin/memory/search")
        return httpx.Response(200, json=[{"id": "mocked"}])

    injected = httpx.Client(transport=httpx.MockTransport(handler))
    with client(http_client=injected) as mm:
        hits = mm.search("x")
    assert hits == [{"id": "mocked"}]


# ── pagination: offset (listAll) ────────────────────────────────────────────


def test_sync_offset_paginator_walks_all_pages():
    pages = {0: [1, 2], 2: [3, 4], 4: [5]}  # last page short -> stop
    calls = []

    def fetch(limit, offset):
        calls.append((limit, offset))
        return pages[offset]

    got = list(paginate(fetch, page_size=2))
    assert got == [1, 2, 3, 4, 5]
    assert calls == [(2, 0), (2, 2), (2, 4)]


def test_sync_offset_paginator_stops_on_exact_empty_page():
    pages = {0: [1, 2], 2: []}

    def fetch(limit, offset):
        return pages[offset]

    assert list(paginate(fetch, page_size=2)) == [1, 2]


def test_offset_page_size_capped_at_max():
    from memmesh import MAX_PAGE_SIZE

    def fetch(limit, offset):
        assert limit == MAX_PAGE_SIZE
        return []

    list(paginate(fetch, page_size=10_000))


async def test_async_offset_paginator_walks_all_pages():
    pages = {0: ["a", "b"], 2: ["c"]}

    async def fetch(limit, offset):
        return pages[offset]

    got = [x async for x in apaginate(fetch, page_size=2)]
    assert got == ["a", "b", "c"]


# ── pagination: cursor (SeekPage) ───────────────────────────────────────────


def test_sync_cursor_paginator_follows_next():
    pages = {
        None: {"data": [1, 2], "next": "c1", "previous": None},
        "c1": {"data": [3], "next": "c2", "previous": "c0"},
        "c2": {"data": [4], "next": None, "previous": "c1"},
    }
    seen_cursors = []

    def fetch(cursor):
        seen_cursors.append(cursor)
        return pages[cursor]

    assert list(paginate_cursor(fetch)) == [1, 2, 3, 4]
    assert seen_cursors == [None, "c1", "c2"]


async def test_async_cursor_paginator_follows_next():
    pages = {
        None: {"data": ["x"], "next": "n", "previous": None},
        "n": {"data": ["y"], "next": None, "previous": None},
    }

    async def fetch(cursor):
        return pages[cursor]

    got = [item async for item in apaginate_cursor(fetch)]
    assert got == ["x", "y"]


# ── async client smoke (injected transport end-to-end) ──────────────────────


async def test_async_client_with_injected_http_client():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "async-mem"})

    injected = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with AsyncMemMesh(api_key="sk", project_id=PROJ, http_client=injected) as mm:
        out = await mm.observe("hello")
    # Legacy verbatim store wrapped in the ObserveResponse shape.
    assert out.saved == [{"id": "async-mem"}]
    assert out.candidate_count == 1
