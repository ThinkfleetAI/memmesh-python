"""Top-level clients: :class:`MemMesh` (sync) and :class:`AsyncMemMesh`."""

from __future__ import annotations

from typing import Any, Optional

from ._http import AsyncTransport, Transport
from .resources.lattice import AsyncLatticeResource, LatticeResource
from .resources.context import AsyncContextResource, ContextResource
from .resources.memory import AsyncMemoryResource, MemoryResource

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
    ) -> None:
        self._t = Transport(api_key, project_id, base_url, timeout, max_retries)
        self.memory = MemoryResource(self._t)
        self.lattice = LatticeResource(self._t)
        self.context = ContextResource(self._t)

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
    ) -> None:
        self._t = AsyncTransport(api_key, project_id, base_url, timeout, max_retries)
        self.memory = AsyncMemoryResource(self._t)
        self.lattice = AsyncLatticeResource(self._t)
        self.context = AsyncContextResource(self._t)

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
