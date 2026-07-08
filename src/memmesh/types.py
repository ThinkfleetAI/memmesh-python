"""Shared types and small helpers for the MemMesh SDK.

Responses come back as plain ``dict`` objects (typed as ``MemoryItem`` etc.)
so you always have access to the full server payload. Enums + the
``subject`` helper exist to keep call sites readable and typo-proof.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, TypedDict


class MemoryType(str, Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    EVENT = "event"
    INSIGHT = "insight"
    OBSERVATION = "observation"
    RULE = "rule"
    CORRECTION = "correction"
    SUMMARY = "summary"
    BEHAVIOR_PATTERN = "behavior_pattern"
    CONSENT = "consent"


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
Prediction = Dict[str, Any]
PredictResult = Dict[str, Any]
CalibrationReport = Dict[str, Any]
SubjectProfile = Dict[str, Any]


def enum_value(x: Any) -> Any:
    """Return ``x.value`` for enums, else ``x`` — lets callers pass either
    the enum or a raw string."""
    return x.value if isinstance(x, Enum) else x
