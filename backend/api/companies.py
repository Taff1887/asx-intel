"""Company API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.market.price_fetcher import fetch_intraday_bars, get_live_quote
from backend.models import Announcement, Company, PriceData
from backend.schemas import AnnouncementOut, CompanyOut, PriceDataOut

router = APIRouter()


@router.get("", response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db)):
    return db.query(Company).order_by(Company.ticker).all()


@router.get("/{ticker}", response_model=CompanyOut)
def get_company(ticker: str, db: Session = Depends(get_db)):
    company = db.query(Company).filter_by(ticker=ticker.upper()).first()
    if not company:
        raise HTTPException(404, f"Company {ticker} not found")
    return company


@router.get("/{ticker}/announcements", response_model=list[AnnouncementOut])
def company_announcements(ticker: str, limit: int = 50, db: Session = Depends(get_db)):
    return (
        db.query(Announcement)
        .filter(Announcement.ticker.ilike(ticker))
        .order_by(Announcement.announcement_datetime.desc())
        .limit(limit)
        .all()
    )


@router.get("/{ticker}/prices", response_model=list[PriceDataOut])
def company_prices(ticker: str, limit: int = 60, db: Session = Depends(get_db)):
    return (
        db.query(PriceData)
        .filter(PriceData.ticker.ilike(ticker))
        .order_by(PriceData.date.desc())
        .limit(limit)
        .all()
    )


@router.get("/{ticker}/intraday")
def company_intraday(
    ticker: str,
    interval: str = Query("5m", description="Bar interval: 1m, 2m, 5m, 15m"),
):
    """
    Live intraday price bars for today.
    Fetched fresh from yfinance on every call — poll every 60s from the frontend.
    Returns [] outside ASX market hours (10am–4pm AEST Mon–Fri).
    """
    result = fetch_intraday_bars(ticker.upper(), interval=interval)
    return {
        "ticker": ticker.upper(),
        "interval": interval,
        "bars": result.get("bars", []),
        "prev_close": result.get("prev_close"),
    }


@router.get("/{ticker}/quote")
def live_quote(ticker: str):
    """
    Latest price + daily move % for a single ticker.
    Lightweight endpoint for dashboard price cards — call every 60s.
    """
    quote = get_live_quote(ticker.upper())
    if not quote:
        raise HTTPException(404, f"No live data for {ticker} — market may be closed")
    return quote


@router.get("/quotes/batch")
def batch_quotes(tickers: str = Query(..., description="Comma-separated tickers, e.g. BHP,CBA,WDS")):
    """
    Fetch latest quote for multiple tickers in one call.
    Returns dict keyed by ticker.
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    results = {}
    for ticker in ticker_list[:20]:  # cap at 20 to avoid slow responses
        q = get_live_quote(ticker)
        if q:
            results[ticker] = q
    return results
