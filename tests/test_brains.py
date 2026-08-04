"""Request-shaping tests for the Phase 5 brains resource — create,
create_from_project, list (cursor pagination), get, update, delete. No live
server (respx mocks)."""

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


# ── create ──────────────────────────────────────────────────────────────────


@respx.mock
def test_create_posts_full_body_to_brains():
    route = respx.post(f"{PREFIX}/brains").mock(
        return_value=httpx.Response(200, json={"id": "b1", "externalId": "sec-edgar"})
    )
    with client() as mm:
        out = mm.brains.create(
            {
                "externalId": "sec-edgar",
                "name": "SEC EDGAR Financials",
                "domain": "finance",
                "version": "2026.07.0",
                "card": {"provenance": [{"source": "SEC EDGAR", "license": "public-domain"}]},
            }
        )
    assert out["id"] == "b1"
    body = _body(route)
    assert body["externalId"] == "sec-edgar"
    assert body["domain"] == "finance"
    assert body["card"]["provenance"][0]["source"] == "SEC EDGAR"


# ── create_from_project ─────────────────────────────────────────────────────


@respx.mock
def test_create_from_project_builds_draft_private_body():
    route = respx.post(f"{PREFIX}/brains").mock(
        return_value=httpx.Response(200, json={"id": "b2", "status": "DRAFT"})
    )
    with client() as mm:
        out = mm.brains.create_from_project(
            external_id="my-support-playbook", name="Support Playbook", domain="support"
        )
    assert out["status"] == "DRAFT"
    body = _body(route)
    assert body == {
        "externalId": "my-support-playbook",
        "name": "Support Playbook",
        "domain": "support",
        "version": "1.0.0",
        "visibility": "PRIVATE",
        "card": {"provenance": [], "coverage": {}},
    }


@respx.mock
def test_create_from_project_omits_domain_when_absent():
    route = respx.post(f"{PREFIX}/brains").mock(
        return_value=httpx.Response(200, json={"id": "b3"})
    )
    with client() as mm:
        mm.brains.create_from_project(external_id="slug", name="Name")
    body = _body(route)
    assert "domain" not in body
    assert body["version"] == "1.0.0"
    assert body["visibility"] == "PRIVATE"


# ── list (cursor pagination) ────────────────────────────────────────────────


@respx.mock
def test_list_walks_all_cursor_pages():
    def handler(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        if cursor is None:
            return httpx.Response(
                200, json={"data": [{"id": "b1"}, {"id": "b2"}], "next": "c1", "previous": None}
            )
        if cursor == "c1":
            return httpx.Response(
                200, json={"data": [{"id": "b3"}], "next": None, "previous": None}
            )
        raise AssertionError(f"unexpected cursor {cursor}")

    respx.get(f"{PREFIX}/brains").mock(side_effect=handler)
    with client() as mm:
        got = [b["id"] for b in mm.brains.list(limit=2)]
    assert got == ["b1", "b2", "b3"]


@respx.mock
def test_list_passes_limit_param():
    route = respx.get(f"{PREFIX}/brains").mock(
        return_value=httpx.Response(200, json={"data": [], "next": None, "previous": None})
    )
    with client() as mm:
        list(mm.brains.list(limit=25))
    assert route.calls.last.request.url.params["limit"] == "25"


# ── get / update / delete ───────────────────────────────────────────────────


@respx.mock
def test_get_hits_brain_route():
    respx.get(f"{PREFIX}/brains/b9").mock(
        return_value=httpx.Response(200, json={"id": "b9", "status": "PUBLISHED"})
    )
    with client() as mm:
        out = mm.brains.get("b9")
    assert out["id"] == "b9"


@respx.mock
def test_update_patches_brain():
    route = respx.patch(f"{PREFIX}/brains/b9").mock(
        return_value=httpx.Response(200, json={"id": "b9", "status": "PUBLISHED"})
    )
    with client() as mm:
        out = mm.brains.update("b9", {"visibility": "PUBLIC", "status": "PUBLISHED"})
    assert out["status"] == "PUBLISHED"
    body = _body(route)
    assert body == {"visibility": "PUBLIC", "status": "PUBLISHED"}


@respx.mock
def test_delete_hits_brain_route():
    route = respx.delete(f"{PREFIX}/brains/b9").mock(return_value=httpx.Response(204))
    with client() as mm:
        out = mm.brains.delete("b9")
    assert out is None
    assert route.called


# ── async parity smoke ──────────────────────────────────────────────────────


async def test_async_brains_create_and_list():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/brains"):
            return httpx.Response(200, json={"id": "ab1"})
        if request.method == "GET" and request.url.path.endswith("/brains"):
            return httpx.Response(200, json={"data": [{"id": "ab1"}], "next": None, "previous": None})
        raise AssertionError("unexpected request")

    injected = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with AsyncMemMesh(api_key="sk", project_id=PROJ, http_client=injected) as mm:
        created = await mm.brains.create({"externalId": "x", "name": "X"})
        got = [b["id"] async for b in mm.brains.list()]
    assert created["id"] == "ab1"
    assert got == ["ab1"]
