"""Tests for the Phase 5 consent resource — opt_out, opt_in, get_status.

Consent is implemented CLIENT-SIDE over the memory CRUD surface: decisions are
written/read as ``type='consent'`` memory items. These tests exercise that
client-side logic (the supersede-then-create sequence, the read/filter path)
against respx mocks of the underlying ``/admin/memory`` routes."""

import json

import httpx
import respx

from memmesh import AsyncMemMesh, MemMesh, subject

BASE = "https://app.memmesh.ai"
PROJ = "proj_test"
PREFIX = f"{BASE}/api/v1/projects/{PROJ}"

SARAH = subject("contact", "sarah")


def client() -> MemMesh:
    return MemMesh(api_key="sk-test", project_id=PROJ, max_retries=0)


def _body(route) -> dict:
    return json.loads(route.calls.last.request.content)


# ── opt_out (supersede prior + create a consent memory) ─────────────────────


@respx.mock
def test_opt_out_supersedes_prior_then_creates_consent_memory():
    prior = {
        "id": "old-consent",
        "type": "consent",
        "metadata": {"subject": {"kind": "contact", "externalId": "sarah"}, "optedOut": False},
        "created": "2026-01-01T00:00:00Z",
    }
    # 1) findActiveConsent -> list scans for the prior record
    list_route = respx.get(f"{PREFIX}/admin/memory").mock(
        return_value=httpx.Response(200, json=[prior])
    )
    # 2) supersede -> hard-delete the prior row
    delete_route = respx.delete(f"{PREFIX}/admin/memory/old-consent").mock(
        return_value=httpx.Response(204)
    )
    # 3) create the new active consent memory
    create_route = respx.post(f"{PREFIX}/admin/memory").mock(
        return_value=httpx.Response(200, json={"id": "new-consent"})
    )

    with client() as mm:
        status = mm.consent.opt_out(SARAH, reason="GDPR Art. 17 request 2026-05-25")

    assert list_route.called
    assert delete_route.called  # prior superseded
    # the created memory is a type=consent, importance=10, category=consent item
    body = _body(create_route)
    assert body["content"] == "[consent] contact:sarah opted out"
    assert body["type"] == "consent"
    assert body["scope"] == "project"
    assert body["importance"] == 10
    assert body["category"] == "consent"
    assert body["metadata"]["subject"] == {"kind": "contact", "externalId": "sarah"}
    assert body["metadata"]["optedOut"] is True
    assert body["metadata"]["reason"] == "GDPR Art. 17 request 2026-05-25"
    assert body["metadata"]["recordKind"] == "consent"
    # returned status
    assert status["optedOut"] is True
    assert status["memoryId"] == "new-consent"
    assert status["optedOutAt"] is not None
    assert status["reason"] == "GDPR Art. 17 request 2026-05-25"


# ── get_status (read/filter path, incl. default when no record) ─────────────


@respx.mock
def test_get_status_reads_active_record_and_defaults_when_absent():
    active = {
        "id": "c-active",
        "type": "consent",
        "metadata": {
            "subject": {"kind": "contact", "externalId": "sarah"},
            "optedOut": True,
            "optedOutAt": "2026-05-25T12:00:00Z",
            "reason": "art17",
        },
        "created": "2026-05-25T12:00:00Z",
    }
    # a non-consent item and a consent item for a different subject must be ignored
    noise = [
        {"id": "n1", "type": "event", "metadata": {}},
        {
            "id": "n2",
            "type": "consent",
            "metadata": {"subject": {"kind": "contact", "externalId": "someone-else"}},
        },
        active,
    ]
    route = respx.get(f"{PREFIX}/admin/memory").mock(return_value=httpx.Response(200, json=noise))

    with client() as mm:
        status = mm.consent.get_status(SARAH)
    assert status == {
        "subject": {"kind": "contact", "externalId": "sarah"},
        "optedOut": True,
        "optedOutAt": "2026-05-25T12:00:00Z",
        "reason": "art17",
        "memoryId": "c-active",
    }
    # limit is capped at 500 for the consent scan
    assert route.calls.last.request.url.params["limit"] == "500"

    # No record for the subject -> default opted-in status
    route.mock(return_value=httpx.Response(200, json=[]))
    with client() as mm:
        default = mm.consent.get_status(SARAH)
    assert default == {
        "subject": {"kind": "contact", "externalId": "sarah"},
        "optedOut": False,
        "optedOutAt": None,
        "reason": None,
        "memoryId": None,
    }


# ── opt_in (async; no prior -> no delete, creates opted-in record) ──────────


async def test_async_opt_in_creates_record_without_prior():
    seen = {"deletes": 0, "creates": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path.endswith("/admin/memory"):
            return httpx.Response(200, json=[])  # no prior consent record
        if request.method == "DELETE":
            seen["deletes"] += 1
            return httpx.Response(204)
        if request.method == "POST" and path.endswith("/admin/memory"):
            seen["creates"] += 1
            body = json.loads(request.content)
            assert body["content"] == "[consent] contact:sarah opted in"
            assert body["metadata"]["optedOut"] is False
            assert body["metadata"]["optedOutAt"] is None
            return httpx.Response(200, json={"id": "in-consent"})
        raise AssertionError(f"unexpected {request.method} {path}")

    injected = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with AsyncMemMesh(api_key="sk", project_id=PROJ, http_client=injected) as mm:
        status = await mm.consent.opt_in(SARAH)

    assert seen["deletes"] == 0  # nothing to supersede
    assert seen["creates"] == 1
    assert status == {
        "subject": {"kind": "contact", "externalId": "sarah"},
        "optedOut": False,
        "optedOutAt": None,
        "reason": None,
        "memoryId": "in-consent",
    }
