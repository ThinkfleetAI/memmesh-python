"""Memory resource — observe, recall, search, and manage memories."""

from __future__ import annotations

import asyncio
import base64
from typing import Any, List, Optional, Union

from .._pagination import (
    MAX_PAGE_SIZE,
    AsyncOffsetPaginator,
    SyncOffsetPaginator,
    apaginate,
    paginate,
)
from ..types import (
    ExplainResult,
    FeedbackRating,
    IngestMediaResult,
    MemoryFeedback,
    MemoryItem,
    MemoryScope,
    MemoryType,
    ObserveResponse,
    SearchResult,
    Subject,
    enum_value,
    render_procedure_content,
)


def _media_body(
    media: Union[bytes, str],
    mime_type: str,
    user_id: Optional[str],
    agent_id: Optional[str],
    session_id: Optional[str],
    source: Optional[str],
) -> dict:
    data_b64 = media if isinstance(media, str) else base64.b64encode(media).decode("ascii")
    body: dict = {"dataBase64": data_b64, "mimeType": mime_type}
    if user_id:
        body["userId"] = user_id
    if agent_id:
        body["agentId"] = agent_id
    if session_id:
        body["sessionId"] = session_id
    if source:
        body["source"] = source
    return body


def _attachment_body(
    data: Union[bytes, str],
    subject: Subject,
    mime_type: str,
    file_name: Optional[str],
    content: Optional[str],
    activity_type: Optional[str],
    occurred_at: Optional[str],
    importance: Optional[int],
    metadata: Optional[dict],
) -> dict:
    data_b64 = data if isinstance(data, str) else base64.b64encode(data).decode("ascii")
    raw = {
        "subject": subject,
        "mimeType": mime_type,
        "fileName": file_name,
        "content": content,
        "activityType": activity_type,
        "occurredAt": occurred_at,
        "importance": importance,
        "metadata": metadata,
        "dataBase64": data_b64,
    }
    return {k: v for k, v in raw.items() if v is not None}


def _explain_source_ids(memory: MemoryItem) -> List[str]:
    """Pull source-memory ids off a derived item's metadata. Accepts both the
    camelCase the Rust engine emits and the snake_case legacy items carry."""
    md = memory.get("metadata") or {}
    raw_ids = md.get("sourceMemoryIds")
    if raw_ids is None:
        raw_ids = md.get("source_memory_ids") or []
    if not isinstance(raw_ids, list):
        return []
    return [x for x in raw_ids if isinstance(x, str)]


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
    if occurred_at:
        # Event time, not ingest time. `validFrom` is the column behavior mining
        # buckets day-of-week / hour-of-day on, so this is what makes a backfill
        # work: without it every historical row lands at the moment of import and
        # the mined patterns describe the import job, not the data. The metadata
        # copy above is kept only for readers that already look for it.
        body["validFrom"] = occurred_at
    if category:
        body["category"] = category
    return body


def _observe_text_body(text: str, role: str, occurred_at: Optional[str]) -> dict:
    """Body for the raw-text observe path — the engine's noise filter runs over
    ``text`` and decides what (if anything) to keep."""
    body: dict = {"text": text, "role": role}
    if occurred_at:
        body["occurredAt"] = occurred_at
    return body


