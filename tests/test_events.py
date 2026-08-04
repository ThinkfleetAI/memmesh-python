"""Request-shaping tests for the events resource — poll, emit, and a
subscribe start/stop test. No live server (respx / MockTransport)."""

import asyncio
import json
import threading

import httpx
import respx

from memmesh import AsyncMemMesh, MemMesh

BASE = "https://app.memmesh.ai"
PROJ = "proj_test"
PREFIX = f"{BASE}/api/v1/projects/{PROJ}"


def client() -> MemMesh:
    return MemMesh(api_key="sk-test", project_id=PROJ, max_retries=0)


def _body(route) -> dict:
    return json.loads(route.calls.last.request.content)


# ── poll ─────────────────────────────────────────────────────────────────────


@respx.mock
def test_poll_joins_event_types_and_passes_params():
    route = respx.get(f"{PREFIX}/memory-events").mock(
        return_value=httpx.Response(200, json=[{"id": "e1", "occurredAt": "t1"}])
    )
    with client() as mm:
        out = mm.events.poll(
            since="2026-01-01T00:00:00Z",
            limit=50,
            event_types=["risk.fired", "segment.changed"],
        )
    assert out == [{"id": "e1", "occurredAt": "t1"}]
    params = route.calls.last.request.url.params
    assert params["since"] == "2026-01-01T00:00:00Z"
    assert params["limit"] == "50"
    assert params["eventTypes"] == "risk.fired,segment.changed"


@respx.mock
def test_poll_omits_event_types_when_empty():
    route = respx.get(f"{PREFIX}/memory-events").mock(
        return_value=httpx.Response(200, json=[])
    )
    with client() as mm:
        mm.events.poll()
    assert "eventTypes" not in route.calls.last.request.url.params


# ── emit ─────────────────────────────────────────────────────────────────────


@respx.mock
def test_emit_posts_to_lattice_route():
    route = respx.post(f"{PREFIX}/lattice/events/emit").mock(
        return_value=httpx.Response(200, json={"emitted": True, "alertDispatches": 2})
    )
    body = {
        "eventType": "cart.abandoned",
        "subject": {"kind": "contact", "externalId": "sarah"},
        "severity": "warn",
        "payloadJson": json.dumps({"cartValue": 84}),
    }
    with client() as mm:
        out = mm.events.emit(body)
    assert out == {"emitted": True, "alertDispatches": 2}
    assert _body(route) == body


# ── subscribe (sync background thread) start/stop ─────────────────────────────


@respx.mock
def test_subscribe_polls_invokes_handler_then_stops():
    respx.get(f"{PREFIX}/memory-events").mock(
        return_value=httpx.Response(
            200, json=[{"id": "e1", "eventType": "risk.fired", "occurredAt": "t1"}]
        )
    )
    received = []
    got_one = threading.Event()

    def handler(event):
        received.append(event)
        got_one.set()

    with client() as mm:
        stop = mm.events.subscribe(handler, interval_ms=500)
        try:
            assert got_one.wait(timeout=3.0), "handler was never invoked"
        finally:
            stop()  # unsubscribe — loop should exit promptly

    assert received[0]["eventType"] == "risk.fired"


# ── subscribe (async background task) start/stop ──────────────────────────────


async def test_async_subscribe_start_stop():
    def transport_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=[{"id": "e1", "eventType": "segment.changed", "occurredAt": "t1"}]
        )

    injected = httpx.AsyncClient(transport=httpx.MockTransport(transport_handler))
    received = []
    got_one = asyncio.Event()

    async def handler(event):
        received.append(event)
        got_one.set()

    async with AsyncMemMesh(api_key="sk", project_id=PROJ, http_client=injected) as mm:
        stop = mm.events.subscribe(handler, interval_ms=500)
        try:
            await asyncio.wait_for(got_one.wait(), timeout=3.0)
        finally:
            stop()
        # give the cancelled task a tick to unwind
        await asyncio.sleep(0)

    assert received[0]["eventType"] == "segment.changed"


async def test_async_poll_and_emit():
    def transport_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/lattice/events/emit"):
            return httpx.Response(200, json={"emitted": True, "alertDispatches": 0})
        return httpx.Response(200, json=[{"id": "e2", "occurredAt": "t2"}])

    injected = httpx.AsyncClient(transport=httpx.MockTransport(transport_handler))
    async with AsyncMemMesh(api_key="sk", project_id=PROJ, http_client=injected) as mm:
        events = await mm.events.poll(limit=10)
        emitted = await mm.events.emit({"eventType": "x"})
    assert events[0]["id"] == "e2"
    assert emitted["emitted"] is True
