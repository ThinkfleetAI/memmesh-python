"""Request-shaping tests for the Phase 2 memory methods — get, list_all,
list_platform, mine, explain, list_feedback, and the multimodal observe_*
helpers. No live server (respx mocks)."""

import base64
import json

import httpx
import respx

from memmesh import AsyncMemMesh, MemMesh, subject

BASE = "https://app.memmesh.ai"
PROJ = "proj_test"
PREFIX = f"{BASE}/api/v1/projects/{PROJ}"


def client() -> MemMesh:
    return MemMesh(api_key="sk-test", project_id=PROJ, max_retries=0)


def _body(route) -> dict:
    return json.loads(route.calls.last.request.content)


# ── get ─────────────────────────────────────────────────────────────────────


@respx.mock
def test_get_fetches_single_memory():
    route = respx.get(f"{PREFIX}/admin/memory/mem_9").mock(
        return_value=httpx.Response(200, json={"id": "mem_9", "content": "hi"})
    )
    with client() as mm:
        out = mm.memory.get("mem_9")
    assert out == {"id": "mem_9", "content": "hi"}
    assert route.called


# ── list_all (offset paginator) ─────────────────────────────────────────────


@respx.mock
def test_list_all_walks_every_page():
    pages = {0: [{"id": "a"}, {"id": "b"}], 2: [{"id": "c"}]}  # short page ends walk

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        assert int(request.url.params["limit"]) == 2
        return httpx.Response(200, json=pages[offset])

    respx.get(f"{PREFIX}/admin/memory").mock(side_effect=handler)
    with client() as mm:
        got = [m["id"] for m in mm.memory.list_all(page_size=2)]
    assert got == ["a", "b", "c"]


@respx.mock
def test_list_all_passes_filters():
    route = respx.get(f"{PREFIX}/admin/memory").mock(return_value=httpx.Response(200, json=[]))
    with client() as mm:
        list(mm.memory.list_all(scope="project", status="confirmed", type="event", page_size=50))
    params = route.calls.last.request.url.params
    assert params["scope"] == "project"
    assert params["status"] == "confirmed"
    assert params["type"] == "event"
    assert params["limit"] == "50"


# ── list_platform ───────────────────────────────────────────────────────────


@respx.mock
def test_list_platform_hits_platform_route():
    route = respx.get(f"{PREFIX}/admin/memory/platform").mock(
        return_value=httpx.Response(200, json=[{"id": "p1"}])
    )
    with client() as mm:
        out = mm.memory.list_platform(status="confirmed", limit=5)
    assert out == [{"id": "p1"}]
    params = route.calls.last.request.url.params
    assert params["status"] == "confirmed"
    assert params["limit"] == "5"


# ── mine ────────────────────────────────────────────────────────────────────


@respx.mock
def test_mine_hits_user_route():
    route = respx.get(f"{PREFIX}/memory/mine").mock(
        return_value=httpx.Response(200, json=[{"id": "u1"}])
    )
    with client() as mm:
        out = mm.memory.mine(limit=20)
    assert out == [{"id": "u1"}]
    assert route.calls.last.request.url.params["limit"] == "20"


# ── list_feedback ───────────────────────────────────────────────────────────


@respx.mock
def test_list_feedback_hits_feedback_route():
    route = respx.get(f"{PREFIX}/admin/memory/mem_1/feedback").mock(
        return_value=httpx.Response(200, json=[{"id": "fb1", "rating": "negative"}])
    )
    with client() as mm:
        out = mm.memory.list_feedback("mem_1")
    assert out[0]["rating"] == "negative"
    assert route.called


# ── explain ─────────────────────────────────────────────────────────────────


@respx.mock
def test_explain_resolves_source_memories():
    respx.get(f"{PREFIX}/admin/memory/pat_1").mock(
        return_value=httpx.Response(
            200,
            json={"id": "pat_1", "metadata": {"sourceMemoryIds": ["s1", "s2"]}},
        )
    )
    respx.get(f"{PREFIX}/admin/memory/s1").mock(return_value=httpx.Response(200, json={"id": "s1"}))
    # s2 was deleted — 404 should be skipped, not fatal.
    respx.get(f"{PREFIX}/admin/memory/s2").mock(return_value=httpx.Response(404, text="gone"))
    with client() as mm:
        out = mm.memory.explain("pat_1")
    assert out["memory"]["id"] == "pat_1"
    assert [m["id"] for m in out["sourceMemories"]] == ["s1"]


