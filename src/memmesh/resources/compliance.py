"""Compliance resource — GDPR-grade export, erasure, audit, and packs.

Two subject-scoped operations:

* :meth:`export_subject` (Art. 15) — return every memory, pattern, observation,
  event, and alert fire for the subject in a single bundle the controller can
  hand to the data subject.
* :meth:`hard_delete_subject` (Art. 17) — cascade-delete the same set and write
  a tombstone audit row so the deletion itself is auditable.

Plus the audit log (:meth:`list_audit_events`) and compliance-pack management
(:meth:`list_packs`, :meth:`list_project_packs`, :meth:`upsert_project_pack`,
:meth:`remove_project_pack`). Served under ``/memory-compliance/*`` and
``/memory-compliance-packs``. Mirrors ``thinkfleet-memory-sdk``'s
``resources/compliance.ts``.
"""

from __future__ import annotations

from typing import Any, List, Optional
from urllib.parse import quote

from ..types import (
    AuditEvent,
    CompliancePack,
    ComplianceSubject,
    ExportSubjectResponse,
    HardDeleteSubjectResponse,
    ProjectPackEnablement,
)


def _hard_delete_body(
    subject: ComplianceSubject, reason: str, dry_run: Optional[bool]
) -> dict:
    body: dict = {"subject": subject, "reason": reason}
    if dry_run is not None:
        body["dryRun"] = dry_run
    return body


def _audit_query(
    subject: Optional[ComplianceSubject],
    actor: Optional[str],
    event_types: Optional[List[str]],
    since: Optional[str],
    limit: Optional[int],
) -> dict:
    query: dict = {
        "subjectKind": subject["kind"] if subject else None,
        "subjectExternalId": subject["externalId"] if subject else None,
        "actor": actor,
        "since": since,
        "limit": limit,
    }
    if event_types:
        query["eventTypes"] = ",".join(event_types)
    return query


def _upsert_pack_body(pack_id: str, enabled: bool, config: Optional[dict]) -> dict:
    body: dict = {"packId": pack_id, "enabled": enabled}
    if config is not None:
        body["config"] = config
    return body


