"""Learning resource — the closed-loop **decision → action → outcome** primitive.

Where :meth:`LatticeResource.predict` answers "what will happen?", the learning
loop answers **"did acting on it work?"**. Record a decision (with links to the
patterns/predictions that informed it), record its realized outcome, and every
informing pattern's calibrated confidence moves toward what actually happened.
:meth:`get_effectiveness` rolls "what worked" up per action_type / decision_type
/ policy / pattern_kind.

Domain-agnostic by design — subject/decision/action/outcome/reward only. Mirrors
``thinkfleet-memory-sdk``'s ``resources/learning.ts`` one-for-one.
"""

from __future__ import annotations

from typing import Any, List, Optional

from ..types import (
    EffectivenessGroupBy,
    EffectivenessRow,
    OutcomeRecord,
    ProvenanceRef,
    RecordDecisionResult,
    RecordOutcomeResult,
    Subject,
)


def _decision_body(
    subject: Subject,
    actor: Optional[str],
    decision_type: Optional[str],
    policy: Optional[str],
    informed_by: Optional[List[ProvenanceRef]],
    action_type: Optional[str],
    params: Optional[dict],
    status: Optional[str],
    occurred_at: Optional[str],
    metadata: Optional[dict],
    idempotency_key: Optional[str],
) -> dict:
    raw = {
        "subject": subject,
        "actor": actor,
        "decisionType": decision_type,
        "policy": policy,
        "informedBy": informed_by,
        "actionType": action_type,
        "params": params,
        "status": status,
        "occurredAt": occurred_at,
        "metadata": metadata,
        "idempotencyKey": idempotency_key,
    }
    return {k: v for k, v in raw.items() if v is not None}


def _outcome_body(
    decision_id: str,
    result: str,
    subject: Optional[Subject],
    outcome_type: Optional[str],
    reward: Optional[float],
    realized_at: Optional[str],
    attribution_window_secs: Optional[int],
    metadata: Optional[dict],
    idempotency_key: Optional[str],
) -> dict:
    raw = {
        "decisionId": decision_id,
        "result": result,
        "subject": subject,
        "outcomeType": outcome_type,
        "reward": reward,
        "realizedAt": realized_at,
        "attributionWindowSecs": attribution_window_secs,
        "metadata": metadata,
        "idempotencyKey": idempotency_key,
    }
    return {k: v for k, v in raw.items() if v is not None}


def _outcomes_params(
    subject: Optional[Subject],
    decision_type: Optional[str],
    action_type: Optional[str],
    limit: Optional[int],
) -> dict:
    raw = {
        "subjectKind": subject["kind"] if subject is not None else None,
        "subjectExternalId": subject["externalId"] if subject is not None else None,
        "decisionType": decision_type,
        "actionType": action_type,
        "limit": limit,
    }
    return {k: v for k, v in raw.items() if v is not None}


