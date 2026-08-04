"""Request-shaping tests for the alerts resource — list, get, create, update,
delete, enable, disable, list_fires. No live server (respx mocks)."""

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


# ── list ─────────────────────────────────────────────────────────────────────


@respx.mock
def test_list_hits_alerts_route():
    route = respx.get(f"{PREFIX}/memory-alerts").mock(
        return_value=httpx.Response(200, json=[{"id": "a1", "enabled": True}])
    )
    with client() as mm:
        out = mm.alerts.list()
    assert out == [{"id": "a1", "enabled": True}]
    assert route.called


# ── get ──────────────────────────────────────────────────────────────────────


@respx.mock
def test_get_hits_alert_route():
    respx.get(f"{PREFIX}/memory-alerts/a1").mock(
        return_value=httpx.Response(200, json={"id": "a1"})
    )
    with client() as mm:
        out = mm.alerts.get("a1")
    assert out["id"] == "a1"


# ── create ───────────────────────────────────────────────────────────────────


@respx.mock
def test_create_posts_full_body():
    route = respx.post(f"{PREFIX}/memory-alerts").mock(
        return_value=httpx.Response(200, json={"id": "a1"})
    )
    body = {
        "name": "VIP at risk",
        "trigger": {"kind": "engine-event", "eventTypes": ["risk.fired"]},
        "filter": {"metadataMatch": {"riskKind": "rfm_at_risk_high_value"}},
        "notify": [{"kind": "webhook", "url": "https://hooks.slack.com/x"}],
        "throttle": {"dedupOn": "subject", "cooldownMinutes": 60},
    }
    with client() as mm:
        out = mm.alerts.create(body)
    assert out["id"] == "a1"
    assert _body(route) == body


# ── update ───────────────────────────────────────────────────────────────────


@respx.mock
def test_update_patches_alert():
    route = respx.patch(f"{PREFIX}/memory-alerts/a1").mock(
        return_value=httpx.Response(200, json={"id": "a1", "name": "renamed"})
    )
    with client() as mm:
        out = mm.alerts.update("a1", {"name": "renamed"})
    assert out["name"] == "renamed"
    assert _body(route) == {"name": "renamed"}


# ── delete ───────────────────────────────────────────────────────────────────


@respx.mock
def test_delete_hits_alert_route():
    route = respx.delete(f"{PREFIX}/memory-alerts/a1").mock(
        return_value=httpx.Response(204)
    )
    with client() as mm:
        out = mm.alerts.delete("a1")
    assert out is None
    assert route.called


# ── enable / disable ─────────────────────────────────────────────────────────


@respx.mock
def test_enable_patches_enabled_true():
    route = respx.patch(f"{PREFIX}/memory-alerts/a1").mock(
        return_value=httpx.Response(200, json={"id": "a1", "enabled": True})
    )
    with client() as mm:
        out = mm.alerts.enable("a1")
    assert out["enabled"] is True
    assert _body(route) == {"enabled": True}


@respx.mock
def test_disable_patches_enabled_false():
    route = respx.patch(f"{PREFIX}/memory-alerts/a1").mock(
        return_value=httpx.Response(200, json={"id": "a1", "enabled": False})
    )
    with client() as mm:
        out = mm.alerts.disable("a1")
    assert out["enabled"] is False
    assert _body(route) == {"enabled": False}


# ── list_fires ───────────────────────────────────────────────────────────────


@respx.mock
def test_list_fires_hits_fires_route():
    route = respx.get(f"{PREFIX}/memory-alerts/a1/fires").mock(
        return_value=httpx.Response(200, json=[{"id": "f1", "alertRuleId": "a1"}])
    )
    with client() as mm:
        out = mm.alerts.list_fires("a1")
    assert out[0]["alertRuleId"] == "a1"
    assert route.called


# ── async parity smoke ───────────────────────────────────────────────────────


async def test_async_alerts_create_and_enable():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/memory-alerts"):
            return httpx.Response(200, json={"id": "a9"})
        if request.method == "PATCH":
            return httpx.Response(200, json={"id": "a9", "enabled": False})
        return httpx.Response(200, json={})

    injected = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with AsyncMemMesh(api_key="sk", project_id=PROJ, http_client=injected) as mm:
        created = await mm.alerts.create(
            {"name": "n", "trigger": {"kind": "engine-event", "eventTypes": ["x"]}, "notify": []}
        )
        disabled = await mm.alerts.disable("a9")
    assert created["id"] == "a9"
    assert disabled["enabled"] is False
