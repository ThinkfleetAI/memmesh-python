"""Request-shaping tests — verify the SDK builds the right URLs, headers, and
bodies against the real API contract, without a live server (respx mocks)."""

import httpx
import pytest
import respx

from memmesh import MemMesh, MemoryType, subject
from memmesh.errors import AuthenticationError, RateLimitError

BASE = "https://memory.thinkfleet.ai"
PROJ = "proj_test"
PREFIX = f"{BASE}/api/v1/projects/{PROJ}"


def client() -> MemMesh:
    return MemMesh(api_key="sk-test", project_id=PROJ, max_retries=1)


@respx.mock
def test_observe_posts_admin_memory_with_subject_metadata():
    route = respx.post(f"{PREFIX}/admin/memory").mock(
        return_value=httpx.Response(200, json={"id": "mem_1"})
    )
    with client() as mm:
        out = mm.observe(
            "Ordered a large pizza, no tip.",
            subject=subject("contact", "sarah"),
            activity_type="pizza_order",
        )
    assert out == {"id": "mem_1"}
    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer sk-test"
    body = __import__("json").loads(sent.content)
    assert body["type"] == "event"
    assert body["metadata"]["subject"] == {"kind": "contact", "externalId": "sarah"}
    assert body["metadata"]["eventType"] == "pizza_order"


@respx.mock
def test_search_posts_query():
    route = respx.post(f"{PREFIX}/admin/memory/search").mock(
        return_value=httpx.Response(200, json=[{"id": "mem_1", "score": 0.9}])
    )
    with client() as mm:
        hits = mm.search("pizza", limit=3)
    assert hits[0]["id"] == "mem_1"
    body = __import__("json").loads(route.calls.last.request.content)
    assert body == {"query": "pizza", "limit": 3}


@respx.mock
def test_predict_hits_lattice_endpoint():
    route = respx.post(f"{PREFIX}/lattice/predict").mock(
        return_value=httpx.Response(200, json={"predictions": []})
    )
    with client() as mm:
        mm.predict(subject("contact", "sarah"), horizon_days=14)
    body = __import__("json").loads(route.calls.last.request.content)
    assert body == {"subject": {"kind": "contact", "externalId": "sarah"}, "horizonDays": 14}


@respx.mock
def test_enum_is_accepted_for_type():
    route = respx.post(f"{PREFIX}/admin/memory").mock(
        return_value=httpx.Response(200, json={"id": "m"})
    )
    with client() as mm:
        mm.memory.create("hello", type=MemoryType.RULE)
    body = __import__("json").loads(route.calls.last.request.content)
    assert body["type"] == "rule"


@respx.mock
def test_401_raises_authentication_error():
    respx.post(f"{PREFIX}/admin/memory/search").mock(
        return_value=httpx.Response(401, text="bad key")
    )
    with client() as mm:
        with pytest.raises(AuthenticationError):
            mm.search("x")


@respx.mock
def test_429_is_retried_then_raises():
    respx.post(f"{PREFIX}/admin/memory/search").mock(
        return_value=httpx.Response(429, text="slow down")
    )
    with client() as mm:
        with pytest.raises(RateLimitError):
            mm.search("x")
