"""
Reports, ingestion trigger, and daily report generation endpoints.
"""

import json
import logging
import os
from datetime import date, datetime
from typing import Optional

import pytz
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.ingestion.announcement_ingestor import ingest_date
from backend.market.price_fetcher import fetch_and_save_prices
from backend.models import Announcement, DailyReport, PriceData
from backend.processing.classifier import classify_announcement
from backend.processing.importance_scorer import score_importance
from backend.processing.summariser import generate_daily_report, summarise_announcement
from backend.schemas import DailyReportOut, IngestResponse

AEST = pytz.timezone("Australia/Sydney")

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/daily-report", response_model=DailyReportOut)
def get_daily_report(
    date: Optional[str] = Query(None, description="YYYY-MM-DD, defaults to today"),
    db: Session = Depends(get_db),
):
    if date:
        try:
            target = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "date must be YYYY-MM-DD")
    else:
        target = datetime.utcnow().date()

    report = db.query(DailyReport).filter(
        DailyReport.date >= datetime(target.year, target.month, target.day),
        DailyReport.date < datetime(target.year, target.month, target.day, 23, 59, 59),
    ).first()

    if not report:
        raise HTTPException(404, f"No daily report found for {target}. Run POST /generate-daily-report first.")
    return report


@router.post("/ingest", response_model=IngestResponse)
def trigger_ingest(
    date: Optional[str] = Query(None, description="YYYY-MM-DD, defaults to today"),
    mock: bool = Query(False, description="Force use of mock data"),
    db: Session = Depends(get_db),
):
    if date:
        try:
            target = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "date must be YYYY-MM-DD")
    else:
        target = datetime.utcnow().date()

    logger.info("Starting ingestion for %s (mock=%s)", target, mock)
    result = ingest_date(target, db, use_mock=mock)
    return IngestResponse(**result)


@router.post("/summarise")
def trigger_summarise(
    date: Optional[str] = Query(None, description="YYYY-MM-DD, defaults to today"),
    db: Session = Depends(get_db),
):
    """Run LLM summarisation + importance scoring on all unsummarised announcements for a date."""
    if date:
        try:
            target = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "date must be YYYY-MM-DD")
    else:
        target = datetime.utcnow().date()

    anns = (
        db.query(Announcement)
        .filter(
            Announcement.announcement_datetime >= datetime(target.year, target.month, target.day),
            Announcement.announcement_datetime < datetime(target.year, target.month, target.day, 23, 59, 59),
            Announcement.summary_short.is_(None),
        )
        .all()
    )

    processed = 0
    for ann in anns:
        try:
            text = ann.cleaned_text or ann.raw_text or ""
            meta = {
                "ticker": ann.ticker,
                "company_name": ann.company_name,
                "sector": ann.sector,
                "title": ann.title,
                "announcement_type": ann.announcement_type,
                "page_count": ann.page_count,
            }

            # Classify if not already done
            if not ann.announcement_type or ann.announcement_type == "Other":
                ann.announcement_type = classify_announcement(text, meta)
                meta["announcement_type"] = ann.announcement_type

            # Price data for context
            price_rec = (
                db.query(PriceData)
                .filter_by(ticker=ann.ticker)
                .order_by(PriceData.date.desc())
                .first()
            )
            price_data = {
                "daily_move_pct": price_rec.daily_move_pct if price_rec else None,
            }

            # Summarise
            summary = summarise_announcement(text, meta, price_data)
            ann.summary_short = summary.get("summary_short", "")
            ann.summary_detailed = summary.get("summary_detailed", "")
            ann.why_it_matters = summary.get("why_it_matters", "")
            ann.market_impact = summary.get("market_impact", "")
            ann.key_numbers = json.dumps(summary.get("key_numbers", []))
            ann.risks_caveats = summary.get("risks_caveats", "")

            # Score importance
            score, reason = score_importance(text, meta, price_data)
            ann.importance_score = score
            ann.importance_reason = reason

            db.commit()
            processed += 1
        except Exception as exc:
            logger.error("Summarise error for announcement %d: %s", ann.id, exc)
            db.rollback()

    return {"date": str(target), "processed": processed}


