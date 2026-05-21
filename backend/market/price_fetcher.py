"""
Share price data fetcher using yfinance.

ASX tickers must be suffixed with .AX (e.g. BHP → BHP.AX).

Modular design: swap out _fetch_ohlcv() to use a paid provider
(Refinitiv, Bloomberg, Iress) without changing anything else.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import yfinance as yf
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import PriceData

logger = logging.getLogger(__name__)

# XJO = ASX 200 benchmark for abnormal move calculation
_BENCHMARK_TICKER = "^AXJO"
_VOLUME_LOOKBACK_DAYS = 30


def _to_asx_ticker(ticker: str) -> str:
    """Append .AX suffix if not already present."""
    ticker = ticker.upper().strip()
    if not ticker.endswith(".AX"):
        ticker = ticker + ".AX"
    return ticker


def _fetch_ohlcv(ticker: str, start: date, end: date) -> pd.DataFrame:
    """
    Download OHLCV from yfinance.

    *** SWAP-OUT POINT ***
    Replace this function body to use a different market data provider.
    The caller expects a DataFrame with columns: Open, High, Low, Close, Volume
    indexed by date. Return an empty DataFrame on failure.
    """
    try:
        asx_ticker = _to_asx_ticker(ticker)
        df = yf.download(
            asx_ticker,
            start=start,
            end=end + timedelta(days=1),  # yfinance end is exclusive
            progress=False,
            auto_adjust=True,
        )
        if df.empty:
            logger.warning("No price data from yfinance for %s", asx_ticker)
        return df
    except Exception as exc:
        logger.error("yfinance error for %s: %s", ticker, exc)
        return pd.DataFrame()


def fetch_price_for_date(ticker: str, target_date: date) -> dict[str, Any] | None:
    """
    Fetch OHLCV + derived metrics for a single ticker on a single date.
    Returns None if no data available.
    """
    # Fetch enough history for average volume calculation
    lookback_start = target_date - timedelta(days=_VOLUME_LOOKBACK_DAYS + 5)
    df = _fetch_ohlcv(ticker, lookback_start, target_date)

    if df.empty:
        return None

    # Flatten MultiIndex columns yfinance may return
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Normalise date index
    df.index = pd.to_datetime(df.index).normalize()
    target_ts = pd.Timestamp(target_date)

    if target_ts not in df.index:
        logger.warning("No trading data for %s on %s (market closed?)", ticker, target_date)
        return None

    row = df.loc[target_ts]
    close = float(row["Close"])
    open_ = float(row["Open"])
    high = float(row["High"])
    low = float(row["Low"])
    volume = float(row["Volume"])

    # Previous close
    prev_idx = df.index.get_loc(target_ts)
    if prev_idx > 0:
        prev_close = float(df.iloc[prev_idx - 1]["Close"])
    else:
        prev_close = open_

    daily_move_pct = ((close - prev_close) / prev_close * 100) if prev_close else None
    open_to_close_pct = ((close - open_) / open_ * 100) if open_ else None

    # Average daily volume over lookback window (excluding target date)
    hist = df[df.index < target_ts]["Volume"]
    avg_volume = float(hist.mean()) if not hist.empty else None
    volume_spike = (volume / avg_volume) if avg_volume and avg_volume > 0 else None

    return {
        "ticker": ticker.upper(),
        "date": target_date,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "prev_close": prev_close,
        "volume": volume,
        "avg_volume_20d": avg_volume,
        "daily_move_pct": daily_move_pct,
        "open_to_close_pct": open_to_close_pct,
        "volume_spike_ratio": volume_spike,
    }


def fetch_benchmark_move(target_date: date) -> float | None:
    """Return the XJO (ASX 200) daily move % for the date."""
    lookback = target_date - timedelta(days=5)
    df = _fetch_ohlcv(_BENCHMARK_TICKER, lookback, target_date)
    if df.empty:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df.index = pd.to_datetime(df.index).normalize()
    target_ts = pd.Timestamp(target_date)

    if target_ts not in df.index:
        return None

    idx = df.index.get_loc(target_ts)
    if idx == 0:
        return None

    close = float(df.iloc[idx]["Close"])
    prev_close = float(df.iloc[idx - 1]["Close"])
    return ((close - prev_close) / prev_close * 100) if prev_close else None


def save_price_data(price: dict[str, Any], db: Session) -> None:
    """Upsert price data record."""
    existing = (
        db.query(PriceData)
        .filter_by(ticker=price["ticker"], date=price["date"])
        .first()
    )
    if existing:
        for k, v in price.items():
            setattr(existing, k, v)
        db.commit()
        return

    record = PriceData(**price)
    try:
        db.add(record)
        db.commit()
    except IntegrityError:
        db.rollback()


def fetch_intraday_bars(ticker: str, interval: str = "1m") -> dict[str, Any]:
    """
    Fetch today's intraday OHLCV bars for a ticker.

    interval options: "1m", "2m", "5m", "15m"
    Returns {"bars": [...], "prev_close": float | None}
    bars are {time, open, high, low, close, volume} dicts for today only.
    Returns {"bars": [], "prev_close": None} if unavailable.
    """
    try:
        asx_ticker = _to_asx_ticker(ticker)
        # Fetch 5 days so we always capture the previous trading day's close
        df = yf.download(
            asx_ticker,
            period="5d",
            interval=interval,
            progress=False,
            auto_adjust=True,
        )
        if df.empty:
            return {"bars": [], "prev_close": None}

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Split into today vs earlier using AEST date
        import pytz
        AEST = pytz.timezone("Australia/Sydney")
        now_aest = datetime.now(AEST)
        today_str = now_aest.strftime("%Y-%m-%d")

        prev_close = None
        today_bars = []
        last_prev_close = None

        for ts, row in df.iterrows():
            # Localise timestamp
            if hasattr(ts, "tz_localize"):
                ts_aest = ts.tz_localize("UTC").tz_convert(AEST) if ts.tzinfo is None else ts.tz_convert(AEST)
            else:
                ts_aest = ts
            bar_date = ts_aest.strftime("%Y-%m-%d")
            close_val = round(float(row["Close"]), 4) if pd.notna(row["Close"]) else None

            if bar_date < today_str:
                # Previous day bars — track the last close as prev_close
                if close_val is not None:
                    last_prev_close = close_val
            elif bar_date == today_str:
                today_bars.append({
                    "time": ts.isoformat(),
                    "open": round(float(row["Open"]), 4) if pd.notna(row["Open"]) else None,
                    "high": round(float(row["High"]), 4) if pd.notna(row["High"]) else None,
                    "low": round(float(row["Low"]), 4) if pd.notna(row["Low"]) else None,
                    "close": close_val,
                    "volume": int(row["Volume"]) if pd.notna(row["Volume"]) else None,
                })

        prev_close = last_prev_close

        return {"bars": today_bars, "prev_close": prev_close}

    except Exception as exc:
        logger.error("Intraday fetch error for %s: %s", ticker, exc)
        return {"bars": [], "prev_close": None}


def get_live_quote(ticker: str) -> dict[str, Any] | None:
    """
    Get the latest price, daily move % vs prev close, and volume for a ticker.
    """
    result = fetch_intraday_bars(ticker, interval="1m")
    bars = result.get("bars", [])
    prev_close = result.get("prev_close")
    if not bars:
        return None

    latest = bars[-1]
    first_bar = bars[0]
    close = latest.get("close")

    # Use real prev_close for daily move; fall back to today's open
    ref = prev_close or first_bar.get("open")
    daily_move = None
    if close and ref and ref != 0:
        daily_move = round((close - ref) / ref * 100, 2)

    return {
        "ticker": ticker.upper(),
        "price": close,
        "prev_close": prev_close,
        "daily_move_pct": daily_move,
        "open": first_bar.get("open"),
        "high": max(b["high"] for b in bars if b.get("high")),
        "low": min(b["low"] for b in bars if b.get("low")),
        "volume": sum(b["volume"] for b in bars if b.get("volume")),
        "bars": len(bars),
        "last_updated": bars[-1]["time"],
    }


def fetch_sector(ticker: str) -> str | None:
    """
    Fetch sector/industry for a ticker from yfinance.
    Returns None if unavailable (don't block price fetching on this).
    """
    try:
        info = yf.Ticker(_to_asx_ticker(ticker)).info
        # yfinance returns sector for larger caps; industry is more granular
        return info.get("sector") or info.get("industry") or None
    except Exception:
        return None


def fetch_and_save_prices(tickers: list[str], target_date: date, db: Session) -> dict[str, Any]:
    """
    Fetch prices for all tickers, compute abnormal moves vs benchmark,
    save to DB, and return a summary dict keyed by ticker.
    Also back-fills sector on Announcement records that have none.
    """
    from backend.models import Announcement

    benchmark_move = fetch_benchmark_move(target_date)
    logger.info("Benchmark (XJO) move for %s: %s%%", target_date, benchmark_move)

    results: dict[str, Any] = {}
    for ticker in tickers:
        try:
            price = fetch_price_for_date(ticker, target_date)
            if price:
                if benchmark_move is not None and price.get("daily_move_pct") is not None:
                    price["abnormal_move_pct"] = price["daily_move_pct"] - benchmark_move
                save_price_data(price, db)
                results[ticker] = price
                logger.debug(
                    "%s: close=%.3f move=%+.1f%%",
                    ticker,
                    price.get("close", 0),
                    price.get("daily_move_pct") or 0,
                )

                # Back-fill sector on announcements that don't have one yet
                needs_sector = (
                    db.query(Announcement)
                    .filter(
                        Announcement.ticker == ticker,
                        Announcement.sector.is_(None),
                    )
                    .first()
                )
                if needs_sector:
                    sector = fetch_sector(ticker)
                    if sector:
                        db.query(Announcement).filter(
                            Announcement.ticker == ticker,
                            Announcement.sector.is_(None),
                        ).update({"sector": sector})
                        db.commit()
                        logger.debug("%s sector → %s", ticker, sector)

        except Exception as exc:
            logger.error("Price fetch error for %s: %s", ticker, exc)

    return results
