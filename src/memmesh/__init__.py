"""MemMesh — memory + prediction for AI agents.

>>> from memmesh import MemMesh, subject
>>> mm = MemMesh(api_key="sk-...", project_id="proj_...")
>>> mm.observe("Ordered a large pizza, no tip.", subject=subject("contact", "sarah"))
>>> mm.predict(subject("contact", "sarah"), horizon_days=30)
"""

from ._version import __version__
from .client import AsyncMemMesh, MemMesh
from .errors import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    AuthorizationError,
    MemMeshError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from .types import (
    FeedbackRating,
    MemoryProvenanceTier,
    MemoryReviewReason,
    MemoryScope,
    MemoryType,
    Subject,
    render_procedure_content,
    subject,
)

__all__ = [
    "__version__",
    "MemMesh",
    "AsyncMemMesh",
    "Subject",
    "subject",
    "MemoryType",
    "MemoryScope",
    "MemoryReviewReason",
    "MemoryProvenanceTier",
    "render_procedure_content",
    "FeedbackRating",
    "MemMeshError",
    "AuthenticationError",
    "AuthorizationError",
    "NotFoundError",
    "ValidationError",
    "RateLimitError",
    "ServerError",
    "APITimeoutError",
    "APIConnectionError",
]
