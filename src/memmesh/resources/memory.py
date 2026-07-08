"""Memory resource — observe, recall, search, and manage memories."""

from __future__ import annotations

from typing import Any, List, Optional

from ..types import (
    FeedbackRating,
    MemoryItem,
    MemoryScope,
    MemoryType,
    SearchResult,
    Subject,
    enum_value,
)


def _observe_body(
    content: str,
    subject: Optional[Subject],
    type: Any,
    scope: Any,
    importance: int,
    category: Optional[str],
    activity_type: Optional[str],
    occurred_at: Optional[str],
    metadata: Optional[dict],
) -> dict:
    md: dict = {}
    if subject is not None:
        md["subject"] = subject
    if activity_type:
        md["eventType"] = activity_type
    if occurred_at:
        md["occurredAt"] = occurred_at
    if metadata:
        md.update(metadata)
    body: dict = {
        "content": content,
        "type": enum_value(type),
        "scope": enum_value(scope),
        "importance": importance,
        "source": "admin_created",
        "metadata": md,
    }
    if category:
        body["category"] = category
    return body


def _update_body(content, importance, type, status, scope) -> dict:
    raw = {
        "content": content,
        "importance": importance,
        "type": enum_value(type) if type is not None else None,
        "status": status,
        "scope": enum_value(scope) if scope is not None else None,
    }
    return {k: v for k, v in raw.items() if v is not None}


