"""Acceptance tests for the market data layer (PRD FR-030 to FR-033).

Every tier of the degradation chain is forced deliberately. Offline and fast:
no network, and the retry sleep is injected so backoff costs no wall-clock time.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from data.market import (
    MAX_ATTEMPTS,
    MarketDataService,
    OutOfScopeError,
    Quote,
    QuoteCache,
    QuoteSource,
    Trend,
    normalise_symbol,
)

NOW = datetime(2026, 11, 8, 10, 30, tzinfo=UTC)


# ── doubles ────────────────────────────────────────────────────────────────────


class FakeFeed:
    """A price feed that can answer, return nothing, or fail a set number of times."""

    def __init__(self, price: float | None = 100.0, *, fail_times: int = 0, exc: Exception | None = None):  # noqa: E501
        self.price = price
        self.fail_times = fail_times
        self.exc = exc or ConnectionError("feed unreachable")
        self.calls = 0

    def fetch(self, symbol: str) -> dict[str, Any] | None:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc
        if self.price is None:
            return None
        return {
            "price": self.price,
            "previous_close": self.price * 0.98,
            "currency": "INR",
            "name": symbol,
        }


@pytest.fixture
def cache(tmp_path) -> QuoteCache:
    return QuoteCache(tmp_path / "cache", ttl_minutes=30)


def service(primary=None, fallback=None, cache=None, **kw) -> MarketDataService:
    return MarketDataService(
        primary=primary if primary is not None else FakeFeed(),
        fallback=fallback if fallback is not None else FakeFeed(price=None),
        cache=cache,
        sleep=lambda _s: None,  # backoff without the wait
        **kw,
    )


def stale_entry(cache: QuoteCache, symbol: str, price: float, minutes_old: int) -> None:
    cache.write(
        Quote(
            symbol=symbol,
            price=price,
            previous_close=price,
            currency="INR",
            as_of=(NOW - timedelta(minutes=minutes_old)).isoformat(),
            source=QuoteSource.LIVE,
        )
    )


# ── symbol normalisation (FR-030) ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("RELIANCE", "RELIANCE.NS"),
        ("reliance", "RELIANCE.NS"),
        ("  tcs  ", "TCS.NS"),
        ("HDFCBANK.NS", "HDFCBANK.NS"),
        ("TCS.BO", "TCS.BO"),
        ("^NSEI", "^NSEI"),
        ("^BSESN", "^BSESN"),
    ],
)
def test_symbol_normalisation(raw, expected):
    assert normalise_symbol(raw) == expected


def test_empty_symbol_is_rejected():
    with pytest.raises(OutOfScopeError):
        normalise_symbol("   ")


def test_index_symbols_never_get_an_exchange_suffix():
    """^NSEI.NS does not exist; appending a suffix to an index is a silent miss."""
    assert normalise_symbol("^NSEI") == "^NSEI"
    assert not normalise_symbol("^NSEI").endswith(".NS")


# ── tier 1: live ───────────────────────────────────────────────────────────────


def test_live_fetch_is_labelled_live(cache):
    quote = service(primary=FakeFeed(1500.0), cache=cache).get_quote("RELIANCE", now=NOW)

    assert quote.symbol == "RELIANCE.NS"
    assert quote.price == 1500.0
    assert quote.source == QuoteSource.LIVE
    assert not quote.is_degraded


def test_change_and_percentage_are_derived():
    quote = Quote("X.NS", 110.0, 100.0, "INR", NOW.isoformat(), QuoteSource.LIVE)
    assert quote.change == 10.0
    assert quote.change_pct == 10.0


def test_zero_previous_close_does_not_divide_by_zero():
    quote = Quote("X.NS", 110.0, 0.0, "INR", NOW.isoformat(), QuoteSource.LIVE)
    assert quote.change_pct == 0.0


# ── tier 2: fresh cache (FR-031) ───────────────────────────────────────────────


def test_fresh_cache_is_served_without_touching_the_feed(cache):
    feed = FakeFeed(1500.0)
    svc = service(primary=feed, cache=cache)

    svc.get_quote("RELIANCE", now=NOW)
    assert feed.calls == 1

    again = svc.get_quote("RELIANCE", now=NOW + timedelta(minutes=5))
    assert feed.calls == 1, "a fresh cache hit must issue no network call"
    assert again.source == QuoteSource.CACHE
    assert again.price == 1500.0


def test_cache_expires_after_the_ttl(cache):
    feed = FakeFeed(1500.0)
    svc = service(primary=feed, cache=cache)

    svc.get_quote("RELIANCE", now=NOW)
    svc.get_quote("RELIANCE", now=NOW + timedelta(minutes=31))
    assert feed.calls == 2, "past the TTL the feed must be consulted again"


def test_unreadable_cache_entry_is_ignored_not_fatal(cache, tmp_path):
    cache.cache_dir.mkdir(parents=True, exist_ok=True)
    (cache.cache_dir / "RELIANCE_NS.json").write_text("{ this is not json", encoding="utf-8")

    quote = service(primary=FakeFeed(1500.0), cache=cache).get_quote("RELIANCE", now=NOW)
    assert quote.source == QuoteSource.LIVE


# ── retries and backoff (FR-032) ───────────────────────────────────────────────


def test_transient_failure_is_retried(cache):
    feed = FakeFeed(1500.0, fail_times=2)
    quote = service(primary=feed, cache=cache).get_quote("RELIANCE", now=NOW)

    assert quote.source == QuoteSource.LIVE
    assert feed.calls == 3


def test_retries_are_bounded(cache):
    feed = FakeFeed(1500.0, fail_times=99)
    service(primary=feed, cache=cache).get_quote("RELIANCE", now=NOW)
    assert feed.calls == MAX_ATTEMPTS, "must not retry forever"


def test_a_clean_no_data_is_not_retried(cache):
    """None means 'this symbol does not exist here' — retrying cannot change that.

    The symbol is then reported as out of scope rather than mocked; see
    test_unknown_symbol_is_rejected_not_mocked for why.
    """
    feed = FakeFeed(price=None)
    with pytest.raises(OutOfScopeError):
        service(primary=feed, cache=cache).get_quote("RELIANCE", now=NOW)
    assert feed.calls == 1


def test_rate_limit_falls_through_to_the_fallback_feed(cache):
    primary = FakeFeed(fail_times=99, exc=RuntimeError("429 Too Many Requests"))
    fallback = FakeFeed(1480.0)

    quote = service(primary=primary, fallback=fallback, cache=cache).get_quote("RELIANCE", now=NOW)

    assert quote.price == 1480.0
    assert quote.source == QuoteSource.LIVE


# ── tier 3: stale cache ────────────────────────────────────────────────────────


def test_total_outage_serves_stale_cache_clearly_labelled(cache):
    stale_entry(cache, "RELIANCE.NS", 1400.0, minutes_old=120)

    quote = service(
        primary=FakeFeed(fail_times=99), fallback=FakeFeed(fail_times=99), cache=cache
    ).get_quote("RELIANCE", now=NOW)

    assert quote.price == 1400.0
    assert quote.source == QuoteSource.STALE_CACHE
    assert quote.is_degraded
    assert "STALE" in quote.freshness_label()


def test_stale_data_is_never_presented_as_live(cache):
    stale_entry(cache, "RELIANCE.NS", 1400.0, minutes_old=600)
    quote = service(primary=FakeFeed(fail_times=99), cache=cache).get_quote("RELIANCE", now=NOW)
    assert quote.source != QuoteSource.LIVE


# ── tier 4: mock ───────────────────────────────────────────────────────────────


# Mock stands in for an OUTAGE, never for a symbol that does not exist.
# Found live on 2026-11-08: AAPL returned a confident mock of INR 593.08, because
# "the feed is down" and "no such symbol" were treated as the same failure.


def test_outage_with_no_cache_returns_marked_mock(cache):
    """Feeds raised — a real symbol may well exist, so a labelled placeholder is fair."""
    quote = service(
        primary=FakeFeed(fail_times=99), fallback=FakeFeed(fail_times=99), cache=cache
    ).get_quote("RELIANCE", now=NOW)

    assert quote.source == QuoteSource.MOCK
    assert quote.is_degraded
    assert "SAMPLE DATA" in quote.freshness_label()


def test_unknown_symbol_is_rejected_not_mocked(cache):
    """Feeds answered cleanly: no such listing. Inventing a rupee price would be worse
    than any error message."""
    svc = service(primary=FakeFeed(price=None), fallback=FakeFeed(price=None), cache=cache)
    with pytest.raises(OutOfScopeError, match="No Indian listing found"):
        svc.get_quote("AAPL", now=NOW)


def test_unknown_symbol_is_not_retried(cache):
    """A 404 is permanent. Retrying it cost 7 seconds before this was fixed."""
    primary = FakeFeed(price=None)
    svc = service(primary=primary, fallback=FakeFeed(price=None), cache=cache)
    with pytest.raises(OutOfScopeError):
        svc.get_quote("AAPL", now=NOW)
    assert primary.calls == 1


def test_mock_prices_are_stable_per_symbol(cache):
    svc = service(primary=FakeFeed(fail_times=99), fallback=FakeFeed(fail_times=99), cache=cache)
    first = svc.get_quote("RELIANCE", now=NOW)
    second = svc.get_quote("RELIANCE", now=NOW)
    assert first.price == second.price, "a demo must not jitter between runs"


def test_mock_can_be_disabled_for_strict_callers(cache):
    svc = service(
        primary=FakeFeed(fail_times=99), fallback=FakeFeed(fail_times=99), cache=cache, allow_mock=False
    )
    with pytest.raises(OutOfScopeError, match="mock data disabled"):
        svc.get_quote("RELIANCE", now=NOW)


def test_known_symbol_falls_back_to_stale_cache_before_mock(cache):
    """Cache beats mock: we have quoted this symbol before, so it is real."""
    stale_entry(cache, "RELIANCE.NS", 1400.0, minutes_old=300)
    quote = service(
        primary=FakeFeed(fail_times=99), fallback=FakeFeed(fail_times=99), cache=cache
    ).get_quote("RELIANCE", now=NOW)
    assert quote.source == QuoteSource.STALE_CACHE


# ── the overall contract ───────────────────────────────────────────────────────


def test_no_fault_injection_scenario_raises(cache):
    """FR-032: zero unhandled failures across quote, rate-limit and outage."""
    scenarios = {
        "clean": service(primary=FakeFeed(1500.0), cache=cache),
        "primary down": service(primary=FakeFeed(fail_times=99), cache=cache),
        "both down": service(
            primary=FakeFeed(fail_times=99), fallback=FakeFeed(fail_times=99), cache=cache
        ),
        "timeout": service(primary=FakeFeed(fail_times=99, exc=TimeoutError("timed out")), cache=cache),
        "rate limited": service(
            primary=FakeFeed(fail_times=99, exc=RuntimeError("429")),
            fallback=FakeFeed(fail_times=99),
            cache=cache,
        ),
    }
    for label, svc in scenarios.items():
        quote = svc.get_quote("RELIANCE", now=NOW)
        assert quote.price > 0, f"{label} produced no usable quote"
        assert quote.source in vars(QuoteSource).values()


def test_freshness_label_exists_for_every_source():
    for source in (QuoteSource.LIVE, QuoteSource.CACHE, QuoteSource.STALE_CACHE, QuoteSource.MOCK):
        quote = Quote("X.NS", 100.0, 99.0, "INR", NOW.isoformat(), source)
        assert quote.freshness_label(), f"{source} has no label"

# ── trend windows (FR-011) ─────────────────────────────────────────────────────


class FakeHistory:
    """A history feed returning a fixed series, or failing."""

    def __init__(self, closes: list[float] | None = None, exc: Exception | None = None):
        self.closes = closes
        self.exc = exc
        self.calls: list[tuple[str, int]] = []

    def history(self, symbol: str, days: int) -> list[float] | None:
        self.calls.append((symbol, days))
        if self.exc is not None:
            raise self.exc
        return self.closes


def test_trend_summarises_the_window():
    t = Trend("RELIANCE.NS", 30, (100.0, 90.0, 120.0, 110.0))
    assert t.start_price == 100.0
    assert t.end_price == 110.0
    assert t.high == 120.0
    assert t.low == 90.0
    assert t.change_pct == 10.0
    assert t.direction == "up"


@pytest.mark.parametrize(
    ("closes", "direction"),
    [
        ((100.0, 110.0), "up"),
        ((100.0, 90.0), "down"),
        ((100.0, 101.0), "flat"),
        ((100.0, 99.0), "flat"),
    ],
)
def test_small_moves_are_flat_not_a_trend(closes, direction):
    """+-2% over a month is drift. Narrating it as a move invites a false cause."""
    assert Trend("X.NS", 30, closes).direction == direction


def test_trend_handles_a_zero_start_price():
    assert Trend("X.NS", 30, (0.0, 50.0)).change_pct == 0.0


def test_one_history_call_serves_every_window(cache):
    history = FakeHistory([float(i) for i in range(1, 91)])
    svc = service(cache=cache, history_feed=history)

    trends = svc.get_trends("RELIANCE", windows=(30, 90))

    assert len(history.calls) == 1, "fetch the longest window once and slice it"
    assert history.calls[0][1] == 90
    assert set(trends) == {30, 90}
    assert len(trends[90].closes) == 90
    assert len(trends[30].closes) == 30
    assert trends[30].closes[-1] == trends[90].closes[-1], "both windows end today"


def test_history_failure_yields_no_trend_rather_than_a_fake_one(cache):
    """A mock price can be labelled; a mock trend is an invented narrative."""
    svc = service(cache=cache, history_feed=FakeHistory(exc=ConnectionError("down")))
    assert svc.get_trends("RELIANCE") == {}


def test_history_is_not_retried(cache):
    """Trend is enrichment on an already-fetched quote; backoff would triple latency."""
    history = FakeHistory(exc=ConnectionError("down"))
    service(cache=cache, history_feed=history).get_trends("RELIANCE")
    assert len(history.calls) == 1


def test_a_single_data_point_is_not_a_trend(cache):
    svc = service(cache=cache, history_feed=FakeHistory([100.0]))
    assert svc.get_trends("RELIANCE") == {}


def test_trend_symbol_is_normalised(cache):
    history = FakeHistory([100.0, 105.0, 110.0])
    trends = service(cache=cache, history_feed=history).get_trends("reliance")
    assert history.calls[0][0] == "RELIANCE.NS"
    assert trends[30].symbol == "RELIANCE.NS"


def test_a_quote_only_feed_simply_has_no_history(cache):
    """FakeFeed has no .history, so trend enrichment is skipped, not faked."""
    assert service(primary=FakeFeed(1500.0), cache=cache).get_trends("RELIANCE") == {}
