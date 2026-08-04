"""Typed attributes resource — structured/numeric data the engine reasons over
(credit scores, sensor readings, balances) instead of opaque metadata.

Register an attribute's schema once, then ingest observations: each is validated
against the definition (accepted or quarantined) and accepted numeric values are
folded into per-subject accumulators you can read back with running
mean/variance/min/max/cumulative. Pair with a ``memory-value`` alert rule (see
:mod:`memmesh.resources.alerts`) to fire on a threshold/range. Mirrors
``thinkfleet-memory-sdk``'s ``resources/typed.ts`` — 6 operations, one-for-one.

>>> from memmesh import MemMesh
>>> mm = MemMesh(api_key="sk-...", project_id="proj_...")
>>> mm.typed.register_attribute(
...     {"attributeKey": "credit_score", "dataType": "numeric",
...      "minValid": 300, "maxValid": 850})
>>> mm.typed.ingest([
...     {"attributeKey": "credit_score", "subjectKind": "contact",
...      "subjectExternalId": "sarah", "valueNumeric": 650,
...      "observedAt": "2026-01-01T00:00:00Z"}])
>>> acc = mm.typed.accumulator(
...     subject_kind="contact", subject_external_id="sarah",
...     attribute_key="credit_score")
>>> acc["mean"]  # 650
"""

from __future__ import annotations

from typing import Any, List, Optional

from ..types import (
    Accumulator,
    AttributeDef,
    EnqueueResult,
    IngestReport,
    ObservationStatus,
    RegisterAttributeRequest,
    TypedObservation,
    TypedObservationInput,
)


def _query_params(
    subject_kind: Optional[str],
    subject_external_id: Optional[str],
    attribute_key: Optional[str],
    since: Optional[str],
    until: Optional[str],
    min_value: Optional[float],
    max_value: Optional[float],
    status: Optional[ObservationStatus],
    limit: Optional[int],
    offset: Optional[int],
) -> dict:
    """Build the camelCase query for :meth:`query_observations`; the transport
    drops ``None`` values."""
    return {
        "subjectKind": subject_kind,
        "subjectExternalId": subject_external_id,
        "attributeKey": attribute_key,
        "since": since,
        "until": until,
        "minValue": min_value,
        "maxValue": max_value,
        "status": status,
        "limit": limit,
        "offset": offset,
    }


class TypedAttributesResource:
    """Synchronous typed-attribute operations."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def register_attribute(
        self, body: RegisterAttributeRequest, *, project_id: Optional[str] = None
    ) -> AttributeDef:
        """Register or update an attribute definition (type + plausibility range)."""
        return self._t.post("/memory-typed/attributes", body, project_id)

    def list_attributes(
        self,
        *,
        attribute_key: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> List[AttributeDef]:
        """List registered attribute definitions for the project."""
        params = {"attributeKey": attribute_key, "limit": limit, "offset": offset}
        return self._t.get("/memory-typed/attributes", params, project_id)

    def ingest(
        self, observations: List[TypedObservationInput], *, project_id: Optional[str] = None
    ) -> IngestReport:
        """Ingest a batch of typed observations synchronously and return the
        report (accepted / quarantined / duplicate counts + quarantine reasons)."""
        return self._t.post(
            "/memory-typed/observations", {"observations": observations}, project_id
        )

    def enqueue(
        self, observations: List[TypedObservationInput], *, project_id: Optional[str] = None
    ) -> EnqueueResult:
        """Queue a batch for asynchronous ingest (the scalable path for high
        volume). Returns the count accepted onto the queue; results are folded in
        by a background worker."""
        return self._t.post(
            "/memory-typed/observations/enqueue", {"observations": observations}, project_id
        )

    def query_observations(
        self,
        *,
        subject_kind: Optional[str] = None,
        subject_external_id: Optional[str] = None,
        attribute_key: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        status: Optional[ObservationStatus] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> List[TypedObservation]:
        """Query raw observations by subject, attribute, time window, and value
        range."""
        params = _query_params(
            subject_kind,
            subject_external_id,
            attribute_key,
            since,
            until,
            min_value,
            max_value,
            status,
            limit,
            offset,
        )
        return self._t.get("/memory-typed/observations", params, project_id)

    def accumulator(
        self,
        *,
        subject_kind: str,
        subject_external_id: str,
        attribute_key: str,
        project_id: Optional[str] = None,
    ) -> Accumulator:
        """Read the running statistics for a subject + attribute."""
        params = {
            "subjectKind": subject_kind,
            "subjectExternalId": subject_external_id,
            "attributeKey": attribute_key,
        }
        return self._t.get("/memory-typed/accumulator", params, project_id)


class AsyncTypedAttributesResource:
    """Asynchronous mirror of :class:`TypedAttributesResource`."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    async def register_attribute(
        self, body: RegisterAttributeRequest, *, project_id: Optional[str] = None
    ) -> AttributeDef:
        return await self._t.post("/memory-typed/attributes", body, project_id)

    async def list_attributes(
        self,
        *,
        attribute_key: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> List[AttributeDef]:
        params = {"attributeKey": attribute_key, "limit": limit, "offset": offset}
        return await self._t.get("/memory-typed/attributes", params, project_id)

    async def ingest(
        self, observations: List[TypedObservationInput], *, project_id: Optional[str] = None
    ) -> IngestReport:
        return await self._t.post(
            "/memory-typed/observations", {"observations": observations}, project_id
        )

    async def enqueue(
        self, observations: List[TypedObservationInput], *, project_id: Optional[str] = None
    ) -> EnqueueResult:
        return await self._t.post(
            "/memory-typed/observations/enqueue", {"observations": observations}, project_id
        )

    async def query_observations(
        self,
        *,
        subject_kind: Optional[str] = None,
        subject_external_id: Optional[str] = None,
        attribute_key: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        status: Optional[ObservationStatus] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> List[TypedObservation]:
        params = _query_params(
            subject_kind,
            subject_external_id,
            attribute_key,
            since,
            until,
            min_value,
            max_value,
            status,
            limit,
            offset,
        )
        return await self._t.get("/memory-typed/observations", params, project_id)

    async def accumulator(
        self,
        *,
        subject_kind: str,
        subject_external_id: str,
        attribute_key: str,
        project_id: Optional[str] = None,
    ) -> Accumulator:
        params = {
            "subjectKind": subject_kind,
            "subjectExternalId": subject_external_id,
            "attributeKey": attribute_key,
        }
        return await self._t.get("/memory-typed/accumulator", params, project_id)


__all__ = ["TypedAttributesResource", "AsyncTypedAttributesResource"]
