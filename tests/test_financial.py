"""Request-shaping tests for the financial vertical — ingest_price / _prices /
_fundamentals / _holding / _news (stored as /admin/memory facts) plus the reads
get_profile, predict, reconcile, get_calibration. No live server (respx mocks)."""

import json

import httpx
import respx

from memmesh import AsyncMemMesh, MemMesh, subject

BASE = "https://app.memmesh.ai"
PROJ = "proj_test"
PREFIX = f"{BASE}/api/v1/projects/{PROJ}"

TICKER = subject("ticker", "AAPL")
PORTFOLIO = subject("portfolio", "acct-123")


def client() -> MemMesh:
    return MemMesh(api_key="sk-test", project_id=PROJ, max_retries=0)


def _body(route) -> dict:
    return json.loads(route.calls.last.request.content)


def _bodies(route) -> list:
    return [json.loads(c.request.content) for c in route.calls]


# ── ingest_price ─────────────────────────────────────────────────────────────


@respx.mock
def test_ingest_price_posts_fact_with_as_of():
    route = respx.post(f"{PREFIX}/admin/memory").mock(
        return_value=httpx.Response(200, json={"id": "m1"})
    )
    price = {"ticker": "AAPL", "close": 190.5, "asOf": "2026-01-02"}
    with client() as mm:
        out = mm.financial.ingest_price(price)
    assert out["id"] == "m1"
    body = _body(route)
    assert body["content"] == "AAPL close 190.5 @ 2026-01-02"
    assert body["type"] == "fact"
    assert body["scope"] == "project"
    assert body["category"] == "financial"
    assert body["source"] == "sdk:financial"
    assert body["metadata"] == {"price": price}


@respx.mock
def test_ingest_price_omits_as_of_suffix_when_absent():
    route = respx.post(f"{PREFIX}/admin/memory").mock(
        return_value=httpx.Response(200, json={"id": "m2"})
    )
    with client() as mm:
        mm.financial.ingest_price({"ticker": "MSFT", "close": 410})
    assert _body(route)["content"] == "MSFT close 410"


# ── ingest_prices ────────────────────────────────────────────────────────────


@respx.mock
def test_ingest_prices_posts_each_bar():
    route = respx.post(f"{PREFIX}/admin/memory").mock(
        return_value=httpx.Response(200, json={"id": "mx"})
    )
    prices = [{"ticker": "AAPL", "close": 1}, {"ticker": "AAPL", "close": 2}]
    with client() as mm:
        out = mm.financial.ingest_prices(prices)
    assert len(out) == 2
    assert route.call_count == 2
    assert [b["content"] for b in _bodies(route)] == ["AAPL close 1", "AAPL close 2"]


# ── ingest_fundamentals ──────────────────────────────────────────────────────


@respx.mock
def test_ingest_fundamentals_posts_fundamental_metadata():
    route = respx.post(f"{PREFIX}/admin/memory").mock(
        return_value=httpx.Response(200, json={"id": "m3"})
    )
    fund = {"ticker": "AAPL", "peRatio": 30, "eps": 6.1}
    with client() as mm:
        mm.financial.ingest_fundamentals(fund)
    body = _body(route)
    assert body["content"] == "Fundamentals AAPL"
    assert body["metadata"] == {"fundamental": fund}


# ── ingest_holding ───────────────────────────────────────────────────────────


@respx.mock
def test_ingest_holding_posts_subject_and_holding():
    route = respx.post(f"{PREFIX}/admin/memory").mock(
        return_value=httpx.Response(200, json={"id": "m4"})
    )
    holding = {"ticker": "AAPL", "shares": 100, "costBasis": 150}
    with client() as mm:
        mm.financial.ingest_holding(PORTFOLIO, holding)
    body = _body(route)
    assert body["content"] == "Holding 100 AAPL"
    assert body["metadata"] == {"subject": PORTFOLIO, "holding": holding}


# ── ingest_news ──────────────────────────────────────────────────────────────


