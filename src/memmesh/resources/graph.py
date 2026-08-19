"""Knowledge-graph resource — the structural half of memory.

Observing text doesn't only produce embeddable rows; extraction also resolves
entities and writes typed edges between them. That graph is what reaches a fact
no single memory states outright ("who does Sarah report to?" answered from
``sarah -[member_of]-> team`` plus ``team -[led_by]-> priya``).

Both records are bi-temporal, and the two time axes mean different things:

* ``valid_from`` / ``valid_to`` — when the fact was TRUE in the world.
* ``expired_at`` (edges) — when the graph stopped BELIEVING it, because a
  contradicting edge superseded it.

A fact that was true last year and a fact we were wrong about are not the same
thing, and collapsing them loses the audit trail.

Read-only by design. Entities and edges are written by extraction when you
:meth:`~memmesh.resources.memory.MemoryResource.observe`; the server's manual
create/retire routes exist for annotation tooling, and exposing them here would
invite hand-maintained graphs — which is the work the engine exists to do.

Mirrors ``@memmesh/sdk``'s ``resources/graph.ts``.
"""

from __future__ import annotations

from typing import Any, List, Optional

from ..types import EntityWithEdges, GraphStats, GraphTraversalEdge, MemoryEntity


def _entity_params(
    type: Optional[str],
    scope: Optional[str],
    search: Optional[str],
    limit: Optional[int],
    offset: Optional[int],
) -> dict:
    params: dict = {}
    if type is not None:
        params["type"] = type
    if scope is not None:
        params["scope"] = scope
    if search is not None:
        params["search"] = search
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    return params


def _traverse_body(
    entity_id: str,
    hops: Optional[int],
    predicates: Optional[List[str]],
    as_of: Optional[str],
) -> dict:
    body: dict = {"entityId": entity_id}
    if hops is not None:
        body["hops"] = hops
    if predicates is not None:
        body["predicates"] = predicates
    if as_of is not None:
        body["asOf"] = as_of
    return body


class GraphResource:
    """Synchronous knowledge-graph reads."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def stats(self, *, project_id: Optional[str] = None) -> GraphStats:
        """Aggregate counts for the whole graph.

        Prefer this over ``len(list_entities())`` for any "how big is it"
        question: these are SQL ``COUNT(*)``s over the full table, where the
        list routes page and would report the page size as the total.
        """
        return self._t.get("/admin/memory/graph/stats", None, project_id)

    def list_entities(
        self,
        *,
        type: Optional[str] = None,
        scope: Optional[str] = None,
        search: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> List[MemoryEntity]:
        """Entities, filtered by type/scope or a substring of name or alias."""
        return self._t.get(
            "/admin/memory/entities",
            _entity_params(type, scope, search, limit, offset),
            project_id,
        )

    def get_entity(
        self,
        entity_id: str,
        *,
        as_of: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> EntityWithEdges:
        """One entity plus its 1-hop neighbourhood."""
        params = {"asOf": as_of} if as_of else None
        return self._t.get(f"/admin/memory/entities/{entity_id}", params, project_id)

    def list_edges(
        self,
        *,
        as_of: Optional[str] = None,
        limit: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> List[GraphTraversalEdge]:
        """Every currently-valid edge.

        Use for rendering a whole small graph; for a large one, seed from an
        entity and :meth:`traverse` instead.
        """
        params: dict = {}
        if as_of is not None:
            params["asOf"] = as_of
        if limit is not None:
            params["limit"] = limit
        return self._t.get("/admin/memory/graph/edges", params, project_id)

    def traverse(
        self,
        entity_id: str,
        *,
        hops: Optional[int] = None,
        predicates: Optional[List[str]] = None,
        as_of: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> List[GraphTraversalEdge]:
        """Walk out from a seed entity (1-3 hops).

        This is the multi-hop path: the edges returned here connect facts no
        single memory states together, which is how a question gets answered
        from a chain rather than from one lucky vector hit.
        """
        return self._t.post(
            "/admin/memory/graph/traverse",
            _traverse_body(entity_id, hops, predicates, as_of),
            project_id,
        )


class AsyncGraphResource:
    """Async mirror of :class:`GraphResource`."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    async def stats(self, *, project_id: Optional[str] = None) -> GraphStats:
        """Async mirror of :meth:`GraphResource.stats`."""
        return await self._t.get("/admin/memory/graph/stats", None, project_id)

    async def list_entities(
        self,
        *,
        type: Optional[str] = None,
        scope: Optional[str] = None,
        search: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> List[MemoryEntity]:
        """Async mirror of :meth:`GraphResource.list_entities`."""
        return await self._t.get(
            "/admin/memory/entities",
            _entity_params(type, scope, search, limit, offset),
            project_id,
        )

    async def get_entity(
        self,
        entity_id: str,
        *,
        as_of: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> EntityWithEdges:
        """Async mirror of :meth:`GraphResource.get_entity`."""
        params = {"asOf": as_of} if as_of else None
        return await self._t.get(f"/admin/memory/entities/{entity_id}", params, project_id)

    async def list_edges(
        self,
        *,
        as_of: Optional[str] = None,
        limit: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> List[GraphTraversalEdge]:
        """Async mirror of :meth:`GraphResource.list_edges`."""
        params: dict = {}
        if as_of is not None:
            params["asOf"] = as_of
        if limit is not None:
            params["limit"] = limit
        return await self._t.get("/admin/memory/graph/edges", params, project_id)

    async def traverse(
        self,
        entity_id: str,
        *,
        hops: Optional[int] = None,
        predicates: Optional[List[str]] = None,
        as_of: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> List[GraphTraversalEdge]:
        """Async mirror of :meth:`GraphResource.traverse`."""
        return await self._t.post(
            "/admin/memory/graph/traverse",
            _traverse_body(entity_id, hops, predicates, as_of),
            project_id,
        )