@router.post("/generate-daily-report", response_model=DailyReportOut)
def trigger_daily_report(
    date: Optional[str] = Query(None, description="YYYY-MM-DD, defaults to today"),
    db: Session = Depends(get_db),
):
    if date:
        try:
            target = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "date must be YYYY-MM-DD")
    else:
        target = datetime.utcnow().date()

    anns = (
        db.query(Announcement)
        .filter(
            Announcement.announcement_datetime >= datetime(target.year, target.month, target.day),
            Announcement.announcement_datetime < datetime(target.year, target.month, target.day, 23, 59, 59),
        )
        .order_by(Announcement.importance_score.desc())
        .limit(50)
        .all()
    )

    prices = (
        db.query(PriceData)
        .filter(
            PriceData.date >= datetime(target.year, target.month, target.day),
            PriceData.date < datetime(target.year, target.month, target.day, 23, 59, 59),
        )
        .order_by(PriceData.daily_move_pct.desc())
        .limit(30)
        .all()
    )

    ann_dicts = [
        {
            "ticker": a.ticker,
            "company_name": a.company_name,
            "title": a.title,
            "announcement_type": a.announcement_type,
            "importance_score": a.importance_score,
            "summary_short": a.summary_short,
            "why_it_matters": a.why_it_matters,
            "price_move_pct": a.price_move_pct,
            "sector": a.sector,
        }
        for a in anns
    ]

    price_dicts = [
        {
            "ticker": p.ticker,
            "company_name": db.query(Announcement).filter_by(ticker=p.ticker).first().company_name
            if db.query(Announcement).filter_by(ticker=p.ticker).first()
            else p.ticker,
            "daily_move_pct": p.daily_move_pct,
            "sector": None,
        }
        for p in prices
    ]

    report_data = generate_daily_report(target, ann_dicts, price_dicts)

    # Upsert daily report
    existing = db.query(DailyReport).filter(
        DailyReport.date >= datetime(target.year, target.month, target.day),
        DailyReport.date < datetime(target.year, target.month, target.day, 23, 59, 59),
    ).first()

    if not existing:
        existing = DailyReport(date=datetime(target.year, target.month, target.day))
        db.add(existing)

    existing.executive_summary = report_data.get("executive_summary", "")
    existing.top_announcements_json = json.dumps(report_data.get("top_announcements", []))
    existing.top_movers_json = json.dumps(price_dicts[:10])
    existing.sector_themes = json.dumps(report_data.get("sector_themes", {}))
    existing.unusual_moves = report_data.get("unusual_moves", "")
    existing.watchlist_tomorrow = json.dumps(report_data.get("watchlist_tomorrow", []))
    existing.full_report_text = report_data.get("full_report_text", "")

    db.commit()
    db.refresh(existing)
    return existing


@router.get("/prices/movers")
def get_price_movers(
    date: Optional[str] = Query(None, description="YYYY-MM-DD, defaults to today"),
    limit: int = Query(20, description="Number of movers to return"),
    db: Session = Depends(get_db),
):
    """Return biggest price movers for a date, directly from PriceData table."""
    if date:
        try:
            target = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "date must be YYYY-MM-DD")
    else:
        target = datetime.utcnow().date()

    # Weekend / holiday / before-open fallback: if the requested date has no price
    # data, use the most recent date that does — keeps Friday's movers visible all
    # weekend until Monday's open repopulates.
    has_prices = (
        db.query(PriceData.id)
        .filter(
            PriceData.date >= datetime(target.year, target.month, target.day),
            PriceData.date < datetime(target.year, target.month, target.day, 23, 59, 59),
            PriceData.daily_move_pct.isnot(None),
        )
        .first()
    )
    if not has_prices:
        latest = db.query(func.max(PriceData.date)).scalar()
        if latest:
            target = latest.date() if isinstance(latest, datetime) else latest

    prices = (
        db.query(PriceData)
        .filter(
            PriceData.date >= datetime(target.year, target.month, target.day),
            PriceData.date < datetime(target.year, target.month, target.day, 23, 59, 59),
            PriceData.daily_move_pct.isnot(None),
        )
        .order_by(PriceData.daily_move_pct.desc())
        .limit(limit * 2)  # fetch extra so we can split gainers/losers
        .all()
    )

    # Also get biggest losers
    losers = (
        db.query(PriceData)
        .filter(
            PriceData.date >= datetime(target.year, target.month, target.day),
            PriceData.date < datetime(target.year, target.month, target.day, 23, 59, 59),
            PriceData.daily_move_pct.isnot(None),
        )
        .order_by(PriceData.daily_move_pct.asc())
        .limit(limit)
        .all()
    )

    def price_to_dict(p: PriceData) -> dict:
        # Try to find company name from announcements
        ann = db.query(Announcement.company_name).filter_by(ticker=p.ticker).first()
        return {
            "ticker": p.ticker,
            "company_name": ann[0] if ann else p.ticker,
            "daily_move_pct": p.daily_move_pct,
            "open": p.open,
            "close": p.close,
            "volume": p.volume,
        }

    return {
        "date": str(target),
        "gainers": [price_to_dict(p) for p in prices[:limit] if (p.daily_move_pct or 0) > 0],
        "losers": [price_to_dict(p) for p in losers[:limit] if (p.daily_move_pct or 0) < 0],
        "all": [price_to_dict(p) for p in prices[:limit]],
    }