@respx.mock
def test_ingest_news_single_ticker_label():
    route = respx.post(f"{PREFIX}/admin/memory").mock(
        return_value=httpx.Response(200, json={"id": "m5"})
    )
    news = {"ticker": "AAPL", "headline": "Apple beats earnings", "sentiment": 0.7}
    with client() as mm:
        mm.financial.ingest_news(news)
    body = _body(route)
    assert body["content"] == "News [AAPL]: Apple beats earnings"
    assert body["metadata"] == {"newsEvent": news}


@respx.mock
def test_ingest_news_joins_tickers_and_defaults_label():
    route = respx.post(f"{PREFIX}/admin/memory").mock(
        return_value=httpx.Response(200, json={"id": "m6"})
    )
    with client() as mm:
        mm.financial.ingest_news({"tickers": ["AAPL", "MSFT"], "headline": "Sector moves"})
        assert _body(route)["content"] == "News [AAPL,MSFT]: Sector moves"
        mm.financial.ingest_news({"headline": "Macro update"})
        assert _body(route)["content"] == "News [news]: Macro update"


# ── get_profile ──────────────────────────────────────────────────────────────


@respx.mock
def test_get_profile_posts_subject():
    route = respx.post(f"{PREFIX}/lattice/financial/profile").mock(
        return_value=httpx.Response(200, json={"subject": TICKER, "indicators": []})
    )
    with client() as mm:
        out = mm.financial.get_profile(TICKER)
    assert out["subject"] == TICKER
    assert _body(route) == {"subject": TICKER}


# ── predict ──────────────────────────────────────────────────────────────────


@respx.mock
def test_predict_includes_horizon_and_persist():
    route = respx.post(f"{PREFIX}/lattice/financial/predict").mock(
        return_value=httpx.Response(200, json={"signals": [], "strategy": "default"})
    )
    with client() as mm:
        mm.financial.predict(TICKER, horizon_days=14, persist=False)
    assert _body(route) == {"subject": TICKER, "horizonDays": 14, "persist": False}


@respx.mock
def test_predict_bare_subject_only():
    route = respx.post(f"{PREFIX}/lattice/financial/predict").mock(
        return_value=httpx.Response(200, json={"signals": []})
    )
    with client() as mm:
        mm.financial.predict(TICKER)
    assert _body(route) == {"subject": TICKER}


# ── reconcile ────────────────────────────────────────────────────────────────


@respx.mock
def test_reconcile_posts_empty_body():
    route = respx.post(f"{PREFIX}/lattice/financial/reconcile").mock(
        return_value=httpx.Response(200, json={"scored": 0, "hits": 0, "misses": 0})
    )
    with client() as mm:
        out = mm.financial.reconcile()
    assert out["scored"] == 0
    assert _body(route) == {}


# ── get_calibration ──────────────────────────────────────────────────────────


@respx.mock
def test_get_calibration_includes_opts():
    route = respx.post(f"{PREFIX}/lattice/financial/calibration").mock(
        return_value=httpx.Response(200, json={"buckets": [], "strategy": "momentum"})
    )
    with client() as mm:
        mm.financial.get_calibration(bucket_count=8, strategy="momentum")
    assert _body(route) == {"bucketCount": 8, "strategy": "momentum"}


@respx.mock
def test_get_calibration_empty_by_default():
    route = respx.post(f"{PREFIX}/lattice/financial/calibration").mock(
        return_value=httpx.Response(200, json={"buckets": []})
    )
    with client() as mm:
        mm.financial.get_calibration()
    assert _body(route) == {}


# ── async parity smoke ───────────────────────────────────────────────────────


async def test_async_financial_ingest_prices_and_predict():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/admin/memory"):
            return httpx.Response(200, json={"id": "am1"})
        if request.method == "POST" and request.url.path.endswith("/lattice/financial/predict"):
            return httpx.Response(200, json={"signals": [], "strategy": "default"})
        raise AssertionError("unexpected request")

    injected = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with AsyncMemMesh(api_key="sk", project_id=PROJ, http_client=injected) as mm:
        bars = await mm.financial.ingest_prices(
            [{"ticker": "AAPL", "close": 1}, {"ticker": "AAPL", "close": 2}]
        )
        pred = await mm.financial.predict(TICKER, horizon_days=7)
    assert [b["id"] for b in bars] == ["am1", "am1"]
    assert pred["strategy"] == "default"
