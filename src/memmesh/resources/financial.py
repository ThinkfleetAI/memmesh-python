"""Financial resource — technical indicators, portfolio risk, and a
self-calibrating directional prediction loop.

Financial data is just memory data: you ingest price bars, fundamentals,
holdings, and news as memory items, and the engine derives indicators (SMA/EMA,
RSI, MACD, Bollinger, volatility, drawdown, Sharpe, beta), portfolio risk (VaR,
weighted beta, HHI concentration, allocation), and buy/sell/hold calls whose
REPORTED confidence is the strategy's structural agreement times its *realized*
hit-rate. As calls come due they are scored against actual prices
(:meth:`reconcile`), and that feedback recalibrates future confidence.

You decide where the data originates — a market-data vendor, a brokerage feed, a
news scraper. The SDK only gives you the typed way in and out.

Requires the ``@thinkfleet/pack-financial`` pack enabled on the project; the
read methods return FAILED_PRECONDITION otherwise. Ingestion works regardless
(it's plain memory). Everything here is informational only — NOT investment
advice. Market data (prices/fundamentals/news) is pooled across the project;
holdings are private to their subject. Mirrors ``thinkfleet-memory-sdk``'s
``resources/financial.ts``.
"""

from __future__ import annotations

import asyncio
from typing import Any, List, Optional

from ..types import (
    FinancialCalibrationReport,
    FinancialProfile,
    FundamentalInput,
    HoldingInput,
    MemoryItem,
    MemoryScope,
    MemoryType,
    NewsInput,
    PredictFinancialResult,
    PriceInput,
    ReconcileFinancialResult,
    Subject,
    enum_value,
)


def _price_body(price: PriceInput) -> dict:
    as_of = price.get("asOf")
    content = f"{price['ticker']} close {price['close']}" + (f" @ {as_of}" if as_of else "")
    return {
        "content": content,
        "type": enum_value(MemoryType.FACT),
        "scope": enum_value(MemoryScope.PROJECT),
        "category": "financial",
        "source": "sdk:financial",
        "metadata": {"price": price},
    }


def _fundamentals_body(fundamental: FundamentalInput) -> dict:
    return {
        "content": f"Fundamentals {fundamental['ticker']}",
        "type": enum_value(MemoryType.FACT),
        "scope": enum_value(MemoryScope.PROJECT),
        "category": "financial",
        "source": "sdk:financial",
        "metadata": {"fundamental": fundamental},
    }


def _holding_body(subject: Subject, holding: HoldingInput) -> dict:
    return {
        "content": f"Holding {holding['shares']} {holding['ticker']}",
        "type": enum_value(MemoryType.FACT),
        "scope": enum_value(MemoryScope.PROJECT),
        "category": "financial",
        "source": "sdk:financial",
        "metadata": {"subject": subject, "holding": holding},
    }


def _news_body(news: NewsInput) -> dict:
    tickers = news.get("tickers")
    label = news.get("ticker") or (",".join(tickers) if tickers else None) or "news"
    return {
        "content": f"News [{label}]: {news['headline']}",
        "type": enum_value(MemoryType.FACT),
        "scope": enum_value(MemoryScope.PROJECT),
        "category": "financial",
        "source": "sdk:financial",
        "metadata": {"newsEvent": news},
    }


def _predict_body(subject: Subject, horizon_days: Optional[int], persist: Optional[bool]) -> dict:
    body: dict = {"subject": subject}
    if horizon_days is not None:
        body["horizonDays"] = horizon_days
    if persist is not None:
        body["persist"] = persist
    return body


def _calibration_body(bucket_count: Optional[int], strategy: Optional[str]) -> dict:
    body: dict = {}
    if bucket_count is not None:
        body["bucketCount"] = bucket_count
    if strategy is not None:
        body["strategy"] = strategy
    return body