@respx.mock
def test_explain_no_sources_returns_empty():
    respx.get(f"{PREFIX}/admin/memory/mem_x").mock(
        return_value=httpx.Response(200, json={"id": "mem_x", "metadata": {}})
    )
    with client() as mm:
        out = mm.memory.explain("mem_x")
    assert out["memory"]["id"] == "mem_x"
    assert out["sourceMemories"] == []


@respx.mock
def test_explain_accepts_snake_case_source_ids():
    respx.get(f"{PREFIX}/admin/memory/pat_2").mock(
        return_value=httpx.Response(
            200, json={"id": "pat_2", "metadata": {"source_memory_ids": ["s3"]}}
        )
    )
    respx.get(f"{PREFIX}/admin/memory/s3").mock(return_value=httpx.Response(200, json={"id": "s3"}))
    with client() as mm:
        out = mm.memory.explain("pat_2")
    assert [m["id"] for m in out["sourceMemories"]] == ["s3"]


# ── multimodal observe_* helpers ────────────────────────────────────────────


@respx.mock
def test_observe_image_uploads_attachment_base64():
    route = respx.post(f"{PREFIX}/memory/attachments").mock(
        return_value=httpx.Response(200, json={"id": "img_mem"})
    )
    raw = b"\x89PNG\r\n"
    with client() as mm:
        out = mm.memory.observe_image(
            subject("contact", "sarah"),
            raw,
            "image/png",
            file_name="receipt.png",
            content="Receipt for $38",
        )
    assert out == {"id": "img_mem"}
    body = _body(route)
    assert body["dataBase64"] == base64.b64encode(raw).decode("ascii")
    assert body["mimeType"] == "image/png"
    assert body["fileName"] == "receipt.png"
    assert body["content"] == "Receipt for $38"
    assert body["subject"] == {"kind": "contact", "externalId": "sarah"}


@respx.mock
def test_observe_voice_accepts_prencoded_base64():
    route = respx.post(f"{PREFIX}/memory/attachments").mock(
        return_value=httpx.Response(200, json={"id": "voice_mem"})
    )
    with client() as mm:
        mm.memory.observe_voice(
            subject("user", "ryan"),
            "YWxyZWFkeS1iNjQ=",  # pre-encoded string passes through verbatim
            "audio/mpeg",
        )
    body = _body(route)
    assert body["dataBase64"] == "YWxyZWFkeS1iNjQ="
    assert body["mimeType"] == "audio/mpeg"
    assert "fileName" not in body  # None fields dropped


@respx.mock
def test_observe_document_uploads_attachment():
    route = respx.post(f"{PREFIX}/memory/attachments").mock(
        return_value=httpx.Response(200, json={"id": "doc_mem"})
    )
    with client() as mm:
        mm.memory.observe_document(
            subject("project", "acme"),
            b"%PDF-1.7",
            "application/pdf",
            content="ACME MSA",
            metadata={"term": "24mo"},
        )
    body = _body(route)
    assert body["mimeType"] == "application/pdf"
    assert body["metadata"] == {"term": "24mo"}
    assert body["dataBase64"] == base64.b64encode(b"%PDF-1.7").decode("ascii")


# ── async parity smoke ──────────────────────────────────────────────────────


async def test_async_list_all_walks_pages():
    pages = {0: [{"id": "a"}, {"id": "b"}], 2: [{"id": "c"}]}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=pages[int(request.url.params["offset"])])

    injected = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with AsyncMemMesh(api_key="sk", project_id=PROJ, http_client=injected) as mm:
        got = [m["id"] async for m in mm.memory.list_all(page_size=2)]
    assert got == ["a", "b", "c"]


async def test_async_explain_gathers_sources():
    store = {
        "pat_1": {"id": "pat_1", "metadata": {"sourceMemoryIds": ["s1", "s2"]}},
        "s1": {"id": "s1"},
        "s2": {"id": "s2"},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        mem_id = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=store[mem_id])

    injected = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with AsyncMemMesh(api_key="sk", project_id=PROJ, http_client=injected) as mm:
        out = await mm.memory.explain("pat_1")
    assert sorted(m["id"] for m in out["sourceMemories"]) == ["s1", "s2"]
