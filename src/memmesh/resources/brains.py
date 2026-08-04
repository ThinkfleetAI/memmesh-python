"""Brains resource — the marketplace registry.

Register, version, and manage the brains a project publishes. A brain carries a
Brain Card manifest (ontology, provenance, coverage, eval, pricing) and a stable
``externalId`` slug. Once a brain is ``PUBLISHED`` + ``PUBLIC``, any caller can
consume it over the hosted MCP endpoint
(``/brains/{brainId}/mcp-server/http``); consumption is an MCP connection, not a
REST call, so it lives outside this resource. Mirrors
``thinkfleet-memory-sdk``'s ``resources/brains.ts``.
"""

from __future__ import annotations

from typing import Any, Optional

from .._pagination import (
    AsyncCursorPaginator,
    SyncCursorPaginator,
    apaginate_cursor,
    paginate_cursor,
)
from ..types import (
    Brain,
    BrainCard,
    BrainVisibility,
    CreateBrainRequest,
    SeekPage,
    UpdateBrainRequest,
)


class BrainsResource:
    """Synchronous brain-registry operations."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def create(self, body: CreateBrainRequest, *, project_id: Optional[str] = None) -> Brain:
        """Register a new brain in the project's catalog."""
        return self._t.post("/brains", body, project_id)

    def create_from_project(
        self,
        *,
        external_id: str,
        name: str,
        domain: Optional[str] = None,
        version: Optional[str] = None,
        visibility: Optional[BrainVisibility] = None,
        project_id: Optional[str] = None,
    ) -> Brain:
        """Create a brain from the calling project's memory — the easy,
        high-level path.

        Where :meth:`create` wants a full ``CreateBrainRequest``, this builds a
        sensible one for you from just a slug + name (plus optional domain /
        version / visibility) and an empty-but-valid Brain Card. Coverage
        (subjects, facts, and the induced reasoning layer) is computed
        server-side from the project's own memory, so you don't pass it. The
        brain is created as a DRAFT + PRIVATE; publishing and pricing are
        deliberate, separate steps.
        """
        empty_card: BrainCard = {"provenance": [], "coverage": {}}
        body: CreateBrainRequest = {
            "externalId": external_id,
            "name": name,
            "domain": domain if domain is not None else "",
            "version": version if version is not None else "1.0.0",
            "visibility": visibility if visibility is not None else "PRIVATE",
            # Empty-but-valid card: an empty provenance list and empty coverage.
            # The server recomputes coverage from the project's memory; a real
            # licensed provenance source is only required to publish PUBLIC (a
            # separate step).
            "card": empty_card,
        }
        if domain is None:
            del body["domain"]  # type: ignore[misc]
        return self.create(body, project_id=project_id)

    def list(
        self,
        *,
        limit: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> SyncCursorPaginator[Brain]:
        """List the project's brains (cursor-paginated). Returns an iterator
        (``for b in mm.brains.list()``) that transparently walks every page,
        following the ``SeekPage`` ``next`` cursor under the hood. Iterate whole
        pages instead with ``.pages()``."""

        def fetch(cursor: Optional[str]) -> SeekPage:
            params = {"limit": limit, "cursor": cursor}
            return self._t.get("/brains", params, project_id)

        return paginate_cursor(fetch)

    def get(self, brain_id: str, *, project_id: Optional[str] = None) -> Brain:
        """Fetch one brain by id."""
        return self._t.get(f"/brains/{brain_id}", None, project_id)

    def update(
        self, brain_id: str, body: UpdateBrainRequest, *, project_id: Optional[str] = None
    ) -> Brain:
        """Update / version a brain (name, version, visibility, status, card, …)."""
        return self._t.patch(f"/brains/{brain_id}", body, project_id)

    def delete(self, brain_id: str, *, project_id: Optional[str] = None) -> None:
        """Delete a brain from the catalog."""
        return self._t.delete(f"/brains/{brain_id}", project_id)


class AsyncBrainsResource:
    """Asynchronous mirror of :class:`BrainsResource`."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    async def create(
        self, body: CreateBrainRequest, *, project_id: Optional[str] = None
    ) -> Brain:
        return await self._t.post("/brains", body, project_id)

    async def create_from_project(
        self,
        *,
        external_id: str,
        name: str,
        domain: Optional[str] = None,
        version: Optional[str] = None,
        visibility: Optional[BrainVisibility] = None,
        project_id: Optional[str] = None,
    ) -> Brain:
        """Async mirror of :meth:`BrainsResource.create_from_project`."""
        empty_card: BrainCard = {"provenance": [], "coverage": {}}
        body: CreateBrainRequest = {
            "externalId": external_id,
            "name": name,
            "domain": domain if domain is not None else "",
            "version": version if version is not None else "1.0.0",
            "visibility": visibility if visibility is not None else "PRIVATE",
            "card": empty_card,
        }
        if domain is None:
            del body["domain"]  # type: ignore[misc]
        return await self.create(body, project_id=project_id)

    def list(
        self,
        *,
        limit: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> AsyncCursorPaginator[Brain]:
        """Async mirror of :meth:`BrainsResource.list`. Returns an async iterator
        (``async for b in mm.brains.list()``)."""

        async def fetch(cursor: Optional[str]) -> SeekPage:
            params = {"limit": limit, "cursor": cursor}
            return await self._t.get("/brains", params, project_id)

        return apaginate_cursor(fetch)

    async def get(self, brain_id: str, *, project_id: Optional[str] = None) -> Brain:
        return await self._t.get(f"/brains/{brain_id}", None, project_id)

    async def update(
        self, brain_id: str, body: UpdateBrainRequest, *, project_id: Optional[str] = None
    ) -> Brain:
        return await self._t.patch(f"/brains/{brain_id}", body, project_id)

    async def delete(self, brain_id: str, *, project_id: Optional[str] = None) -> None:
        return await self._t.delete(f"/brains/{brain_id}", project_id)


__all__ = ["BrainsResource", "AsyncBrainsResource"]
