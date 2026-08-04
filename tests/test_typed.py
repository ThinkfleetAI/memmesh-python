"""Request-shaping tests for the typed-attributes resource — register_attribute,
list_attributes, ingest, enqueue, query_observations, accumulator. No live
server (respx / MockTransport)."""

import json

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


# ── register_attribute ───────────────────────────────────────────────────────


@respx.mock
def test_register_attribute_posts_body():
    route = respx.post(f"{PREFIX}/memory-typed/attributes").mock(
        return_value=httpx.Response(200, json={"id": "ad1", "attributeKey": "credit_score"})
    )
    body = {"attributeKey": "credit_score", "dataType": "numeric", "minValid": 300, "maxValid": 850}
    with client() as mm:
        out = mm.typed.register_attribute(body)
    assert out["attributeKey"] == "credit_score"
    assert _body(route) == body


# ── list_attributes ──────────────────────────────────────────────────────────


@respx.mock
def test_list_attributes_passes_params():
    route = respx.get(f"{PREFIX}/memory-typed/attributes").mock(
        return_value=httpx.Response(200, json=[{"id": "ad1"}])
    )
    with client() as mm:
        out = mm.typed.list_attributes(attribute_key="credit_score", limit=10, offset=5)
    assert out[0]["id"] == "ad1"
    params = route.calls.last.request.url.params
    assert params["attributeKey"] == "credit_score"
    assert params["limit"] == "10"
    assert params["offset"] == "5"


# ── ingest ───────────────────────────────────────────────────────────────────


@respx.mock
def test_ingest_wraps_observations():
    route = respx.post(f"{PREFIX}/memory-typed/observations").mock(
        return_value=httpx.Response(
            200, json={"accepted": 1, "quarantined": 0, "duplicates": 0, "quarantineReasons": {}}
        )
    )
    obs = [
        {
            "attributeKey": "credit_score",
            "subjectKind": "contact",
            "subjectExternalId": "sarah",
            "valueNumeric": 650,
            "observedAt": "2026-01-01T00:00:00Z",
        }
    ]
    with client() as mm:
        out = mm.typed.ingest(obs)
    assert out["accepted"] == 1
    assert _body(route) == {"observations": obs}


# ── enqueue ──────────────────────────────────────────────────────────────────


@respx.mock
def test_enqueue_wraps_observations():
    route = respx.post(f"{PREFIX}/memory-typed/observations/enqueue").mock(
        return_value=httpx.Response(200, json={"enqueued": 3})
    )
    obs = [
        {
            "attributeKey": "resting_hr",
            "subjectKind": "patient",
            "subjectExternalId": "p1",
            "valueNumeric": 58,
            "observedAt": "2026-01-01T00:00:00Z",
        }
    ]
    with client() as mm:
        out = mm.typed.enqueue(obs)
    assert out == {"enqueued": 3}
    assert _body(route) == {"observations": obs}


# ── query_observations ───────────────────────────────────────────────────────


@respx.mock
def test_query_observations_passes_full_params():
    route = respx.get(f"{PREFIX}/memory-typed/observations").mock(
        return_value=httpx.Response(200, json=[{"id": "o1"}])
    )
    with client() as mm:
        out = mm.typed.query_observations(
            subject_kind="contact",
            subject_external_id="sarah",
            attribute_key="credit_score",
            since="2026-01-01T00:00:00Z",
            until="2026-02-01T00:00:00Z",
            min_value=600,
            max_value=800,
            status="accepted",
            limit=20,
            offset=0,
        )
    assert out[0]["id"] == "o1"
    params = route.calls.last.request.url.params
    assert params["subjectKind"] == "contact"
    assert params["subjectExternalId"] == "sarah"
    assert params["attributeKey"] == "credit_score"
    assert params["since"] == "2026-01-01T00:00:00Z"
    assert params["until"] == "2026-02-01T00:00:00Z"
    assert params["minValue"] == "600"
    assert params["maxValue"] == "800"
    assert params["status"] == "accepted"
    assert params["limit"] == "20"


# ── accumulator ──────────────────────────────────────────────────────────────


@respx.mock
def test_accumulator_passes_params():
    route = respx.get(f"{PREFIX}/memory-typed/accumulator").mock(
        return_value=httpx.Response(200, json={"count": 3, "mean": 650})
    )
    with client() as mm:
        out = mm.typed.accumulator(
            subject_kind="contact", subject_external_id="sarah", attribute_key="credit_score"
        )
    assert out["mean"] == 650
    params = route.calls.last.request.url.params
    assert params["subjectKind"] == "contact"
    assert params["subjectExternalId"] == "sarah"
    assert params["attributeKey"] == "credit_score"


# ── async parity smoke ───────────────────────────────────────────────────────


async def test_async_typed_ingest_and_accumulator():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/accumulator"):
            return httpx.Response(200, json={"count": 1, "mean": 42})
        return httpx.Response(200, json={"accepted": 1, "quarantined": 0, "duplicates": 0})

    injected = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with AsyncMemMesh(api_key="sk", project_id=PROJ, http_client=injected) as mm:
        report = await mm.typed.ingest(
            [
                {
                    "attributeKey": "k",
                    "subjectKind": "contact",
                    "subjectExternalId": "s",
                    "valueNumeric": 42,
                    "observedAt": "2026-01-01T00:00:00Z",
                }
            ]
        )
        acc = await mm.typed.accumulator(
            subject_kind="contact", subject_external_id="s", attribute_key="k"
        )
    assert report["accepted"] == 1
    assert acc["mean"] == 42
