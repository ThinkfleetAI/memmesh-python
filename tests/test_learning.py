"""Request-shaping tests for the Phase 4 learning + behaviors resources —
record_decision, record_outcome, get_outcomes, get_effectiveness, and
behaviors.discover — plus the memory.consolidate path fix. No live server
(respx mocks)."""

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


# ── learning.record_decision ─────────────────────────────────────────────────


@respx.mock
def test_record_decision_posts_full_body_and_unwraps():
    route = respx.post(f"{PREFIX}/lattice/decisions").mock(
        return_value=httpx.Response(200, json={"decision": {"decisionId": "dec_1"}})
    )
    with client() as mm:
        out = mm.learning.record_decision(
            subject("contact", "sarah"),
            actor="policy:winback-v1",
            decision_type="offer",
            action_type="apply_discount",
            informed_by=[{"memoryId": "pat_1", "refType": "pattern"}],
            params={"pct": "15"},
            idempotency_key="k-1",
        )
    assert out == {"decision": {"decisionId": "dec_1"}}
    body = _body(route)
    assert body["subject"] == {"kind": "contact", "externalId": "sarah"}
    assert body["actor"] == "policy:winback-v1"
    assert body["decisionType"] == "offer"
    assert body["actionType"] == "apply_discount"
    assert body["informedBy"] == [{"memoryId": "pat_1", "refType": "pattern"}]
    assert body["params"] == {"pct": "15"}
    assert body["idempotencyKey"] == "k-1"
    # unset optionals must not be sent
    assert "policy" not in body
    assert "status" not in body


# ── learning.record_outcome ──────────────────────────────────────────────────


@respx.mock
def test_record_outcome_posts_body_and_returns_updates():
    route = respx.post(f"{PREFIX}/lattice/outcomes").mock(
        return_value=httpx.Response(
            200,
            json={"outcomeId": "out_1", "updates": [{"refId": "pat_1", "posteriorConfidence": 0.7}]},
        )
    )
    with client() as mm:
        out = mm.learning.record_outcome(
            "dec_1",
            result="success",
            outcome_type="conversion",
            reward=84.0,
            attribution_window_secs=3600,
        )
    assert out["outcomeId"] == "out_1"
    assert out["updates"][0]["posteriorConfidence"] == 0.7
    body = _body(route)
    assert body == {
        "decisionId": "dec_1",
        "result": "success",
        "outcomeType": "conversion",
        "reward": 84.0,
        "attributionWindowSecs": 3600,
    }


# ── learning.get_outcomes ────────────────────────────────────────────────────


@respx.mock
def test_get_outcomes_splits_subject_and_unwraps_list():
    route = respx.get(f"{PREFIX}/lattice/outcomes").mock(
        return_value=httpx.Response(200, json={"outcomes": [{"outcomeId": "out_1"}]})
    )
    with client() as mm:
        out = mm.learning.get_outcomes(
            subject=subject("contact", "sarah"), decision_type="offer", limit=25
        )
    assert out == [{"outcomeId": "out_1"}]
    params = route.calls.last.request.url.params
    assert params["subjectKind"] == "contact"
    assert params["subjectExternalId"] == "sarah"
    assert params["decisionType"] == "offer"
    assert params["limit"] == "25"


# ── learning.get_effectiveness ───────────────────────────────────────────────


@respx.mock
def test_get_effectiveness_passes_params_and_unwraps_rows():
    route = respx.get(f"{PREFIX}/lattice/effectiveness").mock(
        return_value=httpx.Response(200, json={"rows": [{"groupKey": "apply_discount", "n": 12}]})
    )
    with client() as mm:
        out = mm.learning.get_effectiveness(group_by="action_type", min_support=5)
    assert out == [{"groupKey": "apply_discount", "n": 12}]
    params = route.calls.last.request.url.params
    assert params["groupBy"] == "action_type"
    assert params["minSupport"] == "5"


# ── behaviors.discover ───────────────────────────────────────────────────────


@respx.mock
def test_discover_posts_tuning_body():
    route = respx.post(f"{PREFIX}/lattice/discover").mock(
        return_value=httpx.Response(200, json={"behaviors": [], "subjectsAnalyzed": 42})
    )
    with client() as mm:
        out = mm.behaviors.discover(
            sim_threshold=0.8, min_cluster_size=5, min_stability=0.65, max_members=25
        )
    assert out == {"behaviors": [], "subjectsAnalyzed": 42}
    body = _body(route)
    assert body == {
        "simThreshold": 0.8,
        "minClusterSize": 5,
        "minStability": 0.65,
        "maxMembers": 25,
    }


@respx.mock
def test_discover_defaults_to_empty_body():
    route = respx.post(f"{PREFIX}/lattice/discover").mock(
        return_value=httpx.Response(200, json={"behaviors": []})
    )
    with client() as mm:
        mm.behaviors.discover()
    assert _body(route) == {}


# ── memory.consolidate path fix ──────────────────────────────────────────────


@respx.mock
def test_consolidate_hits_llm_consolidate_route():
    route = respx.post(f"{PREFIX}/admin/memory/llm-consolidate").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    with client() as mm:
        out = mm.memory.consolidate(subject=subject("contact", "sarah"), window_days=30)
    assert out == {"ok": True}
    assert route.called
    body = _body(route)
    assert body == {"subject": {"kind": "contact", "externalId": "sarah"}, "windowDays": 30}


# ── async parity smoke ───────────────────────────────────────────────────────


async def test_async_learning_and_behaviors():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/lattice/decisions"):
            return httpx.Response(200, json={"decision": {"decisionId": "dec_9"}})
        if request.url.path.endswith("/lattice/outcomes"):
            return httpx.Response(200, json={"outcomes": [{"outcomeId": "out_9"}]})
        if request.url.path.endswith("/lattice/discover"):
            return httpx.Response(200, json={"behaviors": [], "subjectsAnalyzed": 1})
        if request.url.path.endswith("/admin/memory/llm-consolidate"):
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, json={})

    injected = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with AsyncMemMesh(api_key="sk", project_id=PROJ, http_client=injected) as mm:
        dec = await mm.learning.record_decision(subject("contact", "s1"), action_type="ping")
        outs = await mm.learning.get_outcomes()
        disc = await mm.behaviors.discover()
        cons = await mm.memory.consolidate()
    assert dec["decision"]["decisionId"] == "dec_9"
    assert outs == [{"outcomeId": "out_9"}]
    assert disc["subjectsAnalyzed"] == 1
    assert cons["ok"] is True
