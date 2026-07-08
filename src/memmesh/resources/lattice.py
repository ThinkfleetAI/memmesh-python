"""Lattice resource — prediction, behavioral profiles, and calibration.

This is the layer mem0 has no equivalent for: it mines memories into patterns,
projects what happens next with a confidence score, and reports how well those
scores hold up against reality.
"""

from __future__ import annotations

from typing import Any, Optional

from ..types import CalibrationReport, PredictResult, Subject, SubjectProfile


class LatticeResource:
    """Synchronous prediction + behavior operations."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def predict(
        self,
        subject: Subject,
        *,
        horizon_days: int = 30,
        project_id: Optional[str] = None,
    ) -> PredictResult:
        """Project future events for a subject from their active patterns.
        Each prediction names the pattern and source memories that produced it
        (provenance), so any single prediction can be explained or audited."""
        return self._t.post("/lattice/predict", {"subject": subject, "horizonDays": horizon_days}, project_id)

    def mine(
        self,
        *,
        subject: Optional[Subject] = None,
        window_days: int = 90,
        project_id: Optional[str] = None,
    ) -> dict:
        """Force pattern (re-)mining over the memory corpus. Omit ``subject``
        for a project-wide run."""
        body: dict = {"source": "memories", "windowDays": window_days}
        if subject is not None:
            body["subject"] = subject
        return self._t.post("/lattice/patterns/extract", body, project_id)

    def profile(self, subject: Subject, *, project_id: Optional[str] = None) -> SubjectProfile:
        """Who is this subject? RFM segment, top entity, cadence summary, risk
        indicators. The non-temporal counterpart to :meth:`predict`."""
        return self._t.post("/lattice/profile", {"subject": subject}, project_id)

    def predict_by_cohort(
        self,
        subject: Subject,
        *,
        cohort_k: int = 10,
        prediction_limit: int = 5,
        min_similarity: Optional[float] = None,
        project_id: Optional[str] = None,
    ) -> dict:
        """Cohort-aware predictions — people like this subject also did X."""
        body: dict = {"subject": subject, "cohortK": cohort_k, "predictionLimit": prediction_limit}
        if min_similarity is not None:
            body["minSimilarity"] = min_similarity
        return self._t.post("/lattice/cohort/predict", body, project_id)

    def calibration(self, *, bucket_count: Optional[int] = None, project_id: Optional[str] = None) -> CalibrationReport:
        """Confidence buckets mapped to realized hit-rates — does "80% confident"
        actually fire ~80% of the time?"""
        return self._t.get("/lattice/calibration", {"bucketCount": bucket_count}, project_id)


class AsyncLatticeResource:
    """Asynchronous mirror of :class:`LatticeResource`."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    async def predict(
        self,
        subject: Subject,
        *,
        horizon_days: int = 30,
        project_id: Optional[str] = None,
    ) -> PredictResult:
        return await self._t.post("/lattice/predict", {"subject": subject, "horizonDays": horizon_days}, project_id)

    async def mine(
        self,
        *,
        subject: Optional[Subject] = None,
        window_days: int = 90,
        project_id: Optional[str] = None,
    ) -> dict:
        body: dict = {"source": "memories", "windowDays": window_days}
        if subject is not None:
            body["subject"] = subject
        return await self._t.post("/lattice/patterns/extract", body, project_id)

    async def profile(self, subject: Subject, *, project_id: Optional[str] = None) -> SubjectProfile:
        return await self._t.post("/lattice/profile", {"subject": subject}, project_id)

    async def predict_by_cohort(
        self,
        subject: Subject,
        *,
        cohort_k: int = 10,
        prediction_limit: int = 5,
        min_similarity: Optional[float] = None,
        project_id: Optional[str] = None,
    ) -> dict:
        body: dict = {"subject": subject, "cohortK": cohort_k, "predictionLimit": prediction_limit}
        if min_similarity is not None:
            body["minSimilarity"] = min_similarity
        return await self._t.post("/lattice/cohort/predict", body, project_id)

    async def calibration(self, *, bucket_count: Optional[int] = None, project_id: Optional[str] = None) -> CalibrationReport:
        return await self._t.get("/lattice/calibration", {"bucketCount": bucket_count}, project_id)