class LearningResource:
    """Synchronous decision / outcome / effectiveness operations."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def record_decision(
        self,
        subject: Subject,
        *,
        actor: Optional[str] = None,
        decision_type: Optional[str] = None,
        policy: Optional[str] = None,
        informed_by: Optional[List[ProvenanceRef]] = None,
        action_type: Optional[str] = None,
        params: Optional[dict] = None,
        status: Optional[str] = None,
        occurred_at: Optional[str] = None,
        metadata: Optional[dict] = None,
        idempotency_key: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> RecordDecisionResult:
        """Record a decision and its causal provenance. ``informed_by`` links the
        patterns/predictions/observations that drove it (credit assignment). Pass
        an ``idempotency_key`` to make the write replay-safe — a repeated key
        returns the existing decision, no duplicate."""
        body = _decision_body(
            subject, actor, decision_type, policy, informed_by, action_type,
            params, status, occurred_at, metadata, idempotency_key,
        )
        return self._t.post("/lattice/decisions", body, project_id)

    def record_outcome(
        self,
        decision_id: str,
        *,
        result: str,
        subject: Optional[Subject] = None,
        outcome_type: Optional[str] = None,
        reward: Optional[float] = None,
        realized_at: Optional[str] = None,
        attribution_window_secs: Optional[int] = None,
        metadata: Optional[dict] = None,
        idempotency_key: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> RecordOutcomeResult:
        """Record the realized outcome of a decision. Folds the result into the
        online calibrated confidence of every pattern the decision was
        ``informed_by``, and returns the before/after for each in ``updates``.
        ``result`` is ``"success"`` / ``"failure"`` / ``"partial"``."""
        body = _outcome_body(
            decision_id, result, subject, outcome_type, reward, realized_at,
            attribution_window_secs, metadata, idempotency_key,
        )
        return self._t.post("/lattice/outcomes", body, project_id)

    def get_outcomes(
        self,
        *,
        subject: Optional[Subject] = None,
        decision_type: Optional[str] = None,
        action_type: Optional[str] = None,
        limit: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> List[OutcomeRecord]:
        """List recorded outcomes for a subject (or the whole scope), newest
        first. Omit ``subject`` for a scope-wide list. ``limit`` defaults to 100
        server-side, clamped [1, 1000]."""
        params = _outcomes_params(subject, decision_type, action_type, limit)
        r = self._t.get("/lattice/outcomes", params, project_id)
        return r.get("outcomes", []) if isinstance(r, dict) else r

    def get_effectiveness(
        self,
        *,
        group_by: Optional[EffectivenessGroupBy] = None,
        min_support: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> List[EffectivenessRow]:
        """"What worked" roll-up — success rate, average reward, and posterior
        confidence per group. ``group_by`` defaults to ``"action_type"``
        server-side; pass ``min_support`` to return only groups with at least
        that many outcomes. Per-scope only."""
        params = {k: v for k, v in {"groupBy": group_by, "minSupport": min_support}.items() if v is not None}
        r = self._t.get("/lattice/effectiveness", params, project_id)
        return r.get("rows", []) if isinstance(r, dict) else r


class AsyncLearningResource:
    """Asynchronous mirror of :class:`LearningResource`."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    async def record_decision(
        self,
        subject: Subject,
        *,
        actor: Optional[str] = None,
        decision_type: Optional[str] = None,
        policy: Optional[str] = None,
        informed_by: Optional[List[ProvenanceRef]] = None,
        action_type: Optional[str] = None,
        params: Optional[dict] = None,
        status: Optional[str] = None,
        occurred_at: Optional[str] = None,
        metadata: Optional[dict] = None,
        idempotency_key: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> RecordDecisionResult:
        body = _decision_body(
            subject, actor, decision_type, policy, informed_by, action_type,
            params, status, occurred_at, metadata, idempotency_key,
        )
        return await self._t.post("/lattice/decisions", body, project_id)

    async def record_outcome(
        self,
        decision_id: str,
        *,
        result: str,
        subject: Optional[Subject] = None,
        outcome_type: Optional[str] = None,
        reward: Optional[float] = None,
        realized_at: Optional[str] = None,
        attribution_window_secs: Optional[int] = None,
        metadata: Optional[dict] = None,
        idempotency_key: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> RecordOutcomeResult:
        body = _outcome_body(
            decision_id, result, subject, outcome_type, reward, realized_at,
            attribution_window_secs, metadata, idempotency_key,
        )
        return await self._t.post("/lattice/outcomes", body, project_id)

    async def get_outcomes(
        self,
        *,
        subject: Optional[Subject] = None,
        decision_type: Optional[str] = None,
        action_type: Optional[str] = None,
        limit: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> List[OutcomeRecord]:
        params = _outcomes_params(subject, decision_type, action_type, limit)
        r = await self._t.get("/lattice/outcomes", params, project_id)
        return r.get("outcomes", []) if isinstance(r, dict) else r

    async def get_effectiveness(
        self,
        *,
        group_by: Optional[EffectivenessGroupBy] = None,
        min_support: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> List[EffectivenessRow]:
        params = {k: v for k, v in {"groupBy": group_by, "minSupport": min_support}.items() if v is not None}
        r = await self._t.get("/lattice/effectiveness", params, project_id)
        return r.get("rows", []) if isinstance(r, dict) else r