@router.get("/prices/movers/news")
def get_mover_news(
    date: Optional[str] = Query(None),
    threshold: float = Query(5.0, description="Min absolute % move to fetch news for"),
    db: Session = Depends(get_db),
):
    """
    For tickers with abs(daily_move_pct) >= threshold, return the reason for the move:
    1. If the ticker has an announcement today in our DB — use that (most reliable)
    2. Otherwise fall back to Yahoo Finance news, but ONLY if published within 24 hours
    """
    import time
    import yfinance as yf

    if date:
        try:
            target = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "date must be YYYY-MM-DD")
    else:
        target = datetime.utcnow().date()

    big_movers = (
        db.query(PriceData)
        .filter(
            PriceData.date >= datetime(target.year, target.month, target.day),
            PriceData.date < datetime(target.year, target.month, target.day, 23, 59, 59),
        )
        .all()
    )
    big_movers = [p for p in big_movers if p.daily_move_pct is not None and abs(p.daily_move_pct) >= threshold]

    cutoff_ts = time.time() - 86_400  # 24 hours ago as unix timestamp
    result = {}

    for price in big_movers:
        # ── 1. Check our DB for an announcement today ──────────────────
        ann = (
            db.query(Announcement)
            .filter(
                Announcement.ticker == price.ticker,
                Announcement.announcement_datetime >= datetime(target.year, target.month, target.day),
                Announcement.announcement_datetime < datetime(target.year, target.month, target.day, 23, 59, 59),
            )
            .order_by(Announcement.importance_score.desc())
            .first()
        )

        if ann:
            result[price.ticker] = [{
                "source": "announcement",
                "title": ann.title,
                "summary": ann.why_it_matters or ann.summary_short or "",
                "url": ann.source_url or "",
                "publisher": "ASX Announcement",
                "type": ann.announcement_type or "",
            }]
            continue

        # ── 2. Fall back to Yahoo Finance — 24h filter only ────────────
        try:
            ticker_obj = yf.Ticker(f"{price.ticker}.AX")
            raw_news = ticker_obj.news or []
            fresh = []
            for item in raw_news:
                content = item.get("content", item)
                # pub date — try multiple locations
                pub_ts = (
                    content.get("pubDate")
                    or content.get("displayTime")
                    or item.get("providerPublishTime")
                )
                # Convert ISO string to timestamp if needed
                if isinstance(pub_ts, str):
                    try:
                        from datetime import timezone
                        pub_ts = datetime.fromisoformat(pub_ts.replace("Z", "+00:00")).timestamp()
                    except Exception:
                        pub_ts = 0
                if pub_ts and float(pub_ts) < cutoff_ts:
                    continue  # skip — older than 24h

                title = content.get("title") or item.get("title", "")
                summary = content.get("summary") or item.get("summary", "")
                url = (content.get("canonicalUrl") or {}).get("url") or item.get("link", "")
                publisher = (content.get("provider") or {}).get("displayName") or item.get("publisher", "")
                if title:
                    fresh.append({
                        "source": "news",
                        "title": title,
                        "summary": summary[:200] if summary else "",
                        "url": url,
                        "publisher": publisher,
                    })
            if fresh:
                result[price.ticker] = fresh[:2]
        except Exception as e:
            logger.debug("News fetch failed for %s: %s", price.ticker, e)

    return result


