"""Pagination helpers — sync and async iterators that transparently walk a
paginated endpoint so resources can expose ``list_all(...)`` without hand-rolling
the loop.

Two page shapes are supported, mirroring the TS SDK:

* **offset** (the TS ``listAll`` walk) — the endpoint returns a bare ``list`` and
  is paged by bumping ``offset``. A page shorter than ``page_size`` ends the walk.
  Use :class:`SyncOffsetPaginator` / :class:`AsyncOffsetPaginator`.
* **cursor** (the TS ``SeekPage<T>`` walk) — the endpoint returns
  ``{"data": [...], "next": <cursor|None>, ...}``. The walk follows ``next`` until
  it is falsy. Use :class:`SyncCursorPaginator` / :class:`AsyncCursorPaginator`.

Every paginator is itself iterable (``for item in ...`` / ``async for item in
...``), yields items one at a time so a large corpus never has to fit in memory,
and exposes :meth:`pages` to iterate whole pages instead. Resources build one by
passing a small page-fetch closure; see :func:`paginate` / :func:`paginate_cursor`
and their async twins.
"""

from __future__ import annotations

from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Generic,
    Iterator,
    List,
    Optional,
    TypeVar,
    Union,
)

from .types import SeekPage

T = TypeVar("T")

#: Server-side cap on ``limit`` for list endpoints. Mirrors the TS
#: ``MAX_PAGE_SIZE`` — the default page size for a full walk.
MAX_PAGE_SIZE = 500


# ── offset paging (TS `listAll`) ────────────────────────────────────────────


class SyncOffsetPaginator(Generic[T]):
    """Walk an offset-paged list endpoint. ``fetch_page(limit, offset)`` returns
    one page as a ``list``."""

    def __init__(
        self,
        fetch_page: Callable[[int, int], List[T]],
        *,
        page_size: int = MAX_PAGE_SIZE,
    ) -> None:
        self._fetch_page = fetch_page
        self._page_size = min(page_size, MAX_PAGE_SIZE)

    def pages(self) -> Iterator[List[T]]:
        offset = 0
        while True:
            page = self._fetch_page(self._page_size, offset)
            yield page
            if len(page) < self._page_size:
                return
            offset += len(page)

    def __iter__(self) -> Iterator[T]:
        for page in self.pages():
            yield from page


class AsyncOffsetPaginator(Generic[T]):
    """Async mirror of :class:`SyncOffsetPaginator`. ``fetch_page`` is awaited."""

    def __init__(
        self,
        fetch_page: Callable[[int, int], Awaitable[List[T]]],
        *,
        page_size: int = MAX_PAGE_SIZE,
    ) -> None:
        self._fetch_page = fetch_page
        self._page_size = min(page_size, MAX_PAGE_SIZE)

    async def pages(self) -> AsyncIterator[List[T]]:
        offset = 0
        while True:
            page = await self._fetch_page(self._page_size, offset)
            yield page
            if len(page) < self._page_size:
                return
            offset += len(page)

    async def __aiter__(self) -> AsyncIterator[T]:
        async for page in self.pages():
            for item in page:
                yield item


# ── cursor paging (TS `SeekPage<T>`) ────────────────────────────────────────


def _page_data(page: Union[SeekPage, dict]) -> List[Any]:
    return list(page.get("data") or [])


def _page_next(page: Union[SeekPage, dict]) -> Optional[str]:
    return page.get("next")


class SyncCursorPaginator(Generic[T]):
    """Walk a cursor-paged (:class:`~memmesh.types.SeekPage`) endpoint.
    ``fetch_page(cursor)`` returns one ``SeekPage`` dict; the first call gets
    ``None``."""

    def __init__(self, fetch_page: Callable[[Optional[str]], Union[SeekPage, dict]]) -> None:
        self._fetch_page = fetch_page

    def pages(self) -> Iterator[SeekPage]:
        cursor: Optional[str] = None
        while True:
            page = self._fetch_page(cursor)
            yield page  # type: ignore[misc]
            cursor = _page_next(page)
            if not cursor:
                return

    def __iter__(self) -> Iterator[T]:
        for page in self.pages():
            yield from _page_data(page)


class AsyncCursorPaginator(Generic[T]):
    """Async mirror of :class:`SyncCursorPaginator`. ``fetch_page`` is awaited."""

    def __init__(
        self,
        fetch_page: Callable[[Optional[str]], Awaitable[Union[SeekPage, dict]]],
    ) -> None:
        self._fetch_page = fetch_page

    async def pages(self) -> AsyncIterator[SeekPage]:
        cursor: Optional[str] = None
        while True:
            page = await self._fetch_page(cursor)
            yield page  # type: ignore[misc]
            cursor = _page_next(page)
            if not cursor:
                return

    async def __aiter__(self) -> AsyncIterator[T]:
        async for page in self.pages():
            for item in _page_data(page):
                yield item


# ── thin factory helpers resources call ─────────────────────────────────────


def paginate(
    fetch_page: Callable[[int, int], List[T]],
    *,
    page_size: int = MAX_PAGE_SIZE,
) -> SyncOffsetPaginator[T]:
    """Build a sync offset paginator. See :class:`SyncOffsetPaginator`."""
    return SyncOffsetPaginator(fetch_page, page_size=page_size)


def apaginate(
    fetch_page: Callable[[int, int], Awaitable[List[T]]],
    *,
    page_size: int = MAX_PAGE_SIZE,
) -> AsyncOffsetPaginator[T]:
    """Build an async offset paginator. See :class:`AsyncOffsetPaginator`."""
    return AsyncOffsetPaginator(fetch_page, page_size=page_size)


def paginate_cursor(
    fetch_page: Callable[[Optional[str]], Union[SeekPage, dict]],
) -> SyncCursorPaginator[T]:
    """Build a sync cursor paginator. See :class:`SyncCursorPaginator`."""
    return SyncCursorPaginator(fetch_page)


def apaginate_cursor(
    fetch_page: Callable[[Optional[str]], Awaitable[Union[SeekPage, dict]]],
) -> AsyncCursorPaginator[T]:
    """Build an async cursor paginator. See :class:`AsyncCursorPaginator`."""
    return AsyncCursorPaginator(fetch_page)
