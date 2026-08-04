"""Alerts resource — user-defined alert rules (Phase 3j).

Define "tell me when X happens, this way" rules that hook into the engine event
stream. Triggers match against the same event types :meth:`EventsResource.poll`
returns; channels deliver via HTTP webhook or write the alert back as a memory
item for the LLM to pick up on its next ``context.build()``. Mirrors
``thinkfleet-memory-sdk``'s ``resources/alerts.ts`` — 8 operations, one-for-one.

>>> from memmesh import MemMesh
>>> mm = MemMesh(api_key="sk-...", project_id="proj_...")
>>> mm.alerts.create({
...     "name": "VIP at risk",
...     "trigger": {"kind": "engine-event", "eventTypes": ["risk.fired"]},
...     "filter": {"metadataMatch": {"riskKind": "rfm_at_risk_high_value"}},
...     "notify": [{"kind": "webhook", "url": "https://hooks.slack.com/..."}],
...     "throttle": {"dedupOn": "subject", "cooldownMinutes": 60},
... })
"""

from __future__ import annotations

from typing import Any, List, Optional

from ..types import (
    AlertFire,
    AlertRule,
    CreateAlertRuleRequest,
    UpdateAlertRuleRequest,
)


class AlertsResource:
    """Synchronous alert-rule operations."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def list(self, *, project_id: Optional[str] = None) -> List[AlertRule]:
        """List the project's alert rules."""
        return self._t.get("/memory-alerts", None, project_id)

    def get(self, alert_id: str, *, project_id: Optional[str] = None) -> AlertRule:
        """Fetch one alert rule by id."""
        return self._t.get(f"/memory-alerts/{alert_id}", None, project_id)

    def create(self, body: CreateAlertRuleRequest, *, project_id: Optional[str] = None) -> AlertRule:
        """Create an alert rule (trigger + optional filter + notify channels)."""
        return self._t.post("/memory-alerts", body, project_id)

    def update(
        self, alert_id: str, body: UpdateAlertRuleRequest, *, project_id: Optional[str] = None
    ) -> AlertRule:
        """Update an alert rule — any subset of fields."""
        return self._t.patch(f"/memory-alerts/{alert_id}", body, project_id)

    def delete(self, alert_id: str, *, project_id: Optional[str] = None) -> None:
        """Delete an alert rule."""
        return self._t.delete(f"/memory-alerts/{alert_id}", project_id)

    def enable(self, alert_id: str, *, project_id: Optional[str] = None) -> AlertRule:
        """Convenience — patch only the ``enabled`` flag to ``True``."""
        return self.update(alert_id, {"enabled": True}, project_id=project_id)

    def disable(self, alert_id: str, *, project_id: Optional[str] = None) -> AlertRule:
        """Convenience — patch only the ``enabled`` flag to ``False``."""
        return self.update(alert_id, {"enabled": False}, project_id=project_id)

    def list_fires(self, alert_id: str, *, project_id: Optional[str] = None) -> List[AlertFire]:
        """Last ~100 fires for an alert rule, newest first."""
        return self._t.get(f"/memory-alerts/{alert_id}/fires", None, project_id)


class AsyncAlertsResource:
    """Asynchronous mirror of :class:`AlertsResource`."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    async def list(self, *, project_id: Optional[str] = None) -> List[AlertRule]:
        return await self._t.get("/memory-alerts", None, project_id)

    async def get(self, alert_id: str, *, project_id: Optional[str] = None) -> AlertRule:
        return await self._t.get(f"/memory-alerts/{alert_id}", None, project_id)

    async def create(
        self, body: CreateAlertRuleRequest, *, project_id: Optional[str] = None
    ) -> AlertRule:
        return await self._t.post("/memory-alerts", body, project_id)

    async def update(
        self, alert_id: str, body: UpdateAlertRuleRequest, *, project_id: Optional[str] = None
    ) -> AlertRule:
        return await self._t.patch(f"/memory-alerts/{alert_id}", body, project_id)

    async def delete(self, alert_id: str, *, project_id: Optional[str] = None) -> None:
        return await self._t.delete(f"/memory-alerts/{alert_id}", project_id)

    async def enable(self, alert_id: str, *, project_id: Optional[str] = None) -> AlertRule:
        return await self.update(alert_id, {"enabled": True}, project_id=project_id)

    async def disable(self, alert_id: str, *, project_id: Optional[str] = None) -> AlertRule:
        return await self.update(alert_id, {"enabled": False}, project_id=project_id)

    async def list_fires(
        self, alert_id: str, *, project_id: Optional[str] = None
    ) -> List[AlertFire]:
        return await self._t.get(f"/memory-alerts/{alert_id}/fires", None, project_id)


__all__ = ["AlertsResource", "AsyncAlertsResource"]
