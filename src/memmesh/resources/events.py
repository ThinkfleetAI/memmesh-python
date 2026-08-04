"""Events resource — the durable memory event log (Phase 3i).

The engine emits durable events on interesting state changes — pattern
emergence, risk firing, segment shift, consent change. Consume them by polling
:meth:`poll` (walk the log with each event's ``occurredAt`` as the next
``since``), or let :meth:`subscribe` run that loop for you in the background and
invoke a handler per event. The write-side counterpart is :meth:`emit`. Mirrors
``thinkfleet-memory-sdk``'s ``resources/events.ts`` — poll / emit / subscribe.

>>> from memmesh import MemMesh
>>> mm = MemMesh(api_key="sk-...", project_id="proj_...")
>>> stop = mm.events.subscribe(
...     lambda e: print(e["eventType"], e["subject"]),
...     event_types=["risk.fired", "segment.changed"],
...     interval_ms=3_000,
... )
>>> # later: stop()
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable, List, Optional

from ..types import EmitEventRequest, EmitEventResult, MemoryEvent


def _poll_params(
    since: Optional[str],
    limit: Optional[int],
    event_types: Optional[List[str]],
) -> dict:
    """Build the query for a poll — ``eventTypes`` is comma-joined (as the API
    expects) only when non-empty; ``None`` values are dropped by the transport."""
    params: dict = {"since": since, "limit": limit}
    if event_types:
        params["eventTypes"] = ",".join(event_types)
    return params


def _clamp_interval_seconds(interval_ms: int) -> float:
    """Mirror the TS floor: at least 500ms between polls."""
    return max(500, interval_ms) / 1000.0


class EventsResource:
    """Synchronous event log operations."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def poll(
        self,
        *,
        since: Optional[str] = None,
        limit: Optional[int] = None,
        event_types: Optional[List[str]] = None,
        project_id: Optional[str] = None,
    ) -> List[MemoryEvent]:
        """Pull events newer than ``since``. Single round-trip; use the last
        event's ``occurredAt`` as the next ``since`` to walk the log. ``limit``
        defaults to 100 server-side (max 1000); ``event_types`` restricts to
        specific types."""
        params = _poll_params(since, limit, event_types)
        return self._t.get("/memory-events", params, project_id)

    def emit(self, body: EmitEventRequest, *, project_id: Optional[str] = None) -> EmitEventResult:
        """Append an event to the durable log. Matching alert rules fire
        synchronously. The write-side counterpart to :meth:`poll`."""
        return self._t.post("/lattice/events/emit", body, project_id)

    def subscribe(
        self,
        handler: Callable[[MemoryEvent], Any],
        *,
        since: Optional[str] = None,
        limit: Optional[int] = None,
        event_types: Optional[List[str]] = None,
        interval_ms: int = 5000,
        project_id: Optional[str] = None,
    ) -> Callable[[], None]:
        """Poll in a background thread and invoke ``handler`` for each event.
        Returns an unsubscribe callable that stops the loop (promptly — it
        interrupts the inter-poll sleep). Handler and network errors are
        swallowed so a single failure never kills the loop, matching the TS
        ``subscribe``."""
        stop = threading.Event()
        cursor: Optional[str] = since
        interval = _clamp_interval_seconds(interval_ms)

        def loop() -> None:
            nonlocal cursor
            while not stop.is_set():
                try:
                    events = self.poll(
                        since=cursor,
                        limit=limit,
                        event_types=event_types,
                        project_id=project_id,
                    )
                    for e in events:
                        if stop.is_set():
                            break
                        try:
                            handler(e)
                        except Exception:
                            # handler errors are the caller's concern; keep going
                            pass
                        cursor = e.get("occurredAt", cursor)
                except Exception:
                    # network blip — back off (below) and retry
                    pass
                # interruptible sleep: unsubscribe wakes it immediately
                stop.wait(interval)

        thread = threading.Thread(target=loop, name="memmesh-events-subscribe", daemon=True)
        thread.start()

        def unsubscribe() -> None:
            stop.set()

        return unsubscribe


class AsyncEventsResource:
    """Asynchronous mirror of :class:`EventsResource`."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    async def poll(
        self,
        *,
        since: Optional[str] = None,
        limit: Optional[int] = None,
        event_types: Optional[List[str]] = None,
        project_id: Optional[str] = None,
    ) -> List[MemoryEvent]:
        params = _poll_params(since, limit, event_types)
        return await self._t.get("/memory-events", params, project_id)

    async def emit(
        self, body: EmitEventRequest, *, project_id: Optional[str] = None
    ) -> EmitEventResult:
        return await self._t.post("/lattice/events/emit", body, project_id)

    def subscribe(
        self,
        handler: Callable[[MemoryEvent], Any],
        *,
        since: Optional[str] = None,
        limit: Optional[int] = None,
        event_types: Optional[List[str]] = None,
        interval_ms: int = 5000,
        project_id: Optional[str] = None,
    ) -> Callable[[], None]:
        """Poll in a background :class:`asyncio.Task` and invoke ``handler`` for
        each event (``handler`` may be sync or a coroutine function). Not itself
        a coroutine — call it from within a running loop and it schedules the
        task, returning a synchronous unsubscribe callable (mirrors the TS
        ``() => void``). Must be called with a running event loop."""
        stop = asyncio.Event()
        cursor: Optional[str] = since
        interval = _clamp_interval_seconds(interval_ms)

        async def loop() -> None:
            nonlocal cursor
            while not stop.is_set():
                try:
                    events = await self.poll(
                        since=cursor,
                        limit=limit,
                        event_types=event_types,
                        project_id=project_id,
                    )
                    for e in events:
                        if stop.is_set():
                            break
                        try:
                            result = handler(e)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception:
                            pass
                        cursor = e.get("occurredAt", cursor)
                except Exception:
                    pass
                try:
                    await asyncio.wait_for(stop.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    pass

        task = asyncio.ensure_future(loop())

        def unsubscribe() -> None:
            stop.set()
            task.cancel()

        return unsubscribe


__all__ = ["EventsResource", "AsyncEventsResource"]
