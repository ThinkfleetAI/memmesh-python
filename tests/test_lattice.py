"""Request-shaping tests for the Phase 3 lattice methods — extract_patterns,
get_pattern, list_patterns, get_context, run_monitor_tick, get_monitor_status,
predict_target, get_cohort, and estimate. No live server (respx mocks)."""

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


# ── extract_patterns ────────────────────────────────────────────────────────


@respx.mock
def test_extract_patterns_posts_full_body():
    route = respx.post(f"{PREFIX}/lattice/patterns/extract").mock(
        return_value=httpx.Response(200, json={"patternsCreated": 3})
    )
    with client() as mm:
        out = mm.lattice.extract_patterns(
            contact_id="c1", window_days=30, force=True, source="contact_events"
        )
    assert out == {"patternsCreated": 3}
    body = _body(route)
    assert body == {
        "contactId": "c1",
        "windowDays": 30,
        "force": True,
        "source": "contact_events",
    }


@respx.mock
def test_extract_patterns_defaults_to_empty_body():
    route = respx.post(f"{PREFIX}/lattice/patterns/extract").mock(
        return_value=httpx.Response(200, json={})
    )
    with client() as mm:
        mm.lattice.extract_patterns()
    assert _body(route) == {}


# ── get_pattern ─────────────────────────────────────────────────────────────


@respx.mock
def test_get_pattern_hits_pattern_route():
    route = respx.get(f"{PREFIX}/lattice/patterns/pat_1").mock(
        return_value=httpx.Response(200, json={"id": "pat_1", "active": True})
    )
    with client() as mm:
        out = mm.lattice.get_pattern("pat_1")
    assert out["id"] == "pat_1"
    assert route.called


# ── list_patterns ───────────────────────────────────────────────────────────


@respx.mock
def test_list_patterns_passes_params_and_path():
    route = respx.get(f"{PREFIX}/lattice/contacts/c1/patterns").mock(
        return_value=httpx.Response(200, json={"data": [], "nextCursor": None})
    )
    with client() as mm:
        out = mm.lattice.list_patterns("c1", active_only=False, limit=10, cursor="cur_2")
    assert out == {"data": [], "nextCursor": None}
    params = route.calls.last.request.url.params
    assert params["activeOnly"] == "false"
    assert params["limit"] == "10"
    assert params["cursor"] == "cur_2"


# ── get_context ─────────────────────────────────────────────────────────────


@respx.mock
def test_get_context_passes_bitemporal_params():
    route = respx.get(f"{PREFIX}/lattice/contacts/c1/context").mock(
        return_value=httpx.Response(200, json={"contactId": "c1"})
    )
    with client() as mm:
        out = mm.lattice.get_context(
            "c1", as_of="2026-01-01T00:00:00Z", events_limit=5, memories_limit=7, graph_hops=2
        )
    assert out["contactId"] == "c1"
    params = route.calls.last.request.url.params
    assert params["asOf"] == "2026-01-01T00:00:00Z"
    assert params["eventsLimit"] == "5"
    assert params["memoriesLimit"] == "7"
    assert params["graphHops"] == "2"


# ── run_monitor_tick ────────────────────────────────────────────────────────


@respx.mock
def test_run_monitor_tick_posts_empty_body():
    route = respx.post(f"{PREFIX}/lattice/monitor/tick").mock(
        return_value=httpx.Response(200, json={"patternsChecked": 4})
    )
    with client() as mm:
        out = mm.lattice.run_monitor_tick()
    assert out["patternsChecked"] == 4
    assert _body(route) == {}


# ── get_monitor_status ──────────────────────────────────────────────────────


@respx.mock
def test_get_monitor_status_hits_status_route():
    respx.get(f"{PREFIX}/lattice/monitor/status").mock(
        return_value=httpx.Response(200, json={"patternsDue": 2, "lastTickAt": None})
    )
    with client() as mm:
        out = mm.lattice.get_monitor_status()
    assert out["patternsDue"] == 2


# ── predict_target ──────────────────────────────────────────────────────────


