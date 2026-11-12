"""Market data with a four-tier degradation chain (PRD FR-030 to FR-033).

The design problem
------------------
A demo that depends on a free third-party API will, at some point, be demonstrated
while that API is down, rate-limited, or simply slow. The requirement is not "fetch
a quote" — it is "always return something, and always be honest about what it is".

So every quote carries a `source` saying which tier produced it:

    live        yfinance answered                      trustworthy
    cache       a fresh cached value, within TTL       trustworthy
    stale_cache the TTL expired and the feed failed    usable, labelled old
    mock        nothing else worked                    clearly marked, never silent

Tier 3 is the one people leave out. When the feed dies, a cache that refuses to
serve expired data is worth exactly as much as no cache at all — and the user would
rather see this morning's close, labelled, than an error.

The rule that keeps this honest: a degraded quote is NEVER presented as live. The
`source` and `as_of` fields travel with the number all the way to the UI, so the
caller cannot accidentally lose the provenance.

Indian scope
------------
Bare symbols resolve to NSE (`RELIANCE` -> `RELIANCE.NS`). Index symbols are passed
through. A non-Indian ticker is not special-cased: `AAPL` becomes `AAPL.NS`, which
has no data, and the caller gets an explicit out-of-scope result rather than a
silently wrong number.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from core.config import load_config
from core.logging_setup import get_logger

logger = get_logger(__name__)

# Indian index symbols yfinance understands. Passed through untouched: an index has
# no exchange suffix, and appending one produces a lookup that silently fails.
INDEX_SYMBOLS = {
    "^NSEI", "^BSESN", "^NSEBANK", "^CNXIT",
    "^NSMIDCP",    # Nifty Midcap 100
    "^NSEMDCP50",  # Nifty Midcap 50
    "^CRSLDX",     # Nifty Next 50 (^NSENXT50 is delisted on Yahoo)
    "^INDIAVIX",
}

MAX_ATTEMPTS = 3
BASE_BACKOFF_SECONDS = 0.5


class QuoteSource:
    """Provenance of a quote. Travels with the number; never dropped."""

    LIVE = "live"
    CACHE = "cache"
    STALE_CACHE = "stale_cache"
    MOCK = "mock"


@dataclass(frozen=True)
class Quote:
    """A price point plus the provenance needed to present it honestly."""

    symbol: str
    price: float
    previous_close: float
    currency: str
    as_of: str  # ISO-8601 UTC
    source: str
    name: str = ""

    @property
    def change(self) -> float:
        return round(self.price - self.previous_close, 2)

    @property
    def change_pct(self) -> float:
        if not self.previous_close:
            return 0.0
        return round((self.price - self.previous_close) / self.previous_close * 100, 2)

    @property
    def is_degraded(self) -> bool:
        """True when this did not come from a live fetch or a fresh cache."""
        return self.source in (QuoteSource.STALE_CACHE, QuoteSource.MOCK)

    def freshness_label(self) -> str:
        """Human-readable provenance for the UI (FR-033)."""
        stamp = datetime.fromisoformat(self.as_of).astimezone().strftime("%H:%M")
        return {
            QuoteSource.LIVE: f"as of {stamp}",
            QuoteSource.CACHE: f"as of {stamp}, cached",
            QuoteSource.STALE_CACHE: f"as of {stamp} — STALE, the live feed is unavailable",
            QuoteSource.MOCK: "SAMPLE DATA — no price feed available, not a real price",
        }[self.source]


class OutOfScopeError(ValueError):
    """Raised for a symbol outside the Indian market (PRD non-goal 11)."""


class PriceFeed(Protocol):
    """What the data layer needs from a price source.

    A Protocol rather than a base class so tests can pass a plain object, and so
    swapping yfinance for another provider needs no inheritance.
    """

    def fetch(self, symbol: str) -> dict[str, Any] | None:
        """Return {price, previous_close, currency, name} or None if unavailable."""


# ── price history and trend (FR-011) ──────────────────────────────────────────


@dataclass(frozen=True)
class Trend:
    """A summary of one window of closing prices.

    Deliberately a summary rather than the raw series. The agent needs to *say*
    something about the window ("down 4.2% over 30 days, inside a 1,180–1,310
    range"), and the chart in the Market tab needs the points — so `closes` is
    kept, but every number the narration uses is precomputed here where it can be
    unit-tested, rather than left to the model to derive from a list of floats.
    """

    symbol: str
    days: int
    closes: tuple[float, ...]

    @property
    def start_price(self) -> float:
        return round(self.closes[0], 2)

    @property
    def end_price(self) -> float:
        return round(self.closes[-1], 2)

    @property
    def high(self) -> float:
        return round(max(self.closes), 2)

    @property
    def low(self) -> float:
        return round(min(self.closes), 2)

    @property
    def change_pct(self) -> float:
        if not self.closes[0]:
            return 0.0
        return round((self.closes[-1] - self.closes[0]) / self.closes[0] * 100, 2)

    @property
    def direction(self) -> str:
        """A band, not a prediction.

        The threshold exists so that noise is not narrated as a move: ±2% over a
        month is ordinary drift for an Indian large cap, and calling it a "rise"
        invites the reader to infer a cause that is not there.
        """
        pct = self.change_pct
        if pct > 2:
            return "up"
        if pct < -2:
            return "down"
        return "flat"

    def summary(self) -> str:
        """One line for the prompt and the trace."""
        return (
            f"{self.days}d: {self.direction} {self.change_pct:+.2f}% "
            f"({self.start_price:,.2f} -> {self.end_price:,.2f}, "
            f"range {self.low:,.2f}-{self.high:,.2f})"
        )


class HistoryFeed(Protocol):
    """What the service needs from a source of daily closes."""

    def history(self, symbol: str, days: int) -> list[float] | None:
        """Return daily closing prices oldest-first, or None if unavailable."""


# ── symbol handling ───────────────────────────────────────────────────────────


def normalise_symbol(raw: str, default_suffix: str = ".NS") -> str:
    """Turn user input into a yfinance symbol.

        reliance        -> RELIANCE.NS
        RELIANCE.NS     -> RELIANCE.NS   (already suffixed)
        TCS.BO          -> TCS.BO        (BSE preserved)
        ^NSEI           -> ^NSEI         (index passed through)

    Raises OutOfScopeError on empty input. Non-Indian tickers are not rejected
    here: this function cannot know that AAPL is American without a symbol
    registry, so rejection happens at fetch time, where "no data" is evidence.
    """
    symbol = (raw or "").strip().upper()
    if not symbol:
        raise OutOfScopeError("No symbol given")

    if symbol in INDEX_SYMBOLS or symbol.startswith("^"):
        return symbol
    if "." in symbol:
        return symbol
    return f"{symbol}{default_suffix}"


# ── cache ─────────────────────────────────────────────────────────────────────


class QuoteCache:
    """A file-backed quote cache that can serve expired entries deliberately.

    One JSON file per symbol rather than a single index file: concurrent writes
    from several agents cannot corrupt each other, and a single unparsable file
    costs one symbol instead of the whole cache.
    """

    def __init__(self, cache_dir: Path, ttl_minutes: int) -> None:
        self.cache_dir = Path(cache_dir)
        self.ttl = timedelta(minutes=ttl_minutes)

    def _path(self, symbol: str) -> Path:
        safe = symbol.replace("^", "_idx_").replace(".", "_")
        return self.cache_dir / f"{safe}.json"

    def read(self, symbol: str, *, now: datetime | None = None) -> tuple[Quote, bool] | None:
        """Return (quote, is_fresh) or None when nothing is cached.

        Returning stale entries rather than hiding them is the point: tier 3 of the
        degradation chain needs them, and only the caller knows whether old data
        beats no data.
        """
        path = self._path(symbol)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            quote = Quote(**payload)
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("Unreadable cache entry for %s (%s); ignoring", symbol, exc)
            return None

        now = now or datetime.now(UTC)
        age = now - datetime.fromisoformat(quote.as_of)
        return quote, age <= self.ttl

    def write(self, quote: Quote) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._path(quote.symbol).write_text(
                json.dumps(asdict(quote), indent=2), encoding="utf-8"
            )
        except OSError as exc:
            # A cache that cannot write is a degraded cache, not a failed request.
            logger.warning("Could not cache %s: %s", quote.symbol, exc)


# ── feeds ─────────────────────────────────────────────────────────────────────


class YFinanceFeed:
    """Primary feed. Free, covers NSE and BSE, no API key.

    Note how an unknown symbol is handled. yfinance does not return None for one —
    it raises, often a bare `KeyError('currentTradingPeriod')` from deep inside its
    own parsing. Letting that propagate makes a permanent condition look like a
    transient fault, so the service retries a 404 three times with backoff. Seven
    seconds to learn that Apple is not listed on the NSE.

    So lookup failures are converted to None, meaning "this symbol is not here",
    while genuine transport errors are allowed to raise and be retried.
    """

    # Substrings that mean "no such symbol" rather than "the service is unwell".
    _NOT_FOUND_MARKERS = ("currenttradingperiod", "not found", "delisted", "no data found")

    def fetch(self, symbol: str) -> dict[str, Any] | None:
        import yfinance as yf

        try:
            info = yf.Ticker(symbol).fast_info
            price = getattr(info, "last_price", None)
            previous = getattr(info, "previous_close", None)
        except Exception as exc:  # noqa: BLE001 - classified immediately below
            if any(m in f"{exc}".lower() for m in self._NOT_FOUND_MARKERS):
                logger.info("yfinance has no symbol %s", symbol)
                return None
            raise  # a real transport problem: let the retry loop handle it

        if price is None or previous is None:
            return None
        return {
            "price": float(price),
            "previous_close": float(previous),
            "currency": getattr(info, "currency", None) or "INR",
            "name": symbol,
        }

    def history(self, symbol: str, days: int) -> list[float] | None:
        """Daily closes, oldest first. None when the symbol has no history here."""
        import yfinance as yf

        try:
            # A calendar window, not a session count: yfinance periods are
            # calendar-based, so "30d" yields roughly 21 trading days.
            frame = yf.Ticker(symbol).history(period=f"{days}d", interval="1d")
        except Exception as exc:  # noqa: BLE001 - same classification as fetch()
            if any(m in f"{exc}".lower() for m in self._NOT_FOUND_MARKERS):
                logger.info("yfinance has no history for %s", symbol)
                return None
            raise

        if frame is None or getattr(frame, "empty", True) or "Close" not in frame:
            return None
        # `c == c` drops NaN, which yfinance emits for a holiday inside the window.
        closes = [float(c) for c in frame["Close"].tolist() if c == c]
        return closes or None


class AlphaVantageFeed:
    """Fallback feed — best effort only.

    Alpha Vantage's NSE/BSE coverage is patchy (PRD risk R2), so this tier may
    simply not know an Indian symbol. It is kept because rate-limit handling
    against a real limited API is worth demonstrating, not because it is reliable
    cover. The real safety net is tiers 3 and 4.
    """

    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key

    def fetch(self, symbol: str) -> dict[str, Any] | None:
        if not self.api_key:
            logger.debug("No Alpha Vantage key configured; skipping fallback tier")
            return None

        import httpx

        base = symbol.split(".")[0]
        try:
            response = httpx.get(
                "https://www.alphavantage.co/query",
                params={"function": "GLOBAL_QUOTE", "symbol": f"{base}.BSE", "apikey": self.api_key},
                timeout=10,
            )
            data = response.json().get("Global Quote") or {}
            price = data.get("05. price")
            previous = data.get("08. previous close")
            if not price or not previous:
                return None
            return {
                "price": float(price),
                "previous_close": float(previous),
                "currency": "INR",
                "name": symbol,
            }
        except Exception as exc:  # noqa: BLE001 - any failure just means "try the next tier"
            logger.warning("Alpha Vantage fallback failed for %s: %s", symbol, exc)
            return None


def _mock_quote(symbol: str, now: datetime) -> Quote:
    """Tier 4. Deterministic per symbol, so a demo does not jitter between runs."""
    seed = sum(ord(c) for c in symbol)
    price = round(100 + seed % 900 + (seed % 97) / 100, 2)
    return Quote(
        symbol=symbol,
        price=price,
        previous_close=round(price * 0.995, 2),
        currency="INR",
        as_of=now.isoformat(),
        source=QuoteSource.MOCK,
        name=symbol,
    )


# ── the service ───────────────────────────────────────────────────────────────


class MarketDataService:
    """Fetches quotes, degrading through four tiers and labelling the result."""

    def __init__(
        self,
        primary: PriceFeed | None = None,
        fallback: PriceFeed | None = None,
        cache: QuoteCache | None = None,
        *,
        history_feed: HistoryFeed | None = None,
        allow_mock: bool = True,
        sleep: Any = time.sleep,
    ) -> None:
        cfg = load_config()
        self.cfg = cfg
        self.primary = primary if primary is not None else YFinanceFeed()
        self.fallback = (
            fallback
            if fallback is not None
            else AlphaVantageFeed(cfg.secrets.alpha_vantage_api_key)
        )
        self.cache = cache or QuoteCache(
            cfg.resolve(cfg.market.cache_dir), cfg.market.cache_ttl_minutes
        )
        # YFinanceFeed satisfies both protocols, so by default the quote feed is
        # also the history feed. A test double that only quotes simply has no
        # history, and trend enrichment is skipped rather than faked.
        self.history_feed = (
            history_feed
            if history_feed is not None
            else (self.primary if hasattr(self.primary, "history") else None)
        )
        self.allow_mock = allow_mock
        self._sleep = sleep  # injected so fault-injection tests do not actually wait

    def get_quote(self, raw_symbol: str, *, now: datetime | None = None) -> Quote:
        """Return a quote, never raising for feed trouble. See the module docstring."""
        now = now or datetime.now(UTC)
        symbol = normalise_symbol(raw_symbol, self.cfg.market.exchange_suffix)

        # Tier 2 first when fresh: a cache hit means no network call at all.
        cached = self.cache.read(symbol, now=now)
        if cached and cached[1]:
            logger.debug("Cache hit for %s", symbol)
            return Quote(**{**asdict(cached[0]), "source": QuoteSource.CACHE})

        # Tier 1 — live, with retries. `errored` distinguishes "the feed broke"
        # from "the feed answered: no such symbol". Conflating them is how AAPL
        # ended up with an invented ₹593 price.
        raw, primary_errored = self._fetch_with_retries(self.primary, symbol)
        fallback_errored = False
        if raw is None:
            raw, fallback_errored = self._fetch_with_retries(self.fallback, symbol, label="fallback")
        any_feed_errored = primary_errored or fallback_errored

        if raw is not None:
            quote = Quote(
                symbol=symbol,
                price=raw["price"],
                previous_close=raw["previous_close"],
                currency=raw.get("currency", "INR"),
                as_of=now.isoformat(),
                source=QuoteSource.LIVE,
                name=raw.get("name", symbol),
            )
            self.cache.write(quote)
            return quote

        # Tier 3 — expired cache beats nothing, provided it says so. This applies
        # whichever way the live attempt failed: a symbol we have quoted before is
        # real, so old data for it is still data.
        if cached:
            logger.warning("Live feeds failed for %s; serving STALE cache", symbol)
            return Quote(**{**asdict(cached[0]), "source": QuoteSource.STALE_CACHE})

        # No cache, and the feeds answered cleanly that they have no such symbol.
        # This is not an outage, it is a symbol that does not exist on the Indian
        # exchanges — so say so. Returning a mock here would mean inventing a rupee
        # price for a foreign listing, which is worse than any error message.
        if not any_feed_errored:
            raise OutOfScopeError(
                f"No Indian listing found for {symbol!r}. Finnie covers NSE and BSE "
                "equities and Indian indices only."
            )

        # Tier 4 — the feeds genuinely broke and we have nothing cached. Mock data,
        # loudly labelled, so a demo survives an outage.
        if not self.allow_mock:
            raise OutOfScopeError(f"No market data available for {symbol} and mock data disabled.")
        logger.warning("Feeds unavailable for %s and no cache; returning marked mock", symbol)
        return _mock_quote(symbol, now)

    def get_trends(self, raw_symbol: str, windows: tuple[int, ...] = (30, 90)) -> dict[int, Trend]:
        """Trend summaries per window. Returns {} when history is unavailable.

        One network call serves every window: the longest is fetched and the
        shorter ones are tail slices of it. Asking for 90 days once and slicing
        beats asking twice for 30 and 90.

        Two deliberate asymmetries with `get_quote`:

        * **No mock tier.** A mock *price* can be labelled as sample data; a mock
          *trend* is an invented narrative, and the agent's whole job here is to
          interpret the trend. Absent is honest; fabricated is not.
        * **No retries.** Trend is enrichment on top of a quote that has already
          been fetched. Retrying with backoff would triple the latency of the
          common path to improve a secondary field.
        """
        feed = self.history_feed
        if feed is None or not windows:
            return {}

        symbol = normalise_symbol(raw_symbol, self.cfg.market.exchange_suffix)
        longest = max(windows)
        try:
            closes = feed.history(symbol, longest)
        except Exception as exc:  # noqa: BLE001 - enrichment: degrade to no trend
            logger.warning("History unavailable for %s: %s", symbol, exc)
            return {}

        if not closes or len(closes) < 2:
            logger.info("Not enough history for %s to describe a trend", symbol)
            return {}

        trends: dict[int, Trend] = {}
        for days in sorted(windows):
            # Proportional slice: `days` calendar days is about days/longest of the
            # sessions returned. Two points minimum, or there is no trend to state.
            take = max(2, round(len(closes) * days / longest))
            trends[days] = Trend(symbol=symbol, days=days, closes=tuple(closes[-take:]))
        return trends

    def _fetch_with_retries(
        self, feed: PriceFeed | None, symbol: str, label: str = "primary"
    ) -> tuple[dict[str, Any] | None, bool]:
        """Returns (data, errored).

        `errored` is True only when the feed raised — i.e. it could not answer.
        A clean None means it answered and has no such symbol, which is a fact
        about the symbol rather than a fault, and must not trigger mock data.
        """
        if feed is None:
            return None, False
        for attempt in range(MAX_ATTEMPTS):
            try:
                result = feed.fetch(symbol)
                if result is not None:
                    return result, False
                return None, False  # a clean "no data" is an answer; retrying cannot change it
            except Exception as exc:  # noqa: BLE001 - transport errors all degrade the same way
                if attempt == MAX_ATTEMPTS - 1:
                    logger.warning("%s feed failed for %s after %d attempts: %s",
                                   label, symbol, MAX_ATTEMPTS, exc)
                    return None, True
                # Exponential backoff with jitter. The jitter matters: without it,
                # every client that failed together retries together, and the
                # recovering service is hit by a synchronised thundering herd.
                delay = BASE_BACKOFF_SECONDS * (2**attempt) * (1 + random.random())  # noqa: S311
                logger.debug("%s feed error for %s; retrying in %.2fs", label, symbol, delay)
                self._sleep(delay)
        return None, True
