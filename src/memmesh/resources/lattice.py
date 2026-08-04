"""Lattice resource — pattern mining, prediction, behavioral profiles,
cohorts, monitoring, deterministic estimators, and calibration.

This is the layer mem0 has no equivalent for: it mines memories into patterns,
projects what happens next with a confidence score, and reports how well those
scores hold up against reality. Mirrors ``thinkfleet-memory-sdk``'s
``resources/lattice.ts`` — 14 operations, one-for-one.
"""

from __future__ import annotations

from typing import Any, Optional

from ..types import (
    BehaviorPatternRecord,
    CalibrationReport,
    EstimateResult,
    ExtractPatternsResult,
    GetCohortResponse,
    LatticeContextBundle,
    ListContactPatternsResponse,
    MonitorStatus,
    MonitorTickResult,
    PredictByCohortResponse,
    PredictionTarget,
    PredictResult,
    Subject,
    SubjectProfile,
    TargetPrediction,
)


class LatticeResource:
    """Synchronous pattern / prediction / behavior operations."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    # ── Pattern extraction & mining ──────────────────────────────────────

    def extract_patterns(
        self,
        *,
        contact_id: Optional[str] = None,
        window_days: Optional[int] = None,
        force: Optional[bool] = None,
        source: Optional[str] = None,
        subject: Optional[Subject] = None,
        project_id: Optional[str] = None,
    ) -> ExtractPatternsResult:
        """Force pattern (re-)extraction. Omit ``contact_id`` for a project-wide
        bulk run; pass it to limit to one contact. Defaults server-side to mining
        the memory corpus (``source='memories'``); pass ``source='contact_events'``
        for the legacy path. Rate-limited server-side at 5 calls/minute."""
        body: dict = {}
        if contact_id is not None:
            body["contactId"] = contact_id
        if window_days is not None:
            body["windowDays"] = window_days
        if force is not None:
            body["force"] = force
        if source is not None:
            body["source"] = source
        if subject is not None:
            body["subject"] = subject
        return self._t.post("/lattice/patterns/extract", body, project_id)

    def mine(
        self,
        *,
        subject: Optional[Subject] = None,
        window_days: int = 90,
        force: Optional[bool] = None,
        project_id: Optional[str] = None,
    ) -> ExtractPatternsResult:
        """Mine behavioral patterns from the memory corpus. Subject-agnostic
        (contact, user, team, workspace, service). Thin wrapper over
        :meth:`extract_patterns` with ``source='memories'``. Omit ``subject`` for
        a project-wide run."""
        body: dict = {"source": "memories", "windowDays": window_days}
        if subject is not None:
            body["subject"] = subject
        if force is not None:
            body["force"] = force
        return self._t.post("/lattice/patterns/extract", body, project_id)

    def get_pattern(self, pattern_id: str, *, project_id: Optional[str] = None) -> BehaviorPatternRecord:
        """Inspect a single pattern by id. 404 if it doesn't exist or belongs to
        a different project."""
        return self._t.get(f"/lattice/patterns/{pattern_id}", None, project_id)

    def list_patterns(
        self,
        contact_id: str,
        *,
        active_only: Optional[bool] = None,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> ListContactPatternsResponse:
        """List behavior patterns Lattice learned for a contact. Cursor-paginated
        — pass the response's ``nextCursor`` back as ``cursor``."""
        params = {"activeOnly": active_only, "limit": limit, "cursor": cursor}
        return self._t.get(f"/lattice/contacts/{contact_id}/patterns", params, project_id)

    # ── Context bundle ───────────────────────────────────────────────────

    def get_context(
        self,
        contact_id: str,
        *,
        as_of: Optional[str] = None,
        events_limit: Optional[int] = None,
        memories_limit: Optional[int] = None,
        graph_hops: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> LatticeContextBundle:
        """Full retrieval bundle for a contact — profile, active patterns, recent
        events, recent memories, and (optionally) the entity/edge graph. Pass an
        ISO-8601 ``as_of`` for a bi-temporal replay of the bundle."""
        params = {
            "asOf": as_of,
            "eventsLimit": events_limit,
            "memoriesLimit": memories_limit,
            "graphHops": graph_hops,
        }
        return self._t.get(f"/lattice/contacts/{contact_id}/context", params, project_id)

    # ── Monitor ──────────────────────────────────────────────────────────

    def run_monitor_tick(self, *, project_id: Optional[str] = None) -> MonitorTickResult:
        """Manually run the pattern-break monitor tick. The platform runs this on
        a cron; manual triggers exist for debugging and tests that need an overdue
        pattern to fire immediately."""
        return self._t.post("/lattice/monitor/tick", {}, project_id)

    def get_monitor_status(self, *, project_id: Optional[str] = None) -> MonitorStatus:
        """Monitor health — timestamp of the last tick + count of patterns due for
        the next check. A liveness probe for the pattern-break dispatcher."""
        return self._t.get("/lattice/monitor/status", None, project_id)

    # ── Predict ──────────────────────────────────────────────────────────

    def predict(
        self,
        subject: Subject,
        *,
        horizon_days: int = 30,
        limit: Optional[int] = None,
        min_confidence: Optional[float] = None,
        occurrences_per_pattern: Optional[int] = None,
        emit_events: Optional[bool] = None,
        imminent_within_hours: Optional[int] = None,
        target: Optional[PredictionTarget] = None,
        project_id: Optional[str] = None,
    ) -> PredictResult:
        """Predict for a subject. Two modes:

        1. **Pattern projection (default).** Omit ``target`` to project the
           subject's active behavior patterns forward — each prediction names the
           pattern and source memories that produced it (provenance).
        2. **Declared target (v2 general prediction).** Pass ``target`` to predict
           anything — churn, next-order amount, next-visit time, anomaly —
           straight from observation history. The estimate arrives in
           ``result['targetPrediction']`` with first-class abstention. Prefer the
           typed :meth:`predict_target` helper for this case."""
        body: dict = {"subject": subject, "horizonDays": horizon_days}
        if limit is not None:
            body["limit"] = limit
        if min_confidence is not None:
            body["minConfidence"] = min_confidence
        if occurrences_per_pattern is not None:
            body["occurrencesPerPattern"] = occurrences_per_pattern
        if emit_events is not None:
            body["emitEvents"] = emit_events
        if imminent_within_hours is not None:
            body["imminentWithinHours"] = imminent_within_hours
        if target is not None:
            body["target"] = target
        return self._t.post("/lattice/predict", body, project_id)

    def predict_target(
        self,
        subject: Subject,
        target: PredictionTarget,
        *,
        horizon_days: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> TargetPrediction:
        """v2 general prediction, typed: declare *what* to predict and get back
        the single calibrated :class:`TargetPrediction` (or an abstention). Thin
        wrapper over :meth:`predict` with a ``target``.

        Always check ``['abstained']`` before reading a value — an abstention means
        "not enough signal", which you must treat as *unknown*, never as low risk.
        If the engine returns no estimate, a synthetic abstention is returned so
        callers never have to null-check."""
        result = self.predict(
            subject,
            horizon_days=horizon_days if horizon_days is not None else 30,
            target=target,
            project_id=project_id,
        )
        return result.get("targetPrediction") or _synthetic_abstention(target, result)

    # ── Profile & cohort ─────────────────────────────────────────────────

    def profile(self, subject: Subject, *, project_id: Optional[str] = None) -> SubjectProfile:
        """Who is this subject? RFM segment, top entity, cadence summary, risk
        indicators. The non-temporal counterpart to :meth:`predict`."""
        return self._t.post("/lattice/profile", {"subject": subject}, project_id)

    def get_cohort(
        self,
        subject: Subject,
        *,
        k: Optional[int] = None,
        min_similarity: Optional[float] = None,
        project_id: Optional[str] = None,
    ) -> GetCohortResponse:
        """Find subjects whose behavior looks similar to ``subject`` — top-K
        nearest neighbors ranked by a blended similarity score (RFM + entity
        Jaccard + pattern-kind Jaccard)."""
        body: dict = {"subject": subject}
        if k is not None:
            body["k"] = k
        if min_similarity is not None:
            body["minSimilarity"] = min_similarity
        return self._t.post("/lattice/cohort", body, project_id)

    def predict_by_cohort(
        self,
        subject: Subject,
        *,
        cohort_k: int = 10,
        prediction_limit: int = 5,
        min_similarity: Optional[float] = None,
        project_id: Optional[str] = None,
    ) -> PredictByCohortResponse:
        """Cohort-aware predictions — "people like this subject also did X."
        Every prediction carries ``supportingSubjects`` + ``sourceMemoryIds`` so
        the answer is traceable back to which cohort members contributed."""
        body: dict = {"subject": subject, "cohortK": cohort_k, "predictionLimit": prediction_limit}
        if min_similarity is not None:
            body["minSimilarity"] = min_similarity
        return self._t.post("/lattice/cohort/predict", body, project_id)

    # ── Estimate & calibration ───────────────────────────────────────────

    def estimate(
        self,
        subject: Subject,
        estimator_id: str,
        *,
        persist: Optional[bool] = None,
        project_id: Optional[str] = None,
    ) -> EstimateResult:
        """Run a deterministic estimator (e.g. PhenoAge biological age) over a
        subject's biomarker signals. Returns a wellness estimate with per-signal
        contributors and a not-a-diagnosis disclaimer — never a medical verdict."""
        body: dict = {"subject": subject, "estimatorId": estimator_id}
        if persist is not None:
            body["persist"] = persist
        return self._t.post("/lattice/estimate", body, project_id)

    def calibration(self, *, bucket_count: Optional[int] = None, project_id: Optional[str] = None) -> CalibrationReport:
        """Confidence buckets mapped to realized hit-rates — does "80% confident"
        actually fire ~80% of the time?"""
        return self._t.get("/lattice/calibration", {"bucketCount": bucket_count}, project_id)


class AsyncLatticeResource:
    """Asynchronous mirror of :class:`LatticeResource`."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    async def extract_patterns(
        self,
        *,
        contact_id: Optional[str] = None,
        window_days: Optional[int] = None,
        force: Optional[bool] = None,
        source: Optional[str] = None,
        subject: Optional[Subject] = None,
        project_id: Optional[str] = None,
    ) -> ExtractPatternsResult:
        body: dict = {}
        if contact_id is not None:
            body["contactId"] = contact_id
        if window_days is not None:
            body["windowDays"] = window_days
        if force is not None:
            body["force"] = force
        if source is not None:
            body["source"] = source
        if subject is not None:
            body["subject"] = subject
        return await self._t.post("/lattice/patterns/extract", body, project_id)

    async def mine(
        self,
        *,
        subject: Optional[Subject] = None,
        window_days: int = 90,
        force: Optional[bool] = None,
        project_id: Optional[str] = None,
    ) -> ExtractPatternsResult:
        body: dict = {"source": "memories", "windowDays": window_days}
        if subject is not None:
            body["subject"] = subject
        if force is not None:
            body["force"] = force
        return await self._t.post("/lattice/patterns/extract", body, project_id)

    async def get_pattern(self, pattern_id: str, *, project_id: Optional[str] = None) -> BehaviorPatternRecord:
        return await self._t.get(f"/lattice/patterns/{pattern_id}", None, project_id)

    async def list_patterns(
        self,
        contact_id: str,
        *,
        active_only: Optional[bool] = None,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> ListContactPatternsResponse:
        params = {"activeOnly": active_only, "limit": limit, "cursor": cursor}
        return await self._t.get(f"/lattice/contacts/{contact_id}/patterns", params, project_id)

    async def get_context(
        self,
        contact_id: str,
        *,
        as_of: Optional[str] = None,
        events_limit: Optional[int] = None,
        memories_limit: Optional[int] = None,
        graph_hops: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> LatticeContextBundle:
        params = {
            "asOf": as_of,
            "eventsLimit": events_limit,
            "memoriesLimit": memories_limit,
            "graphHops": graph_hops,
        }
        return await self._t.get(f"/lattice/contacts/{contact_id}/context", params, project_id)

    async def run_monitor_tick(self, *, project_id: Optional[str] = None) -> MonitorTickResult:
        return await self._t.post("/lattice/monitor/tick", {}, project_id)

    async def get_monitor_status(self, *, project_id: Optional[str] = None) -> MonitorStatus:
        return await self._t.get("/lattice/monitor/status", None, project_id)

    async def predict(
        self,
        subject: Subject,
        *,
        horizon_days: int = 30,
        limit: Optional[int] = None,
        min_confidence: Optional[float] = None,
        occurrences_per_pattern: Optional[int] = None,
        emit_events: Optional[bool] = None,
        imminent_within_hours: Optional[int] = None,
        target: Optional[PredictionTarget] = None,
        project_id: Optional[str] = None,
    ) -> PredictResult:
        body: dict = {"subject": subject, "horizonDays": horizon_days}
        if limit is not None:
            body["limit"] = limit
        if min_confidence is not None:
            body["minConfidence"] = min_confidence
        if occurrences_per_pattern is not None:
            body["occurrencesPerPattern"] = occurrences_per_pattern
        if emit_events is not None:
            body["emitEvents"] = emit_events
        if imminent_within_hours is not None:
            body["imminentWithinHours"] = imminent_within_hours
        if target is not None:
            body["target"] = target
        return await self._t.post("/lattice/predict", body, project_id)

    async def predict_target(
        self,
        subject: Subject,
        target: PredictionTarget,
        *,
        horizon_days: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> TargetPrediction:
        result = await self.predict(
            subject,
            horizon_days=horizon_days if horizon_days is not None else 30,
            target=target,
            project_id=project_id,
        )
        return result.get("targetPrediction") or _synthetic_abstention(target, result)

    async def profile(self, subject: Subject, *, project_id: Optional[str] = None) -> SubjectProfile:
        return await self._t.post("/lattice/profile", {"subject": subject}, project_id)

    async def get_cohort(
        self,
        subject: Subject,
        *,
        k: Optional[int] = None,
        min_similarity: Optional[float] = None,
        project_id: Optional[str] = None,
    ) -> GetCohortResponse:
        body: dict = {"subject": subject}
        if k is not None:
            body["k"] = k
        if min_similarity is not None:
            body["minSimilarity"] = min_similarity
        return await self._t.post("/lattice/cohort", body, project_id)

    async def predict_by_cohort(
        self,
        subject: Subject,
        *,
        cohort_k: int = 10,
        prediction_limit: int = 5,
        min_similarity: Optional[float] = None,
        project_id: Optional[str] = None,
    ) -> PredictByCohortResponse:
        body: dict = {"subject": subject, "cohortK": cohort_k, "predictionLimit": prediction_limit}
        if min_similarity is not None:
            body["minSimilarity"] = min_similarity
        return await self._t.post("/lattice/cohort/predict", body, project_id)

    async def estimate(
        self,
        subject: Subject,
        estimator_id: str,
        *,
        persist: Optional[bool] = None,
        project_id: Optional[str] = None,
    ) -> EstimateResult:
        body: dict = {"subject": subject, "estimatorId": estimator_id}
        if persist is not None:
            body["persist"] = persist
        return await self._t.post("/lattice/estimate", body, project_id)

    async def calibration(self, *, bucket_count: Optional[int] = None, project_id: Optional[str] = None) -> CalibrationReport:
        return await self._t.get("/lattice/calibration", {"bucketCount": bucket_count}, project_id)


def _synthetic_abstention(target: PredictionTarget, result: PredictResult) -> TargetPrediction:
    """Fallback :class:`TargetPrediction` when the engine returns no target
    estimate — mirrors the TS ``predictTarget`` synthetic abstention so callers
    never have to null-check."""
    event_type = target.get("eventType") or target.get("attributeKey") or ""
    reason = result.get("abstentionReason") or "insufficient_signal: engine returned no target estimate"
    return {
        "targetKind": target["kind"],
        "eventType": event_type,
        "probability": 0.0,
        "probabilityLower": 0.0,
        "probabilityUpper": 0.0,
        "value": 0.0,
        "valueLower": 0.0,
        "valueUpper": 0.0,
        "expectedAt": "",
        "expectedAtLower": "",
        "expectedAtUpper": "",
        "daysUntil": 0.0,
        "anomalyScore": 0.0,
        "isAnomaly": False,
        "abstained": True,
        "abstentionReason": reason,
        "explanation": "",
        "evidenceMemoryIds": [],
    }