@respx.mock
def test_predict_target_sends_target_and_returns_estimate():
    route = respx.post(f"{PREFIX}/lattice/predict").mock(
        return_value=httpx.Response(
            200,
            json={
                "targetPrediction": {"probability": 0.8, "abstained": False},
            },
        )
    )
    with client() as mm:
        out = mm.lattice.predict_target(
            subject("customer", "acct-42"),
            {"kind": "event_occurrence", "eventType": "order_placed"},
            horizon_days=90,
        )
    assert out == {"probability": 0.8, "abstained": False}
    body = _body(route)
    assert body["subject"] == {"kind": "customer", "externalId": "acct-42"}
    assert body["horizonDays"] == 90
    assert body["target"] == {"kind": "event_occurrence", "eventType": "order_placed"}


@respx.mock
def test_predict_target_synthesizes_abstention_when_missing():
    respx.post(f"{PREFIX}/lattice/predict").mock(
        return_value=httpx.Response(200, json={"abstentionReason": "no history"})
    )
    with client() as mm:
        out = mm.lattice.predict_target(
            subject("customer", "acct-99"),
            {"kind": "numeric", "attributeKey": "order_total"},
        )
    assert out["abstained"] is True
    assert out["abstentionReason"] == "no history"
    assert out["targetKind"] == "numeric"
    assert out["eventType"] == "order_total"  # falls back to attributeKey


# ── get_cohort ──────────────────────────────────────────────────────────────


@respx.mock
def test_get_cohort_posts_body():
    route = respx.post(f"{PREFIX}/lattice/cohort").mock(
        return_value=httpx.Response(200, json={"members": []})
    )
    with client() as mm:
        out = mm.lattice.get_cohort(subject("contact", "sarah"), k=10, min_similarity=0.5)
    assert out == {"members": []}
    body = _body(route)
    assert body["subject"] == {"kind": "contact", "externalId": "sarah"}
    assert body["k"] == 10
    assert body["minSimilarity"] == 0.5


# ── estimate ────────────────────────────────────────────────────────────────


@respx.mock
def test_estimate_posts_estimator_body():
    route = respx.post(f"{PREFIX}/lattice/estimate").mock(
        return_value=httpx.Response(200, json={"ok": True, "value": 41.2})
    )
    with client() as mm:
        out = mm.lattice.estimate(subject("patient", "p-123"), "phenoage", persist=True)
    assert out["value"] == 41.2
    body = _body(route)
    assert body == {
        "subject": {"kind": "patient", "externalId": "p-123"},
        "estimatorId": "phenoage",
        "persist": True,
    }


# ── predict alignment (general pattern-projection mode) ──────────────────────


@respx.mock
def test_predict_projection_mode_omits_target():
    route = respx.post(f"{PREFIX}/lattice/predict").mock(
        return_value=httpx.Response(200, json={"predictions": []})
    )
    with client() as mm:
        mm.lattice.predict(subject("contact", "sarah"), horizon_days=30, limit=5, min_confidence=0.6)
    body = _body(route)
    assert body["horizonDays"] == 30
    assert body["limit"] == 5
    assert body["minConfidence"] == 0.6
    assert "target" not in body


# ── async parity smoke ──────────────────────────────────────────────────────


async def test_async_get_pattern_and_estimate():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/lattice/patterns/pat_9"):
            return httpx.Response(200, json={"id": "pat_9"})
        return httpx.Response(200, json={"ok": True})

    injected = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with AsyncMemMesh(api_key="sk", project_id=PROJ, http_client=injected) as mm:
        pat = await mm.lattice.get_pattern("pat_9")
        est = await mm.lattice.estimate(subject("patient", "p1"), "phenoage")
    assert pat["id"] == "pat_9"
    assert est["ok"] is True


async def test_async_predict_target_synthesizes_abstention():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    injected = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with AsyncMemMesh(api_key="sk", project_id=PROJ, http_client=injected) as mm:
        out = await mm.lattice.predict_target(
            subject("customer", "acct-1"),
            {"kind": "anomaly", "attributeKey": "resting_hr"},
        )
    assert out["abstained"] is True
    assert out["targetKind"] == "anomaly"
