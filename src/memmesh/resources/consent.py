"""Consent resource — subject-level consent / opt-out.

Records consent decisions as memory items of ``type='consent'`` so the audit log
captures every change. The Rust mining engine honors opt-outs at the start of
every mine pass — opted-out subjects are skipped, and their behavior patterns
aren't generated.

Foundations of the EU AI Act / GDPR Art. 22 compliance story:

* **subject-level** — per-person (or per-team / per-workspace) opt-out
* **audit-traceable** — every opt-out is a confirmed memory item
* **reversible** — opt-in re-enables mining (without restoring prior patterns —
  those need to be re-mined to honor the gap)

Note: v1 stores consent as memory items (this SDK talks to the memory CRUD
surface, not a dedicated endpoint). A later phase introduces a dedicated
``subject_consent`` table for sub-ms lookups; the SDK contract here doesn't
change when that lands. Mirrors ``thinkfleet-memory-sdk``'s
``resources/consent.ts``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional

from ..types import (
    ConsentStatus,
    ConsentSubject,
    MemoryItem,
    MemoryScope,
    MemoryType,
    enum_value,
)

_CONSENT_TYPE = enum_value(MemoryType.CONSENT)

#: The engine caps ``limit`` at 500 (querystring/limit must be <= 500); 1000
#: hard-fails every consent lookup.
_CONSENT_SCAN_LIMIT = 500


def _now_iso() -> str:
    """Current time as a UTC ISO-8601 string with a ``Z`` suffix — matches the
    TS ``new Date().toISOString()`` shape stored on the memory item."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _subject_matches(item: MemoryItem, subject: ConsentSubject) -> bool:
    md = item.get("metadata") or {}
    s = md.get("subject")
    if not isinstance(s, dict):
        return False
    return s.get("kind") == subject["kind"] and s.get("externalId") == subject["externalId"]


def _created_key(item: MemoryItem) -> str:
    # Newest-first; a missing/blank ``created`` sorts last.
    return item.get("created") or ""


def _opt_out_metadata(subject: ConsentSubject, now: str, reason: Optional[str]) -> dict:
    return {
        "subject": subject,
        "optedOut": True,
        "optedOutAt": now,
        "reason": reason if reason is not None else None,
        "recordKind": "consent",
    }


def _opt_in_metadata(subject: ConsentSubject) -> dict:
    return {
        "subject": subject,
        "optedOut": False,
        "optedOutAt": None,
        "reason": None,
        "recordKind": "consent",
    }


def _status_from_item(subject: ConsentSubject, item: Optional[MemoryItem]) -> ConsentStatus:
    if item is None:
        return {"subject": subject, "optedOut": False, "optedOutAt": None, "reason": None, "memoryId": None}
    md = item.get("metadata") or {}
    return {
        "subject": subject,
        "optedOut": bool(md.get("optedOut")),
        "optedOutAt": md.get("optedOutAt"),
        "reason": md.get("reason"),
        "memoryId": item.get("id"),
    }


