"""Context resource — LLM-ready context bundles + temporal graph queries."""

from __future__ import annotations

from typing import Any, List, Optional

from ..types import Subject, enum_value


def _context_body(
    include: Optional[List[str]],
    max_tokens: Optional[int],
    memory_limit: Optional[int],
    prediction_limit: Optional[int],
    exclude_categories: Optional[List[str]],
) -> dict:
    raw = {
        "include": include,
        "maxTokens": max_tokens,
        "memoryLimit": memory_limit,
        "predictionLimit": prediction_limit,
        "excludeCategories": exclude_categories,
    }
    return {k: v for k, v in raw.items() if v is not None}


class ContextResource:
    """Unified, token-budgeted context for an LLM + point-in-time graph reads."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def build(
        self,
        subject: Subject,
        *,
        include: Optional[List[str]] = None,
        max_tokens: Optional[int] = None,
        memory_limit: Optional[int] = None,
        prediction_limit: Optional[int] = None,
        exclude_categories: Optional[List[str]] = None,
        project_id: Optional[str] = None,
    ) -> dict:
        """Aggregate profile + patterns + predictions + memories + observations
        for one subject into a single provenanced bundle."""
        body = {"subject": subject, **_context_body(include, max_tokens, memory_limit, prediction_limit, exclude_categories)}
        return self._t.post("/lattice/context", body, project_id)

    def batch_build(
        self,
        subjects: List[Subject],
        *,
        include: Optional[List[str]] = None,
        max_tokens: Optional[int] = None,
        memory_limit: Optional[int] = None,
        prediction_limit: Optional[int] = None,
        exclude_categories: Optional[List[str]] = None,
        project_id: Optional[str] = None,
    ) -> List[dict]:
        """Build bundles for many subjects (<=500) in one call — the bulk-load
        path. Bundles are returned in request order."""
        body = {"subjects": subjects, **_context_body(include, max_tokens, memory_limit, prediction_limit, exclude_categories)}
        r = self._t.post("/lattice/context/batch", body, project_id)
        return r.get("bundles", []) if isinstance(r, dict) else r

    def query_graph(
        self,
        *,
        subject_id: Optional[str] = None,
        predicate: Optional[str] = None,
        as_of: Optional[str] = None,
        limit: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> List[dict]:
        """Point-in-time knowledge-graph query: edges valid AT ``as_of`` (RFC3339)
        or current, filtered by subject/predicate."""
        body = {k: v for k, v in {"subjectId": subject_id, "predicate": predicate, "asOf": as_of, "limit": limit}.items() if v is not None}
        r = self._t.post("/lattice/graph/query", body, project_id)
        return r.get("edges", []) if isinstance(r, dict) else r


class AsyncContextResource:
    """Asynchronous mirror of :class:`ContextResource`."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    async def build(
        self,
        subject: Subject,
        *,
        include: Optional[List[str]] = None,
        max_tokens: Optional[int] = None,
        memory_limit: Optional[int] = None,
        prediction_limit: Optional[int] = None,
        exclude_categories: Optional[List[str]] = None,
        project_id: Optional[str] = None,
    ) -> dict:
        body = {"subject": subject, **_context_body(include, max_tokens, memory_limit, prediction_limit, exclude_categories)}
        return await self._t.post("/lattice/context", body, project_id)

    async def batch_build(
        self,
        subjects: List[Subject],
        *,
        include: Optional[List[str]] = None,
        max_tokens: Optional[int] = None,
        memory_limit: Optional[int] = None,
        prediction_limit: Optional[int] = None,
        exclude_categories: Optional[List[str]] = None,
        project_id: Optional[str] = None,
    ) -> List[dict]:
        body = {"subjects": subjects, **_context_body(include, max_tokens, memory_limit, prediction_limit, exclude_categories)}
        r = await self._t.post("/lattice/context/batch", body, project_id)
        return r.get("bundles", []) if isinstance(r, dict) else r

    async def query_graph(
        self,
        *,
        subject_id: Optional[str] = None,
        predicate: Optional[str] = None,
        as_of: Optional[str] = None,
        limit: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> List[dict]:
        body = {k: v for k, v in {"subjectId": subject_id, "predicate": predicate, "asOf": as_of, "limit": limit}.items() if v is not None}
        r = await self._t.post("/lattice/graph/query", body, project_id)
        return r.get("edges", []) if isinstance(r, dict) else r
