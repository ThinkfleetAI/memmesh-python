"""Health resource — biological ("health") age + condition prediction.

Health data is just memory data: you record biomarkers, demographics, and
ICD-10 diagnoses as memory items, and the engine derives a biological age
(PhenoAge core + composite adjustments) and condition predictions (biomarkers
trending toward / above clinical thresholds), plus cohort base rates ("of
patients like this one, X% have Y").

You decide where the data originates — EHR feed, document extraction, wearable,
manual entry. The SDK only gives you the typed way in and out.

Requires the ``@thinkfleet/pack-healthcare`` pack enabled on the project; the
read methods return FAILED_PRECONDITION otherwise. Recorded items are stored as
non-activity ``fact`` memories, so they feed the health engine without being
mined as behavioral patterns. Mirrors ``thinkfleet-memory-sdk``'s
``resources/health.ts``.
"""

from __future__ import annotations

from typing import Any, Optional

from ..types import (
    Biomarker,
    CohortHealthRisk,
    ConditionInput,
    DemographicsInput,
    HealthProfile,
    MemoryItem,
    MemoryScope,
    MemoryType,
    Subject,
    enum_value,
)


def _biomarker_body(
    subject: Subject,
    biomarker: str,
    value: float,
    unit: Optional[str],
    observed_at: Optional[str],
) -> dict:
    health: dict = {"biomarker": biomarker, "value": value}
    if unit is not None:
        health["unit"] = unit
    if observed_at is not None:
        health["observedAt"] = observed_at
    content = f"{biomarker} = {value}" + (f" {unit}" if unit else "")
    return {
        "content": content,
        "type": enum_value(MemoryType.FACT),
        "scope": enum_value(MemoryScope.PROJECT),
        "category": "health",
        "source": "sdk:health",
        "metadata": {"subject": subject, "health": health},
    }


def _demographics_body(subject: Subject, demographics: DemographicsInput) -> dict:
    return {
        "content": "Demographics update",
        "type": enum_value(MemoryType.FACT),
        "scope": enum_value(MemoryScope.PROJECT),
        "category": "health",
        "source": "sdk:health",
        "metadata": {"subject": subject, "demographic": demographics},
    }


def _condition_body(subject: Subject, condition: ConditionInput) -> dict:
    return {
        "content": f"Diagnosis {condition['icd10']}",
        "type": enum_value(MemoryType.FACT),
        "scope": enum_value(MemoryScope.PROJECT),
        "category": "health",
        "source": "sdk:health",
        "metadata": {"subject": subject, "condition": condition},
    }


def _cohort_risk_body(subject: Subject, k: Optional[int]) -> dict:
    body: dict = {"subject": subject}
    if k is not None:
        body["k"] = k
    return body


class HealthResource:
    """Synchronous health-vertical operations."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    # ── Input — record health signals (stored as memory items) ──

    def record_biomarker(
        self,
        subject: Subject,
        biomarker: Biomarker,
        value: float,
        *,
        unit: Optional[str] = None,
        observed_at: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> MemoryItem:
        """Record a biomarker reading. Send whatever unit the lab reported via
        ``unit``; the engine normalizes it. Stored as a ``fact`` memory."""
        return self._t.post(
            "/admin/memory",
            _biomarker_body(subject, biomarker, value, unit, observed_at),
            project_id,
        )

    def record_demographics(
        self,
        subject: Subject,
        demographics: DemographicsInput,
        *,
        project_id: Optional[str] = None,
    ) -> MemoryItem:
        """Record/refresh a subject's demographics. Latest values win."""
        return self._t.post("/admin/memory", _demographics_body(subject, demographics), project_id)

    def record_condition(
        self,
        subject: Subject,
        condition: ConditionInput,
        *,
        project_id: Optional[str] = None,
    ) -> MemoryItem:
        """Record an ICD-10 diagnosis."""
        return self._t.post("/admin/memory", _condition_body(subject, condition), project_id)

    # ── Read — derived profile + cohort outcomes ──

    def get_profile(self, subject: Subject, *, project_id: Optional[str] = None) -> HealthProfile:
        """Biological-age estimate + condition predictions + latest biomarkers
        for a subject, derived from their recorded health data."""
        return self._t.post("/lattice/health/profile", {"subject": subject}, project_id)

    def get_cohort_risk(
        self,
        subject: Subject,
        *,
        k: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> CohortHealthRisk:
        """Cohort outcomes — condition prevalence among the patients most similar
        to this subject by baseline features. An epidemiological base rate to
        complement the individual projections from :meth:`get_profile`.

        ``k`` sets the cohort size (nearest patients); default 25 server-side."""
        return self._t.post("/lattice/health/cohort-risk", _cohort_risk_body(subject, k), project_id)


class AsyncHealthResource:
    """Asynchronous mirror of :class:`HealthResource`."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    async def record_biomarker(
        self,
        subject: Subject,
        biomarker: Biomarker,
        value: float,
        *,
        unit: Optional[str] = None,
        observed_at: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> MemoryItem:
        """Async mirror of :meth:`HealthResource.record_biomarker`."""
        return await self._t.post(
            "/admin/memory",
            _biomarker_body(subject, biomarker, value, unit, observed_at),
            project_id,
        )

    async def record_demographics(
        self,
        subject: Subject,
        demographics: DemographicsInput,
        *,
        project_id: Optional[str] = None,
    ) -> MemoryItem:
        """Async mirror of :meth:`HealthResource.record_demographics`."""
        return await self._t.post(
            "/admin/memory", _demographics_body(subject, demographics), project_id
        )

    async def record_condition(
        self,
        subject: Subject,
        condition: ConditionInput,
        *,
        project_id: Optional[str] = None,
    ) -> MemoryItem:
        """Async mirror of :meth:`HealthResource.record_condition`."""
        return await self._t.post("/admin/memory", _condition_body(subject, condition), project_id)

    async def get_profile(
        self, subject: Subject, *, project_id: Optional[str] = None
    ) -> HealthProfile:
        """Async mirror of :meth:`HealthResource.get_profile`."""
        return await self._t.post("/lattice/health/profile", {"subject": subject}, project_id)

    async def get_cohort_risk(
        self,
        subject: Subject,
        *,
        k: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> CohortHealthRisk:
        """Async mirror of :meth:`HealthResource.get_cohort_risk`."""
        return await self._t.post(
            "/lattice/health/cohort-risk", _cohort_risk_body(subject, k), project_id
        )


__all__ = ["HealthResource", "AsyncHealthResource"]