@router.post("/fetch-prices")
def trigger_price_fetch(
    date: Optional[str] = Query(None, description="YYYY-MM-DD, defaults to today"),
    db: Session = Depends(get_db),
):
    """Fetch and save price data for all tickers that have announcements on a given date."""
    if date:
        try:
            target = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "date must be YYYY-MM-DD")
    else:
        target = datetime.utcnow().date()

    tickers = [
        row[0]
        for row in db.query(Announcement.ticker)
        .filter(
            Announcement.announcement_datetime >= datetime(target.year, target.month, target.day),
        )
        .distinct()
        .all()
    ]

    if not tickers:
        return {"message": "No tickers found for date", "date": str(target)}

    results = fetch_and_save_prices(tickers, target, db)

    # Link price moves back to announcements
    for ticker, price in results.items():
        move = price.get("daily_move_pct")
        abnormal = price.get("abnormal_move_pct")
        db.query(Announcement).filter(
            Announcement.ticker == ticker,
            Announcement.announcement_datetime >= datetime(target.year, target.month, target.day),
            Announcement.announcement_datetime < datetime(target.year, target.month, target.day, 23, 59, 59),
        ).update({"price_move_pct": move, "abnormal_move_pct": abnormal})
    db.commit()

    return {"date": str(target), "tickers_fetched": len(results), "tickers": list(results.keys())}


# ── On-demand announcement enrichment ─────────────────────────────────────────

@router.post("/announcements/{ann_id}/enrich")
def enrich_announcement(
    ann_id: int,
    move: Optional[float] = Query(None, description="Live daily move %% to ground the market-reaction explanation"),
    db: Session = Depends(get_db),
):
    """
    Download the PDF, extract text, re-classify, and generate a proper LLM summary
    for a single announcement. Called when the user clicks "Generate AI Summary".

    `move` is the live price move shown on the card — passed so the AI can explain
    the actual market reaction. Falls back to the announcement's stored move, then
    to the latest PriceData row.

    Returns the updated announcement (same shape as AnnouncementOut).
    """
    from backend.ingestion.asx_client import fetch_announcement_document
    from backend.ingestion.pdf_parser import extract_text_from_bytes

    ann = db.query(Announcement).filter_by(id=ann_id).first()
    if not ann:
        raise HTTPException(404, f"Announcement {ann_id} not found")

    # ── 1. Download + extract PDF text if not already present ─────────────────
    # Re-download if we have no text OR if the stored text is the ASX terms-page
    # disclaimer (older records captured that instead of the real PDF).
    stored = (ann.cleaned_text or "").lower()
    is_disclaimer = "constitutes your agreement" in stored or "access to this site" in stored
    if (not ann.cleaned_text or is_disclaimer) and ann.source_url:
        try:
            raw_bytes = fetch_announcement_document(ann.source_url)
            if raw_bytes:
                text = extract_text_from_bytes(raw_bytes, source_url=ann.source_url)
                if text.strip():
                    import re as _re
                    cleaned = _re.sub(r"\s+", " ", text).strip()
                    ann.raw_text     = text[:20_000]
                    ann.cleaned_text = cleaned[:10_000]
                    db.commit()
        except Exception as exc:
            logger.warning("PDF download/extract failed for ann %d: %s", ann_id, exc)

    text = ann.cleaned_text or ann.raw_text or ""

    # ── 2. Classify if still "Other" ──────────────────────────────────────────
    meta = {
        "ticker":            ann.ticker,
        "company_name":      ann.company_name,
        "sector":            ann.sector,
        "title":             ann.title,
        "announcement_type": ann.announcement_type,
        "page_count":        ann.page_count,
    }
    if not ann.announcement_type or ann.announcement_type == "Other":
        ann.announcement_type = classify_announcement(text, meta, use_llm=False)
        meta["announcement_type"] = ann.announcement_type

    # ── 3. Generate the AI summary (LLM) and store it SEPARATELY ──────────────
    # We keep the rule-based summary_* fields ("the original summary that comes
    # with the announcement") untouched and write the AI version to ai_* fields,
    # so the UI can show the original dot points plus the on-demand AI summary.
    # Resolve the price move so the AI can explain the actual market reaction:
    # live move from the card → stored move → latest PriceData row.
    price_move = move if move is not None else ann.price_move_pct
    if price_move is None:
        # Latest price row that actually HAS a move (yfinance sometimes stores null)
        pd_row = (
            db.query(PriceData)
            .filter(PriceData.ticker == ann.ticker, PriceData.daily_move_pct.isnot(None))
            .order_by(PriceData.date.desc())
            .first()
        )
        if pd_row:
            price_move = pd_row.daily_move_pct
    if price_move is not None and ann.price_move_pct is None:
        ann.price_move_pct = price_move  # backfill the link while we're here

    price_data = {"daily_move_pct": price_move}
    summary = summarise_announcement(text, meta, price_data, use_llm=True)

    ann.ai_business_overview = summary.get("business_overview", "")
    ann.ai_summary           = summary.get("summary_detailed", "")
    ann.ai_summary_short     = summary.get("summary_short",    "")
    ann.ai_why_it_matters    = summary.get("why_it_matters",   "")
    if summary.get("key_numbers"):
        ann.key_numbers = json.dumps(summary.get("key_numbers", []))

    # ── 4. Re-score with real text + price (rule-based — fast, no extra LLM) ───
    score, reason = score_importance(text, meta, price_data, use_llm=False)
    ann.importance_score  = score
    ann.importance_reason = reason

    db.commit()
    db.refresh(ann)
    return ann


