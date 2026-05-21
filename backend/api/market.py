"""
Market overview — ASX 200 index, S&P 500, AUD/USD, and ASX top-movers.

Top-movers strategy
───────────────────
Yahoo Finance pre-computes top gainers/losers for every exchange including
ASX. We hit their screener endpoint directly — one fast API call, returns
the top N movers in <1 second. No downloading every stock. No background
threads. Just ask Yahoo for the answer and cache it for 5 minutes.
"""

import logging
import time
from datetime import datetime
from typing import Any

import httpx
import pytz
import yfinance as yf
from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)
router = APIRouter()

AEST = pytz.timezone("Australia/Sydney")

# ── Yahoo Finance screener ─────────────────────────────────────────────────────

_SCREENER_URL = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# ── Cache ──────────────────────────────────────────────────────────────────────

_movers_cache: dict | None = None
_movers_ts:    float = 0.0
_MOVERS_TTL    = 300  # 5-minute cache — screener updates every few minutes anyway


def _query_screener(scr_id: str, count: int) -> list[dict]:
    """
    Fetch pre-computed top movers from Yahoo Finance screener.
    scr_id: "day_gainers" or "day_losers"
    Returns a list of {ticker, company_name, daily_move_pct, close}.
    """
    params = {
        "scrIds": scr_id,
        "count":  count,
        "region": "AU",
        "lang":   "en-AU",
    }
    with httpx.Client(timeout=15, headers=_HEADERS) as client:
        resp = client.get(_SCREENER_URL, params=params)
        resp.raise_for_status()

    quotes = (
        resp.json()
        .get("finance", {})
        .get("result", [{}])[0]
        .get("quotes", [])
    )

    result = []
    for q in quotes:
        sym = q.get("symbol", "")
        if not sym.endswith(".AX"):
            continue  # filter to ASX only
        result.append({
            "ticker":         sym.replace(".AX", ""),
            "company_name":   q.get("longName") or q.get("shortName") or sym,
            "daily_move_pct": round(q.get("regularMarketChangePercent", 0), 2),
            "close":          q.get("regularMarketPrice"),
        })
    return result


# ── Market overview ────────────────────────────────────────────────────────────

def _fetch_index(symbol: str, label: str) -> dict[str, Any] | None:
    try:
        hist = yf.Ticker(symbol).history(period="5d", auto_adjust=True)
        if hist.empty or len(hist) < 1:
            return None
        close = float(hist["Close"].iloc[-1])
        prev  = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else None
        chg   = round((close - prev) / prev * 100, 2) if prev else None
        return {"label": label, "price": round(close, 2), "change_pct": chg}
    except Exception as exc:
        logger.debug("Market fetch failed for %s: %s", symbol, exc)
        return None


@router.get("/market/overview")
def market_overview():
    """ASX 200, S&P 500, and AUD/USD via yfinance."""
    return {
        "asx200": _fetch_index("^AXJO", "ASX 200"),
        "sp500":  _fetch_index("^GSPC", "S&P 500"),
        "audusd": _fetch_index("AUDUSD=X", "AUD/USD"),
        "as_of":  datetime.now(AEST).strftime("%H:%M AEST"),
    }


# ── ASX movers ─────────────────────────────────────────────────────────────────

@router.get("/market/asx-movers")
def asx_movers(limit: int = Query(20, description="Movers per side")):
    """
    True ASX top movers via Yahoo Finance pre-computed screener.
    Single API call, returns in <1 second. Cached 5 minutes.
    """
    global _movers_cache, _movers_ts

    now = time.time()
    if _movers_cache is not None and (now - _movers_ts) < _MOVERS_TTL:
        return {
            "gainers": _movers_cache["gainers"][:limit],
            "losers":  _movers_cache["losers"][:limit],
            "as_of":   _movers_cache["as_of"],
        }

    try:
        gainers = _query_screener("day_gainers", limit)
        losers  = _query_screener("day_losers",  limit)
        _movers_cache = {
            "gainers": gainers,
            "losers":  losers,
            "as_of":   datetime.now(AEST).strftime("%H:%M AEST"),
        }
        _movers_ts = now
    except Exception as exc:
        logger.error("ASX movers screener failed: %s", exc)
        # Return stale cache if available, else empty
        if _movers_cache is not None:
            return {
                "gainers": _movers_cache["gainers"][:limit],
                "losers":  _movers_cache["losers"][:limit],
                "as_of":   _movers_cache["as_of"],
            }
        return {"gainers": [], "losers": [], "as_of": None}

    return {
        "gainers": _movers_cache["gainers"][:limit],
        "losers":  _movers_cache["losers"][:limit],
        "as_of":   _movers_cache["as_of"],
    }