class MemoryResource:
    """Synchronous memory operations."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def observe(
        self,
        content: str,
        *,
        subject: Optional[Subject] = None,
        type: Any = MemoryType.EVENT,
        scope: Any = MemoryScope.PROJECT,
        importance: int = 5,
        category: Optional[str] = None,
        activity_type: Optional[str] = None,
        occurred_at: Optional[str] = None,
        metadata: Optional[dict] = None,
        project_id: Optional[str] = None,
    ) -> MemoryItem:
        """Record that *something happened*. The engine decides what to keep,
        mines it into patterns, and the prediction layer reads it. The primary
        ingestion call for agents."""
        body = _observe_body(content, subject, type, scope, importance, category, activity_type, occurred_at, metadata)
        return self._t.post("/admin/memory", body, project_id)

    def create(
        self,
        content: str,
        *,
        type: Any = MemoryType.FACT,
        scope: Any = MemoryScope.PROJECT,
        importance: int = 5,
        category: Optional[str] = None,
        metadata: Optional[dict] = None,
        project_id: Optional[str] = None,
    ) -> MemoryItem:
        """Seed a memory directly (knowledge an agent should have without
        observing it first)."""
        body: dict = {"content": content, "type": enum_value(type), "scope": enum_value(scope), "importance": importance}
        if category:
            body["category"] = category
        if metadata:
            body["metadata"] = metadata
        return self._t.post("/admin/memory", body, project_id)

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        scope: Any = None,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> List[SearchResult]:
        """Hybrid semantic + keyword search across every scope the project can see."""
        body: dict = {"query": query, "limit": limit}
        if scope is not None:
            body["scope"] = enum_value(scope)
        if status:
            body["status"] = status
        return self._t.post("/admin/memory/search", body, project_id)

    def list(
        self,
        *,
        scope: Any = None,
        status: Optional[str] = None,
        type: Any = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> List[MemoryItem]:
        params = {
            "scope": enum_value(scope) if scope is not None else None,
            "status": status,
            "type": enum_value(type) if type is not None else None,
            "limit": limit,
            "offset": offset,
        }
        return self._t.get("/admin/memory", params, project_id)

    def update(
        self,
        memory_id: str,
        *,
        content: Optional[str] = None,
        importance: Optional[int] = None,
        type: Any = None,
        status: Optional[str] = None,
        scope: Any = None,
        project_id: Optional[str] = None,
    ) -> MemoryItem:
        return self._t.patch(f"/admin/memory/{memory_id}", _update_body(content, importance, type, status, scope), project_id)

    def delete(self, memory_id: str, *, project_id: Optional[str] = None) -> None:
        """Hard-delete a memory item. Gone is gone."""
        return self._t.delete(f"/admin/memory/{memory_id}", project_id)

    def stats(self, *, project_id: Optional[str] = None) -> dict:
        return self._t.get("/admin/memory/stats", None, project_id)

    def feedback(
        self,
        memory_id: str,
        rating: Any,
        *,
        comment: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> None:
        """Reinforce (``positive``) or flag (``negative``) a memory. Three
        negatives sends it to the review queue."""
        body: dict = {"memoryId": memory_id, "rating": enum_value(rating)}
        if comment:
            body["comment"] = comment
        return self._t.post("/memory/feedback", body, project_id)

    # ── Admin / maintenance ops ─────────────────────────────────────────

    def confirm(self, memory_id: str, status: str, *, comment: Optional[str] = None, project_id: Optional[str] = None) -> MemoryItem:
        """Confirm (``confirmed``) or reject (``rejected``) a review-queue item."""
        body: dict = {"status": status}
        if comment:
            body["comment"] = comment
        return self._t.post(f"/admin/memory/{memory_id}/confirm", body, project_id)

    def promote(self, memory_id: str, target_scope: Any, *, project_id: Optional[str] = None) -> MemoryItem:
        """Promote a memory to a broader scope (e.g. user → project)."""
        return self._t.post(f"/admin/memory/{memory_id}/promote", {"targetScope": enum_value(target_scope)}, project_id)

    def consolidate(self, *, subject: Optional[Subject] = None, window_days: Optional[int] = None, project_id: Optional[str] = None) -> dict:
        """LLM deductive-observations pass over recent activity."""
        body: dict = {}
        if subject is not None:
            body["subject"] = subject
        if window_days is not None:
            body["windowDays"] = window_days
        return self._t.post("/admin/memory/consolidate", body, project_id)

    def dedup(self, *, threshold: Optional[float] = None, scan_limit: Optional[int] = None, project_id: Optional[str] = None) -> dict:
        """Semantic dedup: collapse near-duplicates, keep the strongest, supersede the rest."""
        body = {k: v for k, v in {"threshold": threshold, "scanLimit": scan_limit}.items() if v is not None}
        return self._t.post("/admin/memory/dedup", body, project_id)

    def backfill_embeddings(self, *, batch: Optional[int] = None, project_id: Optional[str] = None) -> dict:
        """Vectorize items missing an embedding. Call repeatedly until embedded=0."""
        body = {"batch": batch} if batch is not None else {}
        return self._t.post("/admin/memory/embeddings/backfill", body, project_id)

    def reflect(self, *, user_id: Optional[str] = None, max_sources: Optional[int] = None, max_insights: Optional[int] = None, dry_run: bool = False, project_id: Optional[str] = None) -> dict:
        """Reflection / insight synthesis: synthesize higher-order ``insight``
        memories (with provenance) from a subject's recent confirmed memories."""
        body = {k: v for k, v in {"userId": user_id, "maxSources": max_sources, "maxInsights": max_insights, "dryRun": dry_run}.items() if v is not None}
        return self._t.post("/admin/memory/reflect", body, project_id)

    def prefetch_related(self, seed_memory_ids: List[str], *, limit: Optional[int] = None, project_id: Optional[str] = None) -> List[MemoryItem]:
        """Predictive prefetch: memories linked to the same graph entities as the
        seeds, ranked by association — the context most likely needed next."""
        body: dict = {"seedMemoryIds": seed_memory_ids}
        if limit is not None:
            body["limit"] = limit
        return self._t.post("/admin/memory/prefetch-related", body, project_id)