@router.get("/announcements/{ann_id}/debug-summary")
def debug_summary(ann_id: int, db: Session = Depends(get_db)):
    """Diagnostic — runs the real summarise LLM call and returns the RAW response."""
    from backend.processing import llm_client
    from backend.processing.summariser import _SYSTEM_SUMMARISE, _USER_SUMMARISE_TMPL

    ann = db.query(Announcement).filter_by(id=ann_id).first()
    if not ann:
        raise HTTPException(404, f"Announcement {ann_id} not found")

    text = ann.cleaned_text or ann.raw_text or ""
    user = _USER_SUMMARISE_TMPL.format(
        ticker=ann.ticker, company=ann.company_name, sector=ann.sector or "",
        ann_type=ann.announcement_type or "", title=ann.title,
        price_move="unknown", text=text[:12000],
    )

    provider = llm_client._provider()
    attempts = []
    if provider == "groq":
        for m in llm_client._groq_models():
            t, err = llm_client._groq_attempt(m, _SYSTEM_SUMMARISE, user, 1500)
            attempts.append({"model": m, "len": len(t), "error": err,
                             "first_400": t[:400], "last_150": t[-150:]})
            if t:
                break
    else:
        raw = llm_client.complete(_SYSTEM_SUMMARISE, user, max_tokens=1500)
        attempts.append({"raw_len": len(raw), "first_400": raw[:400], "last_150": raw[-150:]})

    return {"provider": provider, "text_len": len(text), "attempts": attempts}


# ── Full pipeline trigger (used by GitHub Actions cron) ───────────────────────

def _run_full_pipeline(target_date: date, is_final: bool) -> None:
    """Run inside BackgroundTasks — uses backend.pipeline (import-safe, no file I/O at load)."""
    try:
        from backend.pipeline import run_pipeline
        run_pipeline(target_date, is_final=is_final)
    except Exception as exc:
        logger.exception("Background pipeline failed for %s: %s", target_date, exc)


@router.post("/pipeline/run")
def trigger_pipeline(
    background_tasks: BackgroundTasks,
    is_final: bool = Query(False, description="True for EOD run (16:30 AEST)"),
    x_pipeline_secret: Optional[str] = Header(None, alias="X-Pipeline-Secret"),
):
    """
    Full pipeline trigger — called by GitHub Actions cron.
    Protected by X-Pipeline-Secret header (set PIPELINE_SECRET env var on Render).
    Runs immediately in background and returns 202 Accepted.
    """
    expected = os.environ.get("PIPELINE_SECRET", "")
    if expected and x_pipeline_secret != expected:
        raise HTTPException(status_code=403, detail="Invalid pipeline secret")

    today = datetime.now(AEST).date()
    background_tasks.add_task(_run_full_pipeline, today, is_final)
    label = "EOD" if is_final else "intraday"
    logger.info("Pipeline (%s) triggered via API for %s", label, today)
    return {"status": "started", "date": str(today), "is_final": is_final}
