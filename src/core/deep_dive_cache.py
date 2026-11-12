"""File-backed TTL cache for stock deep dive results.

Why this exists
---------------
Every deep dive calls yfinance (network) + OpenAI (money). Re-running the same
analysis within 15 minutes gives identical results because yfinance data is
~15-min delayed — so the input hasn't changed and neither would the output.
Caching for exactly that window avoids the cost with no loss of freshness.

Redis analogy
-------------
In production this module would be replaced by two lines:

    import redis
    r = redis.Redis()
    r.set(f"dd:{symbol}", json.dumps(result), ex=TTL_SECONDS)   # write
    cached = r.get(f"dd:{symbol}")                               # read

The interface here (`get` / `set`) is intentionally identical so the swap is
mechanical. The difference is storage: Redis keeps it in RAM on a separate
server (shared across all processes and machines); this module writes a JSON
file on disk (shared across all Streamlit sessions on one machine, survives
restarts, no external service needed).

Cache key: the bare ticker symbol, upper-cased (TCS, RELIANCE, HDFCBANK).
TTL: 900 s = 15 min, matching yfinance's own data delay.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_CACHE_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "deep_dive_cache.json"
TTL_SECONDS = 900  # 15 minutes — matches yfinance ~15-min delayed data


def _load() -> dict[str, Any]:
    try:
        return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict[str, Any]) -> None:
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get(symbol: str) -> dict[str, Any] | None:
    """Return cached result for `symbol` if it exists and hasn't expired."""
    store = _load()
    entry = store.get(symbol.upper())
    if not entry:
        return None
    age = time.time() - entry.get("timestamp", 0)
    if age > TTL_SECONDS:
        return None  # expired — caller will re-fetch
    return entry.get("result")


def set(symbol: str, result: dict[str, Any]) -> None:  # noqa: A001
    """Store `result` for `symbol` with the current timestamp."""
    store = _load()
    store[symbol.upper()] = {"timestamp": time.time(), "result": result}
    _save(store)


def get_stale(symbol: str) -> tuple[dict[str, Any], int] | None:
    """Return ANY cached result for `symbol` regardless of TTL, plus its age in minutes.

    Used as a last resort when the live fetch fails — better to show old data
    with a clear warning than to show nothing at all. Same as Redis's
    `STALE_WHILE_REVALIDATE` / `STALE_IF_ERROR` behaviour.

    Returns (result, age_minutes) or None if no entry exists at all.
    """
    store = _load()
    entry = store.get(symbol.upper())
    if not entry:
        return None
    age_seconds = time.time() - entry.get("timestamp", 0)
    age_minutes = int(age_seconds // 60)
    return entry.get("result"), age_minutes


def invalidate(symbol: str) -> None:
    """Force a fresh fetch next time (e.g. user manually refreshes)."""
    store = _load()
    store.pop(symbol.upper(), None)
    _save(store)


def ttl_remaining(symbol: str) -> int:
    """Seconds until the cached entry expires, or 0 if absent/expired."""
    store = _load()
    entry = store.get(symbol.upper())
    if not entry:
        return 0
    remaining = TTL_SECONDS - (time.time() - entry.get("timestamp", 0))
    return max(0, int(remaining))
