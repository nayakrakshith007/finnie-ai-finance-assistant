"""Headline feed for the News Synthesizer (PRD FR-014).

Why two payload shapes
----------------------
yfinance's news response changed between versions. Up to roughly 0.2.40 each item
was flat — `title`, `publisher`, `link`, `providerPublishTime` as an epoch. From
roughly 0.2.50 it is nested under `content`, with `pubDate` as an ISO string and
the publisher under `provider.displayName`. The installed version here is 0.2.66,
but pinning to one shape means an upgrade silently returns zero headlines, and
"no news today" is indistinguishable from "the adapter broke". So `_normalise`
reads both and `tests/test_news_feed.py` has a fixture of each.

Verification status, honestly
-----------------------------
On 2026-11-08 Yahoo's news endpoint was down: `Ticker.news` raised
"YAHOO! FINANCE IS CURRENTLY DOWN", and `Search(...).news` returned an empty
list, while quotes kept working normally. So the two shapes come from yfinance's
own source and changelog rather than from a live response, and the outage path is
the one that was observed. **Re-check the live path before recording the demo**
(PRD risk R11); FR-014 is P1 and already on the cut list if it stays down.

That is also why `headlines()` never raises. A news outage must degrade to "I
could not fetch headlines" rather than taking down a turn that the other agents
could still have answered.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from core.logging_setup import get_logger

logger = get_logger(__name__)

DEFAULT_LIMIT = 5  # FR-014: at most five bullets, so no point fetching far more


@dataclass(frozen=True)
class Headline:
    """One article. `url` is required — FR-014 wants every bullet attributable."""

    title: str
    publisher: str
    url: str
    published: str = ""  # ISO-8601, or "" when the feed did not say

    def age_days(self, now: datetime | None = None) -> float | None:
        """How old this is, or None when the feed gave no date.

        Used to tell the model how stale the batch is: a headline from six weeks
        ago should not be narrated as "recent news", and Yahoo mixes ages freely.
        """
        if not self.published:
            return None
        try:
            when = datetime.fromisoformat(self.published)
        except ValueError:
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        return round(((now or datetime.now(UTC)) - when).total_seconds() / 86400, 1)


class NewsFeed(Protocol):
    """What the agent needs from a source of headlines."""

    def headlines(self, query: str, limit: int = DEFAULT_LIMIT) -> list[Headline]:
        """Return up to `limit` headlines, or an empty list. Never raises."""


def _epoch_to_iso(value: Any) -> str:
    try:
        return datetime.fromtimestamp(float(value), tz=UTC).isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def _normalise(raw: dict[str, Any]) -> Headline | None:
    """Turn one yfinance news item into a `Headline`, whichever shape it is.

    Returns None for an item with no title or no link: a bullet Finnie cannot
    attribute is worse than one fewer bullet, because the citation is the only
    thing making the summary checkable.
    """
    if not isinstance(raw, dict):
        return None

    # Newer shape: everything under "content".
    content = raw.get("content")
    if isinstance(content, dict):
        title = str(content.get("title") or "").strip()
        provider = content.get("provider")
        publisher = (
            str(provider.get("displayName") or "").strip()
            if isinstance(provider, dict)
            else ""
        )
        url = ""
        for key in ("canonicalUrl", "clickThroughUrl"):
            candidate = content.get(key)
            if isinstance(candidate, dict) and candidate.get("url"):
                url = str(candidate["url"])
                break
        published = str(content.get("pubDate") or "").strip()
    else:
        # Older flat shape.
        title = str(raw.get("title") or "").strip()
        publisher = str(raw.get("publisher") or "").strip()
        url = str(raw.get("link") or "").strip()
        published = _epoch_to_iso(raw.get("providerPublishTime"))

    if not title or not url:
        return None
    return Headline(
        title=title,
        publisher=publisher or "unknown source",
        url=url,
        published=published,
    )


class YFinanceNewsFeed:
    """Headlines from Yahoo, by ticker or by free-text theme.

    Two routes, because FR-014 covers both "a ticker" and "a theme". A symbol
    goes through `Ticker.news`, which is attached to the listing; anything else
    goes through `Search`, which takes free text. Both are free and need no key.
    """

    def headlines(self, query: str, limit: int = DEFAULT_LIMIT) -> list[Headline]:
        """Up to `limit` headlines. Returns [] on any failure, and says why in the log."""
        if not query or not query.strip():
            return []

        raw_items = self._fetch_raw(query.strip(), limit)
        normalised = [h for h in (_normalise(item) for item in raw_items) if h]

        # De-duplicate by URL: Yahoo repeats the same wire story across providers,
        # and five bullets saying the same thing is not five bullets.
        seen: set[str] = set()
        unique: list[Headline] = []
        for headline in normalised:
            if headline.url in seen:
                continue
            seen.add(headline.url)
            unique.append(headline)

        if len(normalised) != len(raw_items):
            logger.debug(
                "Dropped %d news items with no title or link", len(raw_items) - len(normalised)
            )
        return unique[:limit]

    def _fetch_raw(self, query: str, limit: int) -> list[dict[str, Any]]:
        import yfinance as yf

        is_symbol = "." in query or query.startswith("^") or query.isupper()
        try:
            if is_symbol:
                items = yf.Ticker(query).news or []
                if items:
                    return list(items)
                # A symbol with no attached news still has a themed search.
                logger.debug("No ticker news for %s; trying search", query)
            return list(yf.Search(query, news_count=limit).news or [])
        except Exception as exc:  # noqa: BLE001 - a news outage must not end the turn
            logger.warning("News unavailable for %r: %s: %s", query, type(exc).__name__, exc)
            return []


def build_news_feed() -> NewsFeed:
    """The feed the agent uses in production. Swapped for a double in tests."""
    return YFinanceNewsFeed()
