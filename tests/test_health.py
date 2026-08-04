"""Request-shaping tests for the health vertical — record_biomarker,
record_demographics, record_condition (stored as /admin/memory facts) plus the
derived reads get_profile + get_cohort_risk. No live server (respx mocks)."""

import json

import httpx
import respx

from memmesh import AsyncMemMesh, MemMesh, subject

BASE = "https://app.memmesh.ai"
PROJ = "proj_test"
PREFIX = f"{BASE}/api/v1/projects/{PROJ}"

SUBJECT = subject("patient", "p-123")


def client() -> MemMesh:
    return MemMesh(api_key="sk-test", project_id=PROJ, max_retries=0)


def _body(route) -> dict:
    return json.loads(route.calls.last.request.content)


# ── record_biomarker ─────────────────────────────────────────────────────────


@respx.mock
def test_record_biomarker_posts_fact_to_admin_memory():
    route = respx.post(f"{PREFIX}/admin/memory").mock(
        return_value=httpx.Response(200, json={"id": "m1"})
    )
    with client() as mm:
        out = mm.health.record_biomarker(SUBJECT, "hba1c", 6.2, unit="%")
    assert out["id"] == "m1"
    body = _body(route)
    assert body["content"] == "hba1c = 6.2 %"
    assert body["type"] == "fact"
    assert body["scope"] == "project"
    assert body["category"] == "health"
    assert body["source"] == "sdk:health"
    assert body["metadata"]["subject"] == SUBJECT
    assert body["metadata"]["health"] == {"biomarker": "hba1c", "value": 6.2, "unit": "%"}


@respx.mock
def test_record_biomarker_omits_unit_and_carries_observed_at():
    route = respx.post(f"{PREFIX}/admin/memory").mock(
        return_value=httpx.Response(200, json={"id": "m2"})
    )
    with client() as mm:
        mm.health.record_biomarker(SUBJECT, "ldl", 130, observed_at="2026-01-02T00:00:00Z")
    body = _body(route)
    assert body["content"] == "ldl = 130"
    assert body["metadata"]["health"] == {
        "biomarker": "ldl",
        "value": 130,
        "observedAt": "2026-01-02T00:00:00Z",
    }


# ── record_demographics ──────────────────────────────────────────────────────


@respx.mock
def test_record_demographics_posts_demographic_metadata():
    route = respx.post(f"{PREFIX}/admin/memory").mock(
        return_value=httpx.Response(200, json={"id": "m3"})
    )
    demo = {"ageYears": 54, "sex": "female", "weightKg": 82, "heightCm": 170, "activity": "low"}
    with client() as mm:
        mm.health.record_demographics(SUBJECT, demo)
    body = _body(route)
    assert body["content"] == "Demographics update"
    assert body["category"] == "health"
    assert body["metadata"] == {"subject": SUBJECT, "demographic": demo}


# ── record_condition ─────────────────────────────────────────────────────────


@respx.mock
def test_record_condition_posts_icd10_diagnosis():
    route = respx.post(f"{PREFIX}/admin/memory").mock(
        return_value=httpx.Response(200, json={"id": "m4"})
    )
    cond = {"icd10": "I10", "status": "active"}
    with client() as mm:
        mm.health.record_condition(SUBJECT, cond)
    body = _body(route)
    assert body["content"] == "Diagnosis I10"
    assert body["metadata"] == {"subject": SUBJECT, "condition": cond}


# ── get_profile ──────────────────────────────────────────────────────────────


@respx.mock
def test_get_profile_posts_subject_to_lattice_health_profile():
    route = respx.post(f"{PREFIX}/lattice/health/profile").mock(
        return_value=httpx.Response(200, json={"subject": SUBJECT, "predictedConditions": []})
    )
    with client() as mm:
        out = mm.health.get_profile(SUBJECT)
    assert out["subject"] == SUBJECT
    assert _body(route) == {"subject": SUBJECT}


# ── get_cohort_risk ──────────────────────────────────────────────────────────


@respx.mock
def test_get_cohort_risk_includes_k_when_given():
    route = respx.post(f"{PREFIX}/lattice/health/cohort-risk").mock(
        return_value=httpx.Response(200, json={"subject": SUBJECT, "risks": []})
    )
    with client() as mm:
        mm.health.get_cohort_risk(SUBJECT, k=40)
    assert _body(route) == {"subject": SUBJECT, "k": 40}


@respx.mock
def test_get_cohort_risk_omits_k_when_absent():
    route = respx.post(f"{PREFIX}/lattice/health/cohort-risk").mock(
        return_value=httpx.Response(200, json={"subject": SUBJECT, "risks": []})
    )
    with client() as mm:
        mm.health.get_cohort_risk(SUBJECT)
    assert _body(route) == {"subject": SUBJECT}


# ── async parity smoke ───────────────────────────────────────────────────────


async def test_async_health_record_and_read():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/admin/memory"):
            return httpx.Response(200, json={"id": "am1"})
        if request.method == "POST" and request.url.path.endswith("/lattice/health/profile"):
            return httpx.Response(200, json={"subject": SUBJECT, "predictedConditions": []})
        raise AssertionError("unexpected request")

    injected = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with AsyncMemMesh(api_key="sk", project_id=PROJ, http_client=injected) as mm:
        rec = await mm.health.record_biomarker(SUBJECT, "glucose_fasting", 99, unit="mg/dL")
        prof = await mm.health.get_profile(SUBJECT)
    assert rec["id"] == "am1"
    assert prof["subject"] == SUBJECT