class AsyncMemoryResource:
    """Asynchronous mirror of :class:`MemoryResource`."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    async def observe(
        self,
        content: str,
        *,
        subject: Optional[Subject] = None,
        type: Any = MemoryType.EVENT,
        scope: Any = MemoryScope.PROJECT,
        importance: int = 5,
        category: Optional[str] = None,
        activity_type: Optional[str] = None,
        occurred_at: Optional[str] = None,
        metadata: Optional[dict] = None,
        project_id: Optional[str] = None,
    ) -> MemoryItem:
        body = _observe_body(content, subject, type, scope, importance, category, activity_type, occurred_at, metadata)
        return await self._t.post("/admin/memory", body, project_id)

    async def create(
        self,
        content: str,
        *,
        type: Any = MemoryType.FACT,
        scope: Any = MemoryScope.PROJECT,
        importance: int = 5,
        category: Optional[str] = None,
        metadata: Optional[dict] = None,
        project_id: Optional[str] = None,
    ) -> MemoryItem:
        body: dict = {"content": content, "type": enum_value(type), "scope": enum_value(scope), "importance": importance}
        if category:
            body["category"] = category
        if metadata:
            body["metadata"] = metadata
        return await self._t.post("/admin/memory", body, project_id)

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        scope: Any = None,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> List[SearchResult]:
        body: dict = {"query": query, "limit": limit}
        if scope is not None:
            body["scope"] = enum_value(scope)
        if status:
            body["status"] = status
        return await self._t.post("/admin/memory/search", body, project_id)

    async def list(
        self,
        *,
        scope: Any = None,
        status: Optional[str] = None,
        type: Any = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> List[MemoryItem]:
        params = {
            "scope": enum_value(scope) if scope is not None else None,
            "status": status,
            "type": enum_value(type) if type is not None else None,
            "limit": limit,
            "offset": offset,
        }
        return await self._t.get("/admin/memory", params, project_id)

    async def update(
        self,
        memory_id: str,
        *,
        content: Optional[str] = None,
        importance: Optional[int] = None,
        type: Any = None,
        status: Optional[str] = None,
        scope: Any = None,
        project_id: Optional[str] = None,
    ) -> MemoryItem:
        return await self._t.patch(f"/admin/memory/{memory_id}", _update_body(content, importance, type, status, scope), project_id)

    async def delete(self, memory_id: str, *, project_id: Optional[str] = None) -> None:
        return await self._t.delete(f"/admin/memory/{memory_id}", project_id)

    async def stats(self, *, project_id: Optional[str] = None) -> dict:
        return await self._t.get("/admin/memory/stats", None, project_id)

    async def feedback(
        self,
        memory_id: str,
        rating: Any,
        *,
        comment: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> None:
        body: dict = {"memoryId": memory_id, "rating": enum_value(rating)}
        if comment:
            body["comment"] = comment
        return await self._t.post("/memory/feedback", body, project_id)

    # ── Admin / maintenance ops ─────────────────────────────────────────

    async def confirm(self, memory_id: str, status: str, *, comment: Optional[str] = None, project_id: Optional[str] = None) -> MemoryItem:
        body: dict = {"status": status}
        if comment:
            body["comment"] = comment
        return await self._t.post(f"/admin/memory/{memory_id}/confirm", body, project_id)

    async def promote(self, memory_id: str, target_scope: Any, *, project_id: Optional[str] = None) -> MemoryItem:
        return await self._t.post(f"/admin/memory/{memory_id}/promote", {"targetScope": enum_value(target_scope)}, project_id)

    async def consolidate(self, *, subject: Optional[Subject] = None, window_days: Optional[int] = None, project_id: Optional[str] = None) -> dict:
        body: dict = {}
        if subject is not None:
            body["subject"] = subject
        if window_days is not None:
            body["windowDays"] = window_days
        return await self._t.post("/admin/memory/consolidate", body, project_id)

    async def dedup(self, *, threshold: Optional[float] = None, scan_limit: Optional[int] = None, project_id: Optional[str] = None) -> dict:
        body = {k: v for k, v in {"threshold": threshold, "scanLimit": scan_limit}.items() if v is not None}
        return await self._t.post("/admin/memory/dedup", body, project_id)

    async def backfill_embeddings(self, *, batch: Optional[int] = None, project_id: Optional[str] = None) -> dict:
        body = {"batch": batch} if batch is not None else {}
        return await self._t.post("/admin/memory/embeddings/backfill", body, project_id)

    async def reflect(self, *, user_id: Optional[str] = None, max_sources: Optional[int] = None, max_insights: Optional[int] = None, dry_run: bool = False, project_id: Optional[str] = None) -> dict:
        body = {k: v for k, v in {"userId": user_id, "maxSources": max_sources, "maxInsights": max_insights, "dryRun": dry_run}.items() if v is not None}
        return await self._t.post("/admin/memory/reflect", body, project_id)

    async def prefetch_related(self, seed_memory_ids: List[str], *, limit: Optional[int] = None, project_id: Optional[str] = None) -> List[MemoryItem]:
        body: dict = {"seedMemoryIds": seed_memory_ids}
        if limit is not None:
            body["limit"] = limit
        return await self._t.post("/admin/memory/prefetch-related", body, project_id)