def _observe_response(resp: Any) -> ObserveResponse:
    """Normalize the engine's ``/memory/observe`` payload (camelCase
    ``candidateCount``) into an :class:`ObserveResponse`."""
    data = resp or {}
    saved = data.get("saved") or []
    count = data.get("candidateCount")
    return ObserveResponse(saved=saved, candidate_count=count if count is not None else len(saved))


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
        content: Optional[str] = None,
        *,
        text: Optional[str] = None,
        role: str = "user",
        subject: Optional[Subject] = None,
        type: Any = MemoryType.EVENT,
        scope: Any = MemoryScope.PROJECT,
        importance: int = 5,
        category: Optional[str] = None,
        activity_type: Optional[str] = None,
        occurred_at: Optional[str] = None,
        metadata: Optional[dict] = None,
        project_id: Optional[str] = None,
    ) -> ObserveResponse:
        """Record that *something happened*. The primary ingestion call for agents.

        **Preferred:** hand the engine the raw turn via ``text`` (with an optional
        ``role``, default ``"user"``). It runs through the engine's noise filter
        (extract → dedupe → budget) and only the memories worth keeping are
        stored — filler comes back as ``saved == []`` (success, not an error)::

            mm.memory.observe(text="Moved to the annual plan, prefers email.")

        **Legacy:** pass a pre-decided fact via ``content`` and it is stored
        verbatim (no extraction), then wrapped as a single-item response. Pass
        structured fields the miner reads via ``metadata`` — in particular the RFM
        Monetary score sums a numeric ``amount`` (or ``value``/``total``, or a
        ``lineItems`` array), so a price written only into ``content`` is not
        parsed; set it explicitly::

            mm.memory.observe(
                "Order — pizza",
                subject=subject("contact", "sarah"),
                activity_type="order_placed",
                metadata={"amount": 42.0},
            )

        Either ``text`` (preferred) or ``content`` is required.
        """
        if text is not None and text.strip():
            body = _observe_text_body(text, role, occurred_at)
            return _observe_response(self._t.post("/memory/observe", body, project_id))
        if content is not None and content.strip():
            body = _observe_body(content, subject, type, scope, importance, category, activity_type, occurred_at, metadata)
            item = self._t.post("/admin/memory", body, project_id)
            return ObserveResponse(saved=[item], candidate_count=1)
        raise ValueError("observe requires `text` (preferred) or `content`")

    def ingest_media(
        self,
        media: Union[bytes, str],
        mime_type: str,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        source: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> IngestMediaResult:
        """Ingest an image / audio / document. The engine extracts text (vision,
        transcription, or OCR via LiteLLM) and runs it through the observe
        pipeline, so the result is real memories — not just a stored file.
        Requires multimodal to be enabled on the engine."""
        body = _media_body(media, mime_type, user_id, agent_id, session_id, source)
        return self._t.post("/memory/media", body, project_id)

    def observe_image(
        self,
        subject: Subject,
        image: Union[bytes, str],
        mime_type: str,
        *,
        file_name: Optional[str] = None,
        content: Optional[str] = None,
        activity_type: Optional[str] = None,
        occurred_at: Optional[str] = None,
        importance: Optional[int] = None,
        metadata: Optional[dict] = None,
        project_id: Optional[str] = None,
    ) -> MemoryItem:
        """Record an image as a memory item. The bytes are uploaded as a
        MEMORY_ATTACHMENT file and a memory is created with the subject +
        activity metadata you provide. Pass ``content`` for the searchable
        caption — the engine doesn't auto-caption yet. ``image`` accepts raw
        bytes or a pre-encoded base64 string."""
        body = _attachment_body(
            image, subject, mime_type, file_name, content, activity_type, occurred_at, importance, metadata
        )
        return self._t.post("/memory/attachments", body, project_id)

    def observe_voice(
        self,
        subject: Subject,
        audio: Union[bytes, str],
        mime_type: str,
        *,
        file_name: Optional[str] = None,
        content: Optional[str] = None,
        activity_type: Optional[str] = None,
        occurred_at: Optional[str] = None,
        importance: Optional[int] = None,
        metadata: Optional[dict] = None,
        project_id: Optional[str] = None,
    ) -> MemoryItem:
        """Record a voice clip / audio file as a memory item. Pass ``content``
        for the searchable transcript — the engine doesn't auto-transcribe yet.
        ``audio`` accepts raw bytes or a pre-encoded base64 string."""
        body = _attachment_body(
            audio, subject, mime_type, file_name, content, activity_type, occurred_at, importance, metadata
        )
        return self._t.post("/memory/attachments", body, project_id)

    def observe_document(
        self,
        subject: Subject,
        document: Union[bytes, str],
        mime_type: str,
        *,
        file_name: Optional[str] = None,
        content: Optional[str] = None,
        activity_type: Optional[str] = None,
        occurred_at: Optional[str] = None,
        importance: Optional[int] = None,
        metadata: Optional[dict] = None,
        project_id: Optional[str] = None,
    ) -> MemoryItem:
        """Record a document (PDF, Word, Markdown, plain text, ...) as a memory
        item. Pass ``content`` for the searchable text — the engine doesn't
        auto-extract from PDFs/Office files yet, so parse first. ``document``
        accepts raw bytes or a pre-encoded base64 string."""
        body = _attachment_body(
            document, subject, mime_type, file_name, content, activity_type, occurred_at, importance, metadata
        )
        return self._t.post("/memory/attachments", body, project_id)

    def create(
        self,
        content: str,
        *,
        type: Any = MemoryType.FACT,
        scope: Any = MemoryScope.PROJECT,
        importance: int = 5,
        category: Optional[str] = None,
        metadata: Optional[dict] = None,
        occurred_at: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> MemoryItem:
        """Seed a memory directly (knowledge an agent should have without
        observing it first).

        `occurred_at` is the ISO-8601 time this became true in the world (event
        time). Set it when seeding anything back-dated — behavior mining buckets
        patterns by it, and it defaults to now.
        """
        body: dict = {"content": content, "type": enum_value(type), "scope": enum_value(scope), "importance": importance}
        if category:
            body["category"] = category
        if metadata:
            body["metadata"] = metadata
        if occurred_at:
            # Event time (when it became true in the world), not ingest time.
            body["validFrom"] = occurred_at
        return self._t.post("/admin/memory", body, project_id)

    def create_procedure(
        self,
        goal: str,
        steps: List[dict],
        *,
        when_to_use: Optional[str] = None,
        failure_modes: Optional[List[str]] = None,
        category: Optional[str] = None,
        scope: Any = MemoryScope.PROJECT,
        importance: int = 7,
        project_id: Optional[str] = None,
    ) -> MemoryItem:
        """Author a procedure — "how this job is done here" (goal + steps +
        failure modes). Stored as a ``procedure`` memory: the structured shape
        on ``metadata`` and the rendered how-to on ``content``, so retrieval
        injects it as an explicit exemplar."""
        metadata: dict = {"goal": goal, "steps": steps}
        if when_to_use:
            metadata["whenToUse"] = when_to_use
        if failure_modes:
            metadata["failureModes"] = failure_modes
        content = render_procedure_content(
            goal, steps, when_to_use=when_to_use, failure_modes=failure_modes
        )
        return self.create(
            content,
            type=MemoryType.PROCEDURE,
            scope=scope,
            importance=importance,
            category=category,
            metadata=metadata,
            project_id=project_id,
        )

    def list_pending_review(
        self, *, limit: Optional[int] = None, offset: Optional[int] = None, project_id: Optional[str] = None
    ) -> List[MemoryItem]:
        """The adjudication queue. Each row carries a ``reviewReason``:
        ``pending`` / ``flagged`` / ``low_confidence`` / ``stale``."""
        params = {k: v for k, v in {"limit": limit, "offset": offset}.items() if v is not None}
        return self._t.get("/admin/memory/review", params, project_id)

    def get_precedence(self, *, project_id: Optional[str] = None) -> dict:
        """Which memory wins when two disagree. Falls back to the default
        ladder (human-verified > local > licensed-brain > base) when unset."""
        return self._t.get("/admin/memory/precedence", None, project_id)

    def set_precedence(self, policy: dict, *, project_id: Optional[str] = None) -> dict:
        """Save the precedence policy. Requires the Memory Steward role."""
        return self._t.put("/admin/memory/precedence", policy, project_id)

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        offset: Optional[int] = None,
        scope: Any = None,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> List[SearchResult]:
        """Hybrid semantic + keyword search across every scope the project can see."""
        body: dict = {"query": query, "limit": limit}
        if offset:
            body["offset"] = offset
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

    def get(self, memory_id: str, *, project_id: Optional[str] = None) -> MemoryItem:
        """Fetch a single memory by id."""
        return self._t.get(f"/admin/memory/{memory_id}", None, project_id)

    def list_all(
        self,
        *,
        scope: Any = None,
        status: Optional[str] = None,
        type: Any = None,
        page_size: int = MAX_PAGE_SIZE,
        project_id: Optional[str] = None,
    ) -> SyncOffsetPaginator[MemoryItem]:
        """Walk every memory matching the filters, transparently paging under the
        hood. Returns an iterator (``for m in mm.memory.list_all(...)``) so a
        large corpus never has to fit in memory. Pages by offset over a
        newest-first list, so writes landing mid-walk can shift rows across page
        boundaries — fine for browsing/export."""

        def fetch(limit: int, offset: int) -> List[MemoryItem]:
            return self.list(
                scope=scope, status=status, type=type, limit=limit, offset=offset, project_id=project_id
            )

        return paginate(fetch, page_size=page_size)

    def list_platform(
        self,
        *,
        status: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> List[MemoryItem]:
        """List platform-level memories (shared across all projects on this
        platform)."""
        params = {k: v for k, v in {"status": status, "limit": limit, "offset": offset}.items() if v is not None}
        return self._t.get("/admin/memory/platform", params, project_id)

    def mine(
        self,
        *,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> List[MemoryItem]:
        """List the current user's memories across all scopes."""
        params = {k: v for k, v in {"limit": limit, "offset": offset}.items() if v is not None}
        return self._t.get("/memory/mine", params, project_id)

    def explain(self, memory_id: str, *, project_id: Optional[str] = None) -> ExplainResult:
        """Right-to-explanation. For a derived item (e.g. ``behavior_pattern``),
        resolve the raw source memories that produced it from
        ``metadata.sourceMemoryIds``. For any other item, returns the item with
        an empty ``sourceMemories``. Sources since deleted/superseded are skipped
        rather than failing the whole call."""
        memory = self.get(memory_id, project_id=project_id)
        ids = _explain_source_ids(memory)
        sources: List[MemoryItem] = []
        for source_id in ids:
            try:
                sources.append(self.get(source_id, project_id=project_id))
            except Exception:
                continue
        return {"memory": memory, "sourceMemories": sources}

    def list_feedback(self, memory_id: str, *, project_id: Optional[str] = None) -> List[MemoryFeedback]:
        """List the feedback records attached to a memory item — useful when
        inspecting auto-flagged items to decide whether to confirm or reject."""
        return self._t.get(f"/admin/memory/{memory_id}/feedback", None, project_id)

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

    def get(self, memory_id: str, *, project_id: Optional[str] = None) -> MemoryItem:
        """Fetch a single memory by id.

        The point-lookup counterpart to list()/search(): without it, a caller
        holding a memory id (from a pattern's sourceMemoryIds, an audit log, a
        webhook) had no way to resolve it and had to page list() hoping the row
        was still on one.
        """
        return self._t.get(f"/admin/memory/{memory_id}", None, project_id)

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
        return self._t.post("/admin/memory/llm-consolidate", body, project_id)

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
        content: Optional[str] = None,
        *,
        text: Optional[str] = None,
        role: str = "user",
        subject: Optional[Subject] = None,
        type: Any = MemoryType.EVENT,
        scope: Any = MemoryScope.PROJECT,
        importance: int = 5,
        category: Optional[str] = None,
        activity_type: Optional[str] = None,
        occurred_at: Optional[str] = None,
        metadata: Optional[dict] = None,
        project_id: Optional[str] = None,
    ) -> ObserveResponse:
        """Async mirror of :meth:`MemoryResource.observe`. Prefer ``text`` (raw
        turn through the engine's noise filter); ``content`` stays for legacy
        verbatim stores. Either ``text`` or ``content`` is required."""
        if text is not None and text.strip():
            body = _observe_text_body(text, role, occurred_at)
            return _observe_response(await self._t.post("/memory/observe", body, project_id))
        if content is not None and content.strip():
            body = _observe_body(content, subject, type, scope, importance, category, activity_type, occurred_at, metadata)
            item = await self._t.post("/admin/memory", body, project_id)
            return ObserveResponse(saved=[item], candidate_count=1)
        raise ValueError("observe requires `text` (preferred) or `content`")

    async def ingest_media(
        self,
        media: Union[bytes, str],
        mime_type: str,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        source: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> IngestMediaResult:
        """Async mirror of :meth:`MemoryResource.ingest_media`."""
        body = _media_body(media, mime_type, user_id, agent_id, session_id, source)
        return await self._t.post("/memory/media", body, project_id)

    async def observe_image(
        self,
        subject: Subject,
        image: Union[bytes, str],
        mime_type: str,
        *,
        file_name: Optional[str] = None,
        content: Optional[str] = None,
        activity_type: Optional[str] = None,
        occurred_at: Optional[str] = None,
        importance: Optional[int] = None,
        metadata: Optional[dict] = None,
        project_id: Optional[str] = None,
    ) -> MemoryItem:
        """Async mirror of :meth:`MemoryResource.observe_image`."""
        body = _attachment_body(
            image, subject, mime_type, file_name, content, activity_type, occurred_at, importance, metadata
        )
        return await self._t.post("/memory/attachments", body, project_id)

    async def observe_voice(
        self,
        subject: Subject,
        audio: Union[bytes, str],
        mime_type: str,
        *,
        file_name: Optional[str] = None,
        content: Optional[str] = None,
        activity_type: Optional[str] = None,
        occurred_at: Optional[str] = None,
        importance: Optional[int] = None,
        metadata: Optional[dict] = None,
        project_id: Optional[str] = None,
    ) -> MemoryItem:
        """Async mirror of :meth:`MemoryResource.observe_voice`."""
        body = _attachment_body(
            audio, subject, mime_type, file_name, content, activity_type, occurred_at, importance, metadata
        )
        return await self._t.post("/memory/attachments", body, project_id)

    async def observe_document(
        self,
        subject: Subject,
        document: Union[bytes, str],
        mime_type: str,
        *,
        file_name: Optional[str] = None,
        content: Optional[str] = None,
        activity_type: Optional[str] = None,
        occurred_at: Optional[str] = None,
        importance: Optional[int] = None,
        metadata: Optional[dict] = None,
        project_id: Optional[str] = None,
    ) -> MemoryItem:
        """Async mirror of :meth:`MemoryResource.observe_document`."""
        body = _attachment_body(
            document, subject, mime_type, file_name, content, activity_type, occurred_at, importance, metadata
        )
        return await self._t.post("/memory/attachments", body, project_id)

    async def create(
        self,
        content: str,
        *,
        type: Any = MemoryType.FACT,
        scope: Any = MemoryScope.PROJECT,
        importance: int = 5,
        category: Optional[str] = None,
        metadata: Optional[dict] = None,
        occurred_at: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> MemoryItem:
        body: dict = {"content": content, "type": enum_value(type), "scope": enum_value(scope), "importance": importance}
        if occurred_at:
            # Event time (when it became true in the world), not ingest time.
            body["validFrom"] = occurred_at
        if category:
            body["category"] = category
        if metadata:
            body["metadata"] = metadata
        return await self._t.post("/admin/memory", body, project_id)

    async def create_procedure(
        self,
        goal: str,
        steps: List[dict],
        *,
        when_to_use: Optional[str] = None,
        failure_modes: Optional[List[str]] = None,
        category: Optional[str] = None,
        scope: Any = MemoryScope.PROJECT,
        importance: int = 7,
        project_id: Optional[str] = None,
    ) -> MemoryItem:
        """Author a procedure (async). See :meth:`MemoryResource.create_procedure`."""
        metadata: dict = {"goal": goal, "steps": steps}
        if when_to_use:
            metadata["whenToUse"] = when_to_use
        if failure_modes:
            metadata["failureModes"] = failure_modes
        content = render_procedure_content(
            goal, steps, when_to_use=when_to_use, failure_modes=failure_modes
        )
        return await self.create(
            content,
            type=MemoryType.PROCEDURE,
            scope=scope,
            importance=importance,
            category=category,
            metadata=metadata,
            project_id=project_id,
        )

    async def list_pending_review(
        self, *, limit: Optional[int] = None, offset: Optional[int] = None, project_id: Optional[str] = None
    ) -> List[MemoryItem]:
        """The adjudication queue (async). Rows carry a ``reviewReason``."""
        params = {k: v for k, v in {"limit": limit, "offset": offset}.items() if v is not None}
        return await self._t.get("/admin/memory/review", params, project_id)

    async def get_precedence(self, *, project_id: Optional[str] = None) -> dict:
        """Read the precedence policy (async)."""
        return await self._t.get("/admin/memory/precedence", None, project_id)

    async def set_precedence(self, policy: dict, *, project_id: Optional[str] = None) -> dict:
        """Save the precedence policy (async). Requires the Memory Steward role."""
        return await self._t.put("/admin/memory/precedence", policy, project_id)

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        offset: Optional[int] = None,
        scope: Any = None,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> List[SearchResult]:
        body: dict = {"query": query, "limit": limit}
        if offset:
            body["offset"] = offset
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

    async def get(self, memory_id: str, *, project_id: Optional[str] = None) -> MemoryItem:
        """Fetch a single memory by id (async)."""
        return await self._t.get(f"/admin/memory/{memory_id}", None, project_id)

    def list_all(
        self,
        *,
        scope: Any = None,
        status: Optional[str] = None,
        type: Any = None,
        page_size: int = MAX_PAGE_SIZE,
        project_id: Optional[str] = None,
    ) -> AsyncOffsetPaginator[MemoryItem]:
        """Async mirror of :meth:`MemoryResource.list_all`. Returns an async
        iterator (``async for m in mm.memory.list_all(...)``)."""

        async def fetch(limit: int, offset: int) -> List[MemoryItem]:
            return await self.list(
                scope=scope, status=status, type=type, limit=limit, offset=offset, project_id=project_id
            )

        return apaginate(fetch, page_size=page_size)

    async def list_platform(
        self,
        *,
        status: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> List[MemoryItem]:
        """List platform-level memories (async)."""
        params = {k: v for k, v in {"status": status, "limit": limit, "offset": offset}.items() if v is not None}
        return await self._t.get("/admin/memory/platform", params, project_id)

    async def mine(
        self,
        *,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> List[MemoryItem]:
        """List the current user's memories across all scopes (async)."""
        params = {k: v for k, v in {"limit": limit, "offset": offset}.items() if v is not None}
        return await self._t.get("/memory/mine", params, project_id)

    async def explain(self, memory_id: str, *, project_id: Optional[str] = None) -> ExplainResult:
        """Async mirror of :meth:`MemoryResource.explain`. Source lookups run
        concurrently; sources since deleted/superseded are skipped."""
        memory = await self.get(memory_id, project_id=project_id)
        ids = _explain_source_ids(memory)
        if not ids:
            return {"memory": memory, "sourceMemories": []}

        async def _fetch(source_id: str) -> Optional[MemoryItem]:
            try:
                return await self.get(source_id, project_id=project_id)
            except Exception:
                return None

        results = await asyncio.gather(*[_fetch(source_id) for source_id in ids])
        sources = [m for m in results if m is not None]
        return {"memory": memory, "sourceMemories": sources}

    async def list_feedback(
        self, memory_id: str, *, project_id: Optional[str] = None
    ) -> List[MemoryFeedback]:
        """List the feedback records attached to a memory item (async)."""
        return await self._t.get(f"/admin/memory/{memory_id}/feedback", None, project_id)

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

    async def get(self, memory_id: str, *, project_id: Optional[str] = None) -> MemoryItem:
        """Fetch a single memory by id. See MemoryResource.get."""
        return await self._t.get(f"/admin/memory/{memory_id}", None, project_id)

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
        return await self._t.post("/admin/memory/llm-consolidate", body, project_id)

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
