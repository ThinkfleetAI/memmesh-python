"""Top-level clients: :class:`MemMesh` (sync) and :class:`AsyncMemMesh`."""

from __future__ import annotations

from typing import Any, List, Optional

import httpx

from ._http import (
    AsyncTransport,
    RequestInterceptor,
    ResponseInterceptor,
    Transport,
)
from .resources.alerts import AlertsResource, AsyncAlertsResource
from .resources.behaviors import AsyncBehaviorsResource, BehaviorsResource
from .resources.brains import AsyncBrainsResource, BrainsResource
from .resources.compliance import AsyncComplianceResource, ComplianceResource
from .resources.consent import AsyncConsentResource, ConsentResource
from .resources.events import AsyncEventsResource, EventsResource
from .resources.financial import AsyncFinancialResource, FinancialResource
from .resources.health import AsyncHealthResource, HealthResource
from .resources.lattice import AsyncLatticeResource, LatticeResource
from .resources.context import AsyncContextResource, ContextResource
from .resources.learning import AsyncLearningResource, LearningResource
from .resources.memory import AsyncMemoryResource, MemoryResource
from .resources.typed import AsyncTypedAttributesResource, TypedAttributesResource

# The live API today. Moves to https://api.memmesh.ai as the rebrand lands;
# override with ``base_url=...`` (or point at your self-hosted engine).
DEFAULT_BASE_URL = "https://app.memmesh.ai"


class MemMesh:
    """Synchronous MemMesh client.

    >>> from memmesh import MemMesh, subject
    >>> mm = MemMesh(api_key="sk-...", project_id="proj_...")
    >>> mm.observe("Moved to the annual plan, prefers email.",
    ...            subject=subject("contact", "user_42"))
    >>> mm.search("billing preferences", limit=5)
    >>> mm.predict(subject("contact", "user_42"), horizon_days=30)
    """

    def __init__(
        self,
        api_key: str,
        project_id: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 2,
        request_interceptors: Optional[List[RequestInterceptor]] = None,
        response_interceptors: Optional[List[ResponseInterceptor]] = None,
        http_client: Optional[httpx.Client] = None,
        transport: Optional[Transport] = None,
    ) -> None:
        self._t = transport or Transport(
            api_key,
            project_id,
            base_url,
            timeout,
            max_retries,
            request_interceptors=request_interceptors,
            response_interceptors=response_interceptors,
            http_client=http_client,
        )
        self.memory = MemoryResource(self._t)
        self.lattice = LatticeResource(self._t)
        self.context = ContextResource(self._t)
        self.learning = LearningResource(self._t)
        self.behaviors = BehaviorsResource(self._t)
        self.brains = BrainsResource(self._t)
        self.consent = ConsentResource(self.memory)
        self.alerts = AlertsResource(self._t)
        self.events = EventsResource(self._t)
        self.typed = TypedAttributesResource(self._t)
        self.health = HealthResource(self._t)
        self.financial = FinancialResource(self._t)
        self.compliance = ComplianceResource(self._t)

    # -- convenience shortcuts to the most-used calls --------------------
    def observe(self, *args: Any, **kwargs: Any) -> Any:
        return self.memory.observe(*args, **kwargs)

    def search(self, *args: Any, **kwargs: Any) -> Any:
        return self.memory.search(*args, **kwargs)

    def predict(self, *args: Any, **kwargs: Any) -> Any:
        return self.lattice.predict(*args, **kwargs)

    def calibration(self, *args: Any, **kwargs: Any) -> Any:
        return self.lattice.calibration(*args, **kwargs)

    def close(self) -> None:
        self._t.close()

    def __enter__(self) -> "MemMesh":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class AsyncMemMesh:
    """Asynchronous MemMesh client — mirrors :class:`MemMesh`.

    >>> async with AsyncMemMesh(api_key="sk-...", project_id="proj_...") as mm:
    ...     await mm.observe("...", subject=subject("contact", "user_42"))
    ...     preds = await mm.predict(subject("contact", "user_42"))
    """

    def __init__(
        self,
        api_key: str,
        project_id: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 2,
        request_interceptors: Optional[List[RequestInterceptor]] = None,
        response_interceptors: Optional[List[ResponseInterceptor]] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        transport: Optional[AsyncTransport] = None,
    ) -> None:
        self._t = transport or AsyncTransport(
            api_key,
            project_id,
            base_url,
            timeout,
            max_retries,
            request_interceptors=request_interceptors,
            response_interceptors=response_interceptors,
            http_client=http_client,
        )
        self.memory = AsyncMemoryResource(self._t)
        self.lattice = AsyncLatticeResource(self._t)
        self.context = AsyncContextResource(self._t)
        self.learning = AsyncLearningResource(self._t)
        self.behaviors = AsyncBehaviorsResource(self._t)
        self.brains = AsyncBrainsResource(self._t)
        self.consent = AsyncConsentResource(self.memory)
        self.alerts = AsyncAlertsResource(self._t)
        self.events = AsyncEventsResource(self._t)
        self.typed = AsyncTypedAttributesResource(self._t)
        self.health = AsyncHealthResource(self._t)
        self.financial = AsyncFinancialResource(self._t)
        self.compliance = AsyncComplianceResource(self._t)

    async def observe(self, *args: Any, **kwargs: Any) -> Any:
        return await self.memory.observe(*args, **kwargs)

    async def search(self, *args: Any, **kwargs: Any) -> Any:
        return await self.memory.search(*args, **kwargs)

    async def predict(self, *args: Any, **kwargs: Any) -> Any:
        return await self.lattice.predict(*args, **kwargs)

    async def calibration(self, *args: Any, **kwargs: Any) -> Any:
        return await self.lattice.calibration(*args, **kwargs)

    async def aclose(self) -> None:
        await self._t.aclose()

    async def __aenter__(self) -> "AsyncMemMesh":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()
