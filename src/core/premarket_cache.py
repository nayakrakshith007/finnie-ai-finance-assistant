"""File-backed date-keyed cache for the daily pre-market briefing.

One briefing per calendar day (India Standard Time).  All Streamlit sessions
on the same machine share the same cache file, so the first user who clicks
"Pre-Market Briefing" pays the LLM cost; every subsequent visitor that day
reads from cache.

Redis analogy
-------------
This module exposes the same get/set surface as deep_dive_cache.  Swapping to
Redis is mechanical::

    r.set("premarket:" + today, json.dumps(result), exat=midnight_unix)
    cached = r.get("premarket:" + today)

The difference is lifetime: deep_dive_cache uses a rolling 15-min TTL;
this module expires at midnight IST — matching the rhythm of EOD data.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_CACHE_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "premarket_cache.json"
_IST = timezone(timedelta(hours=5, minutes=30))


def _today_ist() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%d")


def _load() -> dict[str, Any]:
    try:
        return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict[str, Any]) -> None:
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get() -> dict[str, Any] | None:
    """Return today's cached briefing, or None if not yet generated."""
    store = _load()
    return (store.get(_today_ist()) or {}).get("result")


def set(result: dict[str, Any]) -> None:  # noqa: A001
    """Store the briefing for today (IST date key)."""
    store = _load()
    today = _today_ist()
    store[today] = {"timestamp": time.time(), "result": result}
    # Keep only the last 7 days to prevent unbounded growth.
    cutoff = (datetime.now(_IST) - timedelta(days=7)).strftime("%Y-%m-%d")
    store = {k: v for k, v in store.items() if k >= cutoff}
    _save(store)


def generated_at() -> str | None:
    """Human-readable IST time when today's briefing was generated, or None."""
    store = _load()
    entry = store.get(_today_ist())
    if not entry:
        return None
    dt = datetime.fromtimestamp(entry.get("timestamp", 0), tz=_IST)
    return dt.strftime("%I:%M %p IST, %d %b %Y")


def invalidate() -> None:
    """Force a fresh fetch for today (manual refresh button)."""
    store = _load()
    store.pop(_today_ist(), None)
    _save(store)