class ComplianceResource:
    """Synchronous compliance operations."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def export_subject(
        self, subject: ComplianceSubject, *, project_id: Optional[str] = None
    ) -> ExportSubjectResponse:
        """Art. 15 subject-access export — every memory, pattern, observation,
        event, and alert fire for the subject in one bundle."""
        return self._t.post("/memory-compliance/export", {"subject": subject}, project_id)

    def hard_delete_subject(
        self,
        subject: ComplianceSubject,
        *,
        reason: str,
        dry_run: Optional[bool] = None,
        project_id: Optional[str] = None,
    ) -> HardDeleteSubjectResponse:
        """Art. 17 right-to-erasure — cascade-delete the subject's data and write
        a tombstone audit row. ``reason`` is required (audit case id). Pass
        ``dry_run=True`` for a preview that touches no rows."""
        return self._t.post(
            "/memory-compliance/hard-delete",
            _hard_delete_body(subject, reason, dry_run),
            project_id,
        )

    def list_audit_events(
        self,
        *,
        subject: Optional[ComplianceSubject] = None,
        actor: Optional[str] = None,
        event_types: Optional[List[str]] = None,
        since: Optional[str] = None,
        limit: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> List[AuditEvent]:
        """Read the memory_audit_event log. GDPR Art. 15 "who accessed my data
        and when." Pass a ``subject`` to narrow to one person's access log; omit
        for project-wide audit."""
        return self._t.get(
            "/memory-compliance/audit",
            _audit_query(subject, actor, event_types, since, limit),
            project_id,
        )

    def list_packs(self, *, project_id: Optional[str] = None) -> List[CompliancePack]:
        """List installed compliance packs. Packs claim jurisdiction over
        specific memory classes (e.g. HIPAA → ``phi``) and enforce
        domain-specific redaction / consent / retention rules on every read."""
        return self._t.get("/memory-compliance/packs", None, project_id)

    def list_project_packs(
        self, *, project_id: Optional[str] = None
    ) -> List[ProjectPackEnablement]:
        """List which compliance packs are enabled (or explicitly disabled) for
        the current project. Packs not appearing fall back to the platform
        default set (``MEMORY_DEFAULT_PACK_IDS``)."""
        return self._t.get("/memory-compliance-packs", None, project_id)

    def upsert_project_pack(
        self,
        *,
        pack_id: str,
        enabled: bool,
        config: Optional[dict] = None,
        project_id: Optional[str] = None,
    ) -> ProjectPackEnablement:
        """Enable, disable, or update the config for a compliance pack in the
        current project. Idempotent — same ``pack_id`` updates the existing row
        in place. Changes propagate to the Rust engine within the cache TTL
        (~30s)."""
        return self._t.post(
            "/memory-compliance-packs", _upsert_pack_body(pack_id, enabled, config), project_id
        )

    def remove_project_pack(self, pack_id: str, *, project_id: Optional[str] = None) -> None:
        """Remove the per-project enablement row for a pack. The project then
        falls back to the platform default set — use
        :meth:`upsert_project_pack` with ``enabled=False`` to explicitly disable
        instead of revert."""
        self._t.delete(f"/memory-compliance-packs/{quote(pack_id, safe='')}", project_id)


class AsyncComplianceResource:
    """Asynchronous mirror of :class:`ComplianceResource`."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    async def export_subject(
        self, subject: ComplianceSubject, *, project_id: Optional[str] = None
    ) -> ExportSubjectResponse:
        """Async mirror of :meth:`ComplianceResource.export_subject`."""
        return await self._t.post("/memory-compliance/export", {"subject": subject}, project_id)

    async def hard_delete_subject(
        self,
        subject: ComplianceSubject,
        *,
        reason: str,
        dry_run: Optional[bool] = None,
        project_id: Optional[str] = None,
    ) -> HardDeleteSubjectResponse:
        """Async mirror of :meth:`ComplianceResource.hard_delete_subject`."""
        return await self._t.post(
            "/memory-compliance/hard-delete",
            _hard_delete_body(subject, reason, dry_run),
            project_id,
        )

    async def list_audit_events(
        self,
        *,
        subject: Optional[ComplianceSubject] = None,
        actor: Optional[str] = None,
        event_types: Optional[List[str]] = None,
        since: Optional[str] = None,
        limit: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> List[AuditEvent]:
        """Async mirror of :meth:`ComplianceResource.list_audit_events`."""
        return await self._t.get(
            "/memory-compliance/audit",
            _audit_query(subject, actor, event_types, since, limit),
            project_id,
        )

    async def list_packs(self, *, project_id: Optional[str] = None) -> List[CompliancePack]:
        """Async mirror of :meth:`ComplianceResource.list_packs`."""
        return await self._t.get("/memory-compliance/packs", None, project_id)

    async def list_project_packs(
        self, *, project_id: Optional[str] = None
    ) -> List[ProjectPackEnablement]:
        """Async mirror of :meth:`ComplianceResource.list_project_packs`."""
        return await self._t.get("/memory-compliance-packs", None, project_id)

    async def upsert_project_pack(
        self,
        *,
        pack_id: str,
        enabled: bool,
        config: Optional[dict] = None,
        project_id: Optional[str] = None,
    ) -> ProjectPackEnablement:
        """Async mirror of :meth:`ComplianceResource.upsert_project_pack`."""
        return await self._t.post(
            "/memory-compliance-packs", _upsert_pack_body(pack_id, enabled, config), project_id
        )

    async def remove_project_pack(
        self, pack_id: str, *, project_id: Optional[str] = None
    ) -> None:
        """Async mirror of :meth:`ComplianceResource.remove_project_pack`."""
        await self._t.delete(f"/memory-compliance-packs/{quote(pack_id, safe='')}", project_id)


__all__ = ["ComplianceResource", "AsyncComplianceResource"]
