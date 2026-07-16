"""Shared types and small helpers for the MemMesh SDK.

Responses come back as plain ``dict`` objects (typed as ``MemoryItem`` etc.)
so you always have access to the full server payload. Enums + the
``subject`` helper exist to keep call sites readable and typo-proof.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict


class MemoryType(str, Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    EVENT = "event"
    INSIGHT = "insight"
    OBSERVATION = "observation"
    RULE = "rule"
    CORRECTION = "correction"
    SUMMARY = "summary"
    #: A reusable procedure — how a job is done here (goal + steps + failure
    #: modes). Injected as a how-to exemplar, not a fact. Author with
    #: ``memory.create_procedure(...)``.
    PROCEDURE = "procedure"
    BEHAVIOR_PATTERN = "behavior_pattern"
    CONSENT = "consent"


class MemoryReviewReason(str, Enum):
    """Why a memory is in the adjudication queue (highest-priority reason wins)."""

    PENDING = "pending"
    FLAGGED = "flagged"
    LOW_CONFIDENCE = "low_confidence"
    STALE = "stale"


class MemoryProvenanceTier(str, Enum):
    """Origin tier used to resolve conflicts. Default order strongest→weakest."""

    HUMAN_VERIFIED = "human_verified"
    LOCAL = "local"
    LICENSED_BRAIN = "licensed_brain"
    BASE = "base"


class MemoryScope(str, Enum):
    PLATFORM = "platform"
    PROJECT = "project"
    LOCATION = "location"
    AGENT = "agent"
    USER = "user"
    SESSION = "session"


class FeedbackRating(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class Subject(TypedDict):
    """The entity a memory or prediction is about.

    ``kind`` is free-form (``"contact"``, ``"user"``, ``"patient"``,
    ``"workspace"``, ...); ``externalId`` is your stable id for it.
    """

    kind: str
    externalId: str


def subject(kind: str, external_id: str) -> Subject:
    """Build a :class:`Subject` with the API's camelCase shape.

    >>> subject("contact", "sarah-pizza")
    {'kind': 'contact', 'externalId': 'sarah-pizza'}
    """
    return {"kind": kind, "externalId": external_id}


# Server payloads are returned verbatim as dicts.
MemoryItem = Dict[str, Any]
SearchResult = Dict[str, Any]
IngestMediaResult = Dict[str, Any]
Prediction = Dict[str, Any]
PredictResult = Dict[str, Any]
CalibrationReport = Dict[str, Any]
SubjectProfile = Dict[str, Any]


def enum_value(x: Any) -> Any:
    """Return ``x.value`` for enums, else ``x`` — lets callers pass either
    the enum or a raw string."""
    return x.value if isinstance(x, Enum) else x


def render_procedure_content(
    goal: str,
    steps: List[Dict[str, str]],
    *,
    when_to_use: Optional[str] = None,
    failure_modes: Optional[List[str]] = None,
) -> str:
    """Render a procedure into the injectable ``content`` string — identical to
    the engine-side renderer, so client-authored content matches the server.

    ``steps`` is a list of ``{"text": ..., "pitfall"?: ...}`` dicts.
    """
    lines = [f"Goal: {goal.strip()}"]
    if when_to_use and when_to_use.strip():
        lines.append(f"When: {when_to_use.strip()}")
    lines.append("Steps:")
    for i, step in enumerate(steps, start=1):
        pitfall = step.get("pitfall")
        suffix = f" (watch out: {pitfall.strip()})" if pitfall and pitfall.strip() else ""
        lines.append(f"{i}. {step['text'].strip()}{suffix}")
    failures = [f.strip() for f in (failure_modes or []) if f.strip()]
    if failures:
        lines.append("Avoid:")
        lines.extend(f"- {f}" for f in failures)
    return "\n".join(lines)
