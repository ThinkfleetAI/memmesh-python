"""Request-shaping tests for the knowledge-graph resource and the identity
provenance now carried by raw-text observe. No live server (respx mocks)."""

import json

import httpx
import pytest
import respx

from memmesh import AsyncMemMesh, MemMesh

BASE = "https://app.memmesh.ai"
PROJ = "proj_test"
PREFIX = f"{BASE}/api/v1/projects/{PROJ}"


def client() -> MemMesh:
    return MemMesh(api_key="sk-test", project_id=PROJ, max_retries=0)


def _body(route) -> dict:
    return json.loads(route.calls.last.request.content)


# ── graph reads ─────────────────────────────────────────────────────────────


@respx.mock
def test_stats_hits_graph_stats():
    respx.get(f"{PREFIX}/admin/memory/graph/stats").mock(
        return_value=httpx.Response(
            200,
            json={
                "entityCount": 12,
                "edgeCount": 34,
                "memoriesWithEdges": 7,
                "retiredEntities": 0,
                "retiredEdges": 1,
                "entitiesByType": {"person": 3},
                "extraction": {"platformEnabled": True, "projectEnabled": False},
            },
        )
    )
    with client() as mm:
        out = mm.memory.graph.stats()
    assert out["entityCount"] == 12
    assert out["edgeCount"] == 34
    assert out["extraction"]["projectEnabled"] is False


@respx.mock
def test_list_entities_passes_filters_as_query_params():
    route = respx.get(f"{PREFIX}/admin/memory/entities").mock(
        return_value=httpx.Response(200, json=[{"id": "e1", "canonicalName": "Sarah"}])
    )
    with client() as mm:
        out = mm.memory.graph.list_entities(type="person", search="sar", limit=5)
    assert out[0]["canonicalName"] == "Sarah"
    q = route.calls.last.request.url.params
    assert q["type"] == "person"
    assert q["search"] == "sar"
    assert q["limit"] == "5"


@respx.mock
def test_list_entities_omits_unset_filters():
    route = respx.get(f"{PREFIX}/admin/memory/entities").mock(
        return_value=httpx.Response(200, json=[])
    )
    with client() as mm:
        mm.memory.graph.list_entities()
    assert str(route.calls.last.request.url.params) == ""


@respx.mock
def test_get_entity_returns_entity_with_edges():
    respx.get(f"{PREFIX}/admin/memory/entities/e1").mock(
        return_value=httpx.Response(
            200, json={"entity": {"id": "e1"}, "edges": [{"id": "g1"}]}
        )
    )
    with client() as mm:
        out = mm.memory.graph.get_entity("e1")
    assert out["entity"]["id"] == "e1"
    assert len(out["edges"]) == 1


@respx.mock
def test_list_edges_returns_hydrated_traversal_shape():
    """The read routes hydrate both ends — `subject`/`object` are entity dicts,
    not ids, and there is no `subjectId` on the wire at all."""
    route = respx.get(f"{PREFIX}/admin/memory/graph/edges").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "g1",
                    "subject": {"id": "e1", "canonicalName": "NVIDIA CORP"},
                    "predicate": "reported_metric",
                    "object": {"id": "e2", "canonicalName": "Cost of Revenue"},
                    "objectLiteral": None,
                    "weight": 0.85,
                    "hop": 0,
                }
            ],
        )
    )
    with client() as mm:
        out = mm.memory.graph.list_edges(limit=100)
    assert out[0]["subject"]["canonicalName"] == "NVIDIA CORP"
    assert out[0]["object"]["canonicalName"] == "Cost of Revenue"
    assert out[0]["hop"] == 0
    assert "subjectId" not in out[0]
    assert route.calls.last.request.url.params["limit"] == "100"


@respx.mock
def test_traverse_posts_entity_id_and_predicates():
    route = respx.post(f"{PREFIX}/admin/memory/graph/traverse").mock(
        return_value=httpx.Response(200, json=[{"id": "g1"}])
    )
    with client() as mm:
        mm.memory.graph.traverse("e1", hops=2, predicates=["member_of", "led_by"])
    assert _body(route) == {
        "entityId": "e1",
        "hops": 2,
        "predicates": ["member_of", "led_by"],
    }


@respx.mock
def test_traverse_omits_unset_options():
    route = respx.post(f"{PREFIX}/admin/memory/graph/traverse").mock(
        return_value=httpx.Response(200, json=[])
    )
    with client() as mm:
        mm.memory.graph.traverse("e1")
    assert _body(route) == {"entityId": "e1"}


# ── observe provenance ──────────────────────────────────────────────────────


@respx.mock
def test_observe_text_forwards_identity_fields():
    route = respx.post(f"{PREFIX}/memory/observe").mock(
        return_value=httpx.Response(200, json={"saved": [], "candidateCount": 0})
    )
    with client() as mm:
        mm.memory.observe(
            text="I just moved to Denver.",
            user_id="user-123",
            agent_id="agent-9",
            session_id="thread-456",
        )
    assert _body(route) == {
        "text": "I just moved to Denver.",
        "role": "user",
        "userId": "user-123",
        "agentId": "agent-9",
        "sessionId": "thread-456",
    }


@respx.mock
def test_observe_text_omits_identity_when_unset():
    """An older call site must produce the same body it always did — the fields
    are omitted, not sent as null."""
    route = respx.post(f"{PREFIX}/memory/observe").mock(
        return_value=httpx.Response(200, json={"saved": [], "candidateCount": 0})
    )
    with client() as mm:
        mm.memory.observe(text="hello")
    assert _body(route) == {"text": "hello", "role": "user"}


# ── async parity ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_async_graph_stats_and_observe_identity():
    respx.get(f"{PREFIX}/admin/memory/graph/stats").mock(
        return_value=httpx.Response(200, json={"entityCount": 1, "edgeCount": 2})
    )
    route = respx.post(f"{PREFIX}/memory/observe").mock(
        return_value=httpx.Response(200, json={"saved": [], "candidateCount": 0})
    )
    async with AsyncMemMesh(api_key="sk-test", project_id=PROJ, max_retries=0) as mm:
        stats = await mm.memory.graph.stats()
        await mm.memory.observe(text="hi", user_id="u1", session_id="s1")
    assert stats["entityCount"] == 1
    body = _body(route)
    assert body["userId"] == "u1"
    assert body["sessionId"] == "s1"