class ConsentResource:
    """Synchronous subject-level consent operations. Implemented client-side over
    the memory CRUD surface — consent decisions are written and read as
    ``type='consent'`` memory items."""

    def __init__(self, memory: Any) -> None:
        self._memory = memory

    def opt_out(
        self,
        subject: ConsentSubject,
        *,
        reason: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> ConsentStatus:
        """Mark a subject as opted-out. Mining and recall must honor this: the
        Rust engine skips opted-out subjects at mine time. ``reason`` is
        free-text for the audit log (a GDPR Art. 17 request id, etc.)."""
        # Supersede any prior consent record so the audit log shows the history
        # but only one row is "active".
        self._supersede_prior_consent(subject, project_id=project_id)
        now = _now_iso()
        memory = self._memory.create(
            f"[consent] {subject['kind']}:{subject['externalId']} opted out",
            type=MemoryType.CONSENT,
            scope=MemoryScope.PROJECT,
            importance=10,
            category="consent",
            metadata=_opt_out_metadata(subject, now, reason),
            project_id=project_id,
        )
        return {
            "subject": subject,
            "optedOut": True,
            "optedOutAt": now,
            "reason": reason if reason is not None else None,
            "memoryId": memory.get("id"),
        }

    def opt_in(
        self,
        subject: ConsentSubject,
        *,
        project_id: Optional[str] = None,
    ) -> ConsentStatus:
        """Restore consent for a subject. Mining resumes from the next pass.
        Prior patterns are NOT auto-restored — they must be re-mined so the gap
        during opt-out is honored."""
        self._supersede_prior_consent(subject, project_id=project_id)
        memory = self._memory.create(
            f"[consent] {subject['kind']}:{subject['externalId']} opted in",
            type=MemoryType.CONSENT,
            scope=MemoryScope.PROJECT,
            importance=10,
            category="consent",
            metadata=_opt_in_metadata(subject),
            project_id=project_id,
        )
        return {
            "subject": subject,
            "optedOut": False,
            "optedOutAt": None,
            "reason": None,
            "memoryId": memory.get("id"),
        }

    def get_status(
        self,
        subject: ConsentSubject,
        *,
        project_id: Optional[str] = None,
    ) -> ConsentStatus:
        """Read the current consent status for a subject. Returns
        ``optedOut=False`` (the default) if no consent record exists."""
        active = self._find_active_consent(subject, project_id=project_id)
        return _status_from_item(subject, active)

    # ── private helpers ─────────────────────────────────────────────

    def _find_active_consent(
        self, subject: ConsentSubject, *, project_id: Optional[str] = None
    ) -> Optional[MemoryItem]:
        all_items: List[MemoryItem] = self._memory.list(
            limit=_CONSENT_SCAN_LIMIT, project_id=project_id
        )
        matches = [
            m
            for m in all_items
            if m.get("type") == _CONSENT_TYPE and _subject_matches(m, subject)
        ]
        matches.sort(key=_created_key, reverse=True)
        return matches[0] if matches else None

    def _supersede_prior_consent(
        self, subject: ConsentSubject, *, project_id: Optional[str] = None
    ) -> None:
        prior = self._find_active_consent(subject, project_id=project_id)
        if prior is not None:
            # Hard-delete the prior row. The audit log keeps the historical
            # trail; we don't need the old row in the active set anymore.
            self._memory.delete(prior["id"], project_id=project_id)


class AsyncConsentResource:
    """Asynchronous mirror of :class:`ConsentResource`."""

    def __init__(self, memory: Any) -> None:
        self._memory = memory

    async def opt_out(
        self,
        subject: ConsentSubject,
        *,
        reason: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> ConsentStatus:
        """Async mirror of :meth:`ConsentResource.opt_out`."""
        await self._supersede_prior_consent(subject, project_id=project_id)
        now = _now_iso()
        memory = await self._memory.create(
            f"[consent] {subject['kind']}:{subject['externalId']} opted out",
            type=MemoryType.CONSENT,
            scope=MemoryScope.PROJECT,
            importance=10,
            category="consent",
            metadata=_opt_out_metadata(subject, now, reason),
            project_id=project_id,
        )
        return {
            "subject": subject,
            "optedOut": True,
            "optedOutAt": now,
            "reason": reason if reason is not None else None,
            "memoryId": memory.get("id"),
        }

    async def opt_in(
        self,
        subject: ConsentSubject,
        *,
        project_id: Optional[str] = None,
    ) -> ConsentStatus:
        """Async mirror of :meth:`ConsentResource.opt_in`."""
        await self._supersede_prior_consent(subject, project_id=project_id)
        memory = await self._memory.create(
            f"[consent] {subject['kind']}:{subject['externalId']} opted in",
            type=MemoryType.CONSENT,
            scope=MemoryScope.PROJECT,
            importance=10,
            category="consent",
            metadata=_opt_in_metadata(subject),
            project_id=project_id,
        )
        return {
            "subject": subject,
            "optedOut": False,
            "optedOutAt": None,
            "reason": None,
            "memoryId": memory.get("id"),
        }

    async def get_status(
        self,
        subject: ConsentSubject,
        *,
        project_id: Optional[str] = None,
    ) -> ConsentStatus:
        """Async mirror of :meth:`ConsentResource.get_status`."""
        active = await self._find_active_consent(subject, project_id=project_id)
        return _status_from_item(subject, active)

    # ── private helpers ─────────────────────────────────────────────

    async def _find_active_consent(
        self, subject: ConsentSubject, *, project_id: Optional[str] = None
    ) -> Optional[MemoryItem]:
        all_items: List[MemoryItem] = await self._memory.list(
            limit=_CONSENT_SCAN_LIMIT, project_id=project_id
        )
        matches = [
            m
            for m in all_items
            if m.get("type") == _CONSENT_TYPE and _subject_matches(m, subject)
        ]
        matches.sort(key=_created_key, reverse=True)
        return matches[0] if matches else None

    async def _supersede_prior_consent(
        self, subject: ConsentSubject, *, project_id: Optional[str] = None
    ) -> None:
        prior = await self._find_active_consent(subject, project_id=project_id)
        if prior is not None:
            await self._memory.delete(prior["id"], project_id=project_id)


__all__ = ["ConsentResource", "AsyncConsentResource"]