class FinancialResource:
    """Synchronous financial-vertical operations."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    # ── Input — ingest market data + positions (stored as memory items) ──

    def ingest_price(self, price: PriceInput, *, project_id: Optional[str] = None) -> MemoryItem:
        """Ingest a single price bar. Market data — not subject-attributed."""
        return self._t.post("/admin/memory", _price_body(price), project_id)

    def ingest_prices(
        self, prices: List[PriceInput], *, project_id: Optional[str] = None
    ) -> List[MemoryItem]:
        """Ingest many price bars (e.g. a backfill). For very large histories,
        batch in chunks yourself."""
        return [self.ingest_price(p, project_id=project_id) for p in prices]

    def ingest_fundamentals(
        self, fundamental: FundamentalInput, *, project_id: Optional[str] = None
    ) -> MemoryItem:
        """Ingest/refresh a ticker's fundamentals. Latest values win."""
        return self._t.post("/admin/memory", _fundamentals_body(fundamental), project_id)

    def ingest_holding(
        self, subject: Subject, holding: HoldingInput, *, project_id: Optional[str] = None
    ) -> MemoryItem:
        """Record a portfolio position. Subject-private — attributed to the owner
        (use a ``{'kind': 'portfolio', 'externalId': ...}`` subject). Restated,
        not summed: re-recording a ticker replaces the prior position."""
        return self._t.post("/admin/memory", _holding_body(subject, holding), project_id)

    def ingest_news(self, news: NewsInput, *, project_id: Optional[str] = None) -> MemoryItem:
        """Ingest a news event. Market data — tag one or many tickers."""
        return self._t.post("/admin/memory", _news_body(news), project_id)

    # ── Read — indicators, risk, calibrated predictions ──

    def get_profile(self, subject: Subject, *, project_id: Optional[str] = None) -> FinancialProfile:
        """Technical indicators + (for a portfolio subject) a risk rollup, derived
        from ingested market data and holdings. Read-only and forecast-free.

        ``subject['kind'] == 'ticker'`` → single-name analysis (externalId is the
        ticker). Any other kind → portfolio mode over the subject's holdings."""
        return self._t.post("/lattice/financial/profile", {"subject": subject}, project_id)

    def predict(
        self,
        subject: Subject,
        *,
        horizon_days: Optional[int] = None,
        persist: Optional[bool] = None,
        project_id: Optional[str] = None,
    ) -> PredictFinancialResult:
        """Generate directional buy/sell/hold calls. Reported confidence =
        structural agreement × the strategy's realized reliability. By default
        each call is persisted so it can be scored at horizon by
        :meth:`reconcile`."""
        return self._t.post(
            "/lattice/financial/predict", _predict_body(subject, horizon_days, persist), project_id
        )

    def reconcile(self, *, project_id: Optional[str] = None) -> ReconcileFinancialResult:
        """Run the feedback loop: score every persisted prediction whose horizon
        has elapsed against the realized close, and mark it resolved. This is what
        makes the engine learn. Idempotent; safe to run on a schedule."""
        return self._t.post("/lattice/financial/reconcile", {}, project_id)

    def get_calibration(
        self,
        *,
        bucket_count: Optional[int] = None,
        strategy: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> FinancialCalibrationReport:
        """The honesty proof: resolved predictions bucketed by the confidence we
        reported, with the realized hit-rate per band."""
        return self._t.post(
            "/lattice/financial/calibration", _calibration_body(bucket_count, strategy), project_id
        )


class AsyncFinancialResource:
    """Asynchronous mirror of :class:`FinancialResource`."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    async def ingest_price(
        self, price: PriceInput, *, project_id: Optional[str] = None
    ) -> MemoryItem:
        """Async mirror of :meth:`FinancialResource.ingest_price`."""
        return await self._t.post("/admin/memory", _price_body(price), project_id)

    async def ingest_prices(
        self, prices: List[PriceInput], *, project_id: Optional[str] = None
    ) -> List[MemoryItem]:
        """Async mirror of :meth:`FinancialResource.ingest_prices`. Issued
        concurrently; resolves once all are stored."""
        return list(
            await asyncio.gather(*(self.ingest_price(p, project_id=project_id) for p in prices))
        )

    async def ingest_fundamentals(
        self, fundamental: FundamentalInput, *, project_id: Optional[str] = None
    ) -> MemoryItem:
        """Async mirror of :meth:`FinancialResource.ingest_fundamentals`."""
        return await self._t.post("/admin/memory", _fundamentals_body(fundamental), project_id)

    async def ingest_holding(
        self, subject: Subject, holding: HoldingInput, *, project_id: Optional[str] = None
    ) -> MemoryItem:
        """Async mirror of :meth:`FinancialResource.ingest_holding`."""
        return await self._t.post("/admin/memory", _holding_body(subject, holding), project_id)

    async def ingest_news(self, news: NewsInput, *, project_id: Optional[str] = None) -> MemoryItem:
        """Async mirror of :meth:`FinancialResource.ingest_news`."""
        return await self._t.post("/admin/memory", _news_body(news), project_id)

    async def get_profile(
        self, subject: Subject, *, project_id: Optional[str] = None
    ) -> FinancialProfile:
        """Async mirror of :meth:`FinancialResource.get_profile`."""
        return await self._t.post("/lattice/financial/profile", {"subject": subject}, project_id)

    async def predict(
        self,
        subject: Subject,
        *,
        horizon_days: Optional[int] = None,
        persist: Optional[bool] = None,
        project_id: Optional[str] = None,
    ) -> PredictFinancialResult:
        """Async mirror of :meth:`FinancialResource.predict`."""
        return await self._t.post(
            "/lattice/financial/predict", _predict_body(subject, horizon_days, persist), project_id
        )

    async def reconcile(self, *, project_id: Optional[str] = None) -> ReconcileFinancialResult:
        """Async mirror of :meth:`FinancialResource.reconcile`."""
        return await self._t.post("/lattice/financial/reconcile", {}, project_id)

    async def get_calibration(
        self,
        *,
        bucket_count: Optional[int] = None,
        strategy: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> FinancialCalibrationReport:
        """Async mirror of :meth:`FinancialResource.get_calibration`."""
        return await self._t.post(
            "/lattice/financial/calibration", _calibration_body(bucket_count, strategy), project_id
        )


__all__ = ["FinancialResource", "AsyncFinancialResource"]
