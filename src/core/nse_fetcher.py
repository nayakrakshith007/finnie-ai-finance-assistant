"""Fetcher for FII/DII cash-segment activity from Moneycontrol.

Moneycontrol embeds data as __NEXT_DATA__ SSR JSON — no JavaScript execution
or authentication needed.  Returns None on any failure so callers can
fall back gracefully.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

_log = logging.getLogger(__name__)

_MC_FIIDII_URL = "https://www.moneycontrol.com/markets/fii-dii-data/"


def fetch_fii_dii() -> dict[str, Any] | None:
    """Fetch the latest FII / DII cash-segment net activity.

    Source: Moneycontrol's __NEXT_DATA__ SSR JSON — no JavaScript needed.
    Fields fiiCM and diiCM are FII/DII net in the cash segment (₹ crore).
    Positive = net buying, negative = net selling.

    Returns a dict with keys:
      fii:  {net_value, date}
      dii:  {net_value, date}
    Returns None on any error.
    """
    import json
    import re

    try:
        r = requests.get(
            _MC_FIIDII_URL,
            timeout=12,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"},
        )
        r.raise_for_status()

        m = re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
        if not m:
            m = re.search(r'type="application/json">(.*?)</script>', r.text, re.DOTALL)
        if not m:
            _log.warning("Moneycontrol FII/DII: __NEXT_DATA__ not found")
            return None

        data: dict = json.loads(m.group(1))
        rows: list[dict] = (
            data.get("props", {})
            .get("pageProps", {})
            .get("FiiDiiData", {})
            .get("fiiDiiData") or []
        )
        if not rows:
            _log.warning("Moneycontrol FII/DII: empty fiiDiiData array")
            return None

        latest = rows[0]

        def _parse(val: Any) -> float | None:
            try:
                return float(str(val).replace(",", "")) if val not in (None, "", "-") else None
            except (ValueError, TypeError):
                return None

        return {
            "fii": {"net_value": _parse(latest.get("fiiCM")), "date": latest.get("date")},
            "dii": {"net_value": _parse(latest.get("diiCM")), "date": latest.get("date")},
        }

    except Exception as exc:
        _log.warning("Moneycontrol FII/DII fetch failed: %s", exc)
        return None
