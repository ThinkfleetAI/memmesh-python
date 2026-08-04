"""Request-shaping tests for the compliance vertical — export_subject,
hard_delete_subject, list_audit_events (querystring), list_packs,
list_project_packs, upsert_project_pack, remove_project_pack. No live server
(respx mocks)."""

import json

import httpx
import respx

from memmesh import AsyncMemMesh, MemMesh

BASE = "https://app.memmesh.ai"
PROJ = "proj_test"
PREFIX = f"{BASE}/api/v1/projects/{PROJ}"

SUBJECT = {"kind": "contact", "externalId": "sarah-pizza"}


def client() -> MemMesh:
    return MemMesh(api_key="sk-test", project_id=PROJ, max_retries=0)


def _body(route) -> dict:
    return json.loads(route.calls.last.request.content)


# ── export_subject ───────────────────────────────────────────────────────────


@respx.mock
def test_export_subject_posts_subject():
    route = respx.post(f"{PREFIX}/memory-compliance/export").mock(
        return_value=httpx.Response(200, json={"subject": SUBJECT, "counts": {}})
    )
    with client() as mm:
        out = mm.compliance.export_subject(SUBJECT)
    assert out["subject"] == SUBJECT
    assert _body(route) == {"subject": SUBJECT}


# ── hard_delete_subject ──────────────────────────────────────────────────────


@respx.mock
def test_hard_delete_subject_includes_reason_and_dry_run():
    route = respx.post(f"{PREFIX}/memory-compliance/hard-delete").mock(
        return_value=httpx.Response(200, json={"subject": SUBJECT, "memoriesDeleted": 0})
    )
    with client() as mm:
        mm.compliance.hard_delete_subject(SUBJECT, reason="GDPR Art. 17 case A", dry_run=True)
    assert _body(route) == {
        "subject": SUBJECT,
        "reason": "GDPR Art. 17 case A",
        "dryRun": True,
    }


@respx.mock
def test_hard_delete_subject_omits_dry_run_when_absent():
    route = respx.post(f"{PREFIX}/memory-compliance/hard-delete").mock(
        return_value=httpx.Response(200, json={"subject": SUBJECT, "memoriesDeleted": 3})
    )
    with client() as mm:
        mm.compliance.hard_delete_subject(SUBJECT, reason="case B")
    assert _body(route) == {"subject": SUBJECT, "reason": "case B"}


# ── list_audit_events ────────────────────────────────────────────────────────


@respx.mock
def test_list_audit_events_builds_querystring():
    route = respx.get(f"{PREFIX}/memory-compliance/audit").mock(
        return_value=httpx.Response(200, json=[{"id": "e1"}])
    )
    with client() as mm:
        out = mm.compliance.list_audit_events(
            subject=SUBJECT,
            actor="svc-key-1",
            event_types=["read.context", "read.export"],
            since="2026-05-01T00:00:00Z",
            limit=50,
        )
    assert out[0]["id"] == "e1"
    params = route.calls.last.request.url.params
    assert params["subjectKind"] == "contact"
    assert params["subjectExternalId"] == "sarah-pizza"
    assert params["actor"] == "svc-key-1"
    assert params["eventTypes"] == "read.context,read.export"
    assert params["since"] == "2026-05-01T00:00:00Z"
    assert params["limit"] == "50"


@respx.mock
def test_list_audit_events_omits_empty_filters():
    route = respx.get(f"{PREFIX}/memory-compliance/audit").mock(
        return_value=httpx.Response(200, json=[])
    )
    with client() as mm:
        mm.compliance.list_audit_events()
    # None-valued params are stripped by the transport; no eventTypes key either.
    assert dict(route.calls.last.request.url.params) == {}


# ── list_packs ───────────────────────────────────────────────────────────────


@respx.mock
def test_list_packs_hits_packs_route():
    route = respx.get(f"{PREFIX}/memory-compliance/packs").mock(
        return_value=httpx.Response(200, json=[{"id": "hipaa", "version": "1.0.0"}])
    )
    with client() as mm:
        out = mm.compliance.list_packs()
    assert out[0]["id"] == "hipaa"
    assert route.called


# ── list_project_packs ───────────────────────────────────────────────────────


@respx.mock
def test_list_project_packs_hits_enablement_route():
    route = respx.get(f"{PREFIX}/memory-compliance-packs").mock(
        return_value=httpx.Response(200, json=[{"id": "pp1", "packId": "@thinkfleet/pack-healthcare"}])
    )
    with client() as mm:
        out = mm.compliance.list_project_packs()
    assert out[0]["packId"] == "@thinkfleet/pack-healthcare"
    assert route.called


# ── upsert_project_pack ──────────────────────────────────────────────────────


@respx.mock
def test_upsert_project_pack_posts_body_with_config():
    route = respx.post(f"{PREFIX}/memory-compliance-packs").mock(
        return_value=httpx.Response(200, json={"id": "pp1", "enabled": True})
    )
    with client() as mm:
        mm.compliance.upsert_project_pack(
            pack_id="@thinkfleet/pack-healthcare",
            enabled=True,
            config={"deidentificationMode": "safe-harbor"},
        )
    assert _body(route) == {
        "packId": "@thinkfleet/pack-healthcare",
        "enabled": True,
        "config": {"deidentificationMode": "safe-harbor"},
    }


@respx.mock
def test_upsert_project_pack_omits_config_when_absent():
    route = respx.post(f"{PREFIX}/memory-compliance-packs").mock(
        return_value=httpx.Response(200, json={"id": "pp2", "enabled": False})
    )
    with client() as mm:
        mm.compliance.upsert_project_pack(pack_id="gdpr", enabled=False)
    assert _body(route) == {"packId": "gdpr", "enabled": False}


# ── remove_project_pack ──────────────────────────────────────────────────────


@respx.mock
def test_remove_project_pack_url_encodes_pack_id():
    route = respx.delete(
        f"{PREFIX}/memory-compliance-packs/%40thinkfleet%2Fpack-healthcare"
    ).mock(return_value=httpx.Response(204))
    with client() as mm:
        out = mm.compliance.remove_project_pack("@thinkfleet/pack-healthcare")
    assert out is None
    assert route.called


# ── async parity smoke ───────────────────────────────────────────────────────


async def test_async_compliance_export_and_remove():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/memory-compliance/export"):
            return httpx.Response(200, json={"subject": SUBJECT, "counts": {}})
        if request.method == "DELETE" and "/memory-compliance-packs/" in request.url.path:
            return httpx.Response(204)
        raise AssertionError("unexpected request")

    injected = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with AsyncMemMesh(api_key="sk", project_id=PROJ, http_client=injected) as mm:
        bundle = await mm.compliance.export_subject(SUBJECT)
        removed = await mm.compliance.remove_project_pack("gdpr")
    assert bundle["subject"] == SUBJECT
    assert removed is None
