"""
ASX Intel — core pipeline logic.

Import-safe: no module-level logging setup, no file I/O at import time.
Used by both the FastAPI background task (reports.py) and the standalone
scheduler (scripts/scheduler.py).
"""

import json
import logging
from datetime import date, datetime

import pytz

logger = logging.getLogger(__name__)

AEST = pytz.timezone("Australia/Sydney")


def run_pipeline(target_date: date, is_final: bool = False, use_mock: bool = False) -> None:
    """
    Execute the full ingestion + analysis pipeline for a given date.

    Steps:
      1. Ingest ASX announcements (deduped)
      2. Classify + LLM-summarise each new announcement
      3. Fetch share prices + link moves back to announcements
      4. Re-score all announcements with actual price moves
      5. Generate / refresh the daily report

    is_final=True skips nothing but is noted in logs (used for EOD run).
    """
    from backend.database import SessionLocal, init_db
    from backend.ingestion.announcement_ingestor import ingest_date
    from backend.market.price_fetcher import fetch_and_save_prices
    from backend.models import Announcement, DailyReport, PriceData
    from backend.processing.classifier import classify_announcement
    from backend.processing.importance_scorer import score_importance
    from backend.processing.summariser import generate_daily_report, summarise_announcement

    label = "EOD" if is_final else "INTRADAY"
    logger.info("=" * 60)
    logger.info("PIPELINE START [%s] %s", label, target_date)
    logger.info("=" * 60)

    init_db()
    db = SessionLocal()

    try:
        # ── 1. Fetch new announcements ────────────────────────────────────────
        logger.info("[1/5] Fetching announcements…")
        result = ingest_date(target_date, db, use_mock=use_mock)
        logger.info(
            "      %d fetched, %d new saved, %d errors",
            result["announcements_fetched"],
            result["announcements_saved"],
            len(result["errors"]),
        )
        for err in result["errors"]:
            logger.warning("      Ingest error: %s", err)

        # ── 2. Classify + score all unsummarised announcements ────────────────
        # NOTE: LLM is intentionally OFF here (use_llm=False). Bulk-LLM-summarising
        # every announcement rate-limits the free Gemini tier and stalls the
        # pipeline before it reaches price fetching. Real AI summaries are made
        # lazily on click via /announcements/{id}/enrich (which downloads the PDF).
        logger.info("[2/5] Classifying and scoring new announcements (rule-based, fast)…")
        unsummarised = (
            db.query(Announcement)
            .filter(
                Announcement.announcement_datetime
                >= datetime(target_date.year, target_date.month, target_date.day),
                Announcement.announcement_datetime
                < datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59),
                Announcement.summary_short.is_(None),
            )
            .all()
        )
        processed = 0
        for ann in unsummarised:
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
                if not ann.announcement_type or ann.announcement_type == "Other":
                    ann.announcement_type = classify_announcement(text, meta, use_llm=False)
                    meta["announcement_type"] = ann.announcement_type

                price_rec = (
                    db.query(PriceData)
                    .filter_by(ticker=ann.ticker)
                    .order_by(PriceData.date.desc())
                    .first()
                )
                price_data = {"daily_move_pct": price_rec.daily_move_pct if price_rec else None}

                summary = summarise_announcement(text, meta, price_data, use_llm=False)
                ann.summary_short = summary.get("summary_short", "")
                ann.summary_detailed = summary.get("summary_detailed", "")
                ann.why_it_matters = summary.get("why_it_matters", "")
                ann.market_impact = summary.get("market_impact", "")
                ann.key_numbers = json.dumps(summary.get("key_numbers", []))
                ann.risks_caveats = summary.get("risks_caveats", "")

                score, reason = score_importance(text, meta, price_data, use_llm=False)
                ann.importance_score = score
                ann.importance_reason = reason

                db.commit()
                processed += 1
            except Exception as exc:
                logger.error("      Error processing ann %d (%s): %s", ann.id, ann.ticker, exc)
                db.rollback()
        logger.info("      Processed %d new announcements", processed)

        # ── 3. Fetch share prices ─────────────────────────────────────────────
        logger.info("[3/5] Fetching share prices…")
        tickers = [
            row[0]
            for row in db.query(Announcement.ticker)
            .filter(
                Announcement.announcement_datetime
                >= datetime(target_date.year, target_date.month, target_date.day),
            )
            .distinct()
            .all()
        ]
        prices: dict = {}
        if tickers:
            prices = fetch_and_save_prices(tickers, target_date, db)
            logger.info("      Fetched prices for %d tickers", len(prices))

            for ticker, p in prices.items():
                db.query(Announcement).filter(
                    Announcement.ticker == ticker,
                    Announcement.announcement_datetime
                    >= datetime(target_date.year, target_date.month, target_date.day),
                    Announcement.announcement_datetime
                    < datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59),
                ).update(
                    {
                        "price_move_pct": p.get("daily_move_pct"),
                        "abnormal_move_pct": p.get("abnormal_move_pct"),
                    }
                )
            db.commit()
        else:
            logger.info("      No tickers to fetch yet")

        # ── 4. Re-score with actual price moves ───────────────────────────────
        if tickers:
            logger.info("[4/5] Re-scoring announcements with price data…")
            todays_anns = (
                db.query(Announcement)
                .filter(
                    Announcement.announcement_datetime
                    >= datetime(target_date.year, target_date.month, target_date.day),
                    Announcement.announcement_datetime
                    < datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59),
                )
                .all()
            )
            rescored = 0
            for ann in todays_anns:
                try:
                    price_data = {"daily_move_pct": ann.price_move_pct}
                    meta = {
                        "ticker": ann.ticker,
                        "title": ann.title,
                        "announcement_type": ann.announcement_type,
                        "sector": ann.sector,
                        "page_count": ann.page_count,
                    }
                    score, reason = score_importance(
                        ann.cleaned_text or ann.raw_text or "", meta, price_data, use_llm=False
                    )
                    ann.importance_score = score
                    ann.importance_reason = reason
                    rescored += 1
                except Exception as exc:
                    logger.error("Re-score error for %s: %s", ann.ticker, exc)
            db.commit()
            logger.info("      Re-scored %d announcements", rescored)
        else:
            logger.info("[4/5] Skipped re-score (no prices yet)")

        # ── 5. Generate / refresh daily report ───────────────────────────────
        logger.info("[5/5] Generating daily report…")
        anns_all = (
            db.query(Announcement)
            .filter(
                Announcement.announcement_datetime
                >= datetime(target_date.year, target_date.month, target_date.day),
                Announcement.announcement_datetime
                < datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59),
            )
            .order_by(Announcement.importance_score.desc())
            .limit(50)
            .all()
        )
        prices_all = (
            db.query(PriceData)
            .filter(
                PriceData.date >= datetime(target_date.year, target_date.month, target_date.day),
                PriceData.date
                < datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59),
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
            for a in anns_all
        ]
        price_dicts = [
            {"ticker": p.ticker, "company_name": p.ticker, "daily_move_pct": p.daily_move_pct}
            for p in prices_all
        ]

        try:
            report_data = generate_daily_report(target_date, ann_dicts, price_dicts)
        except Exception as exc:
            logger.error("Daily report generation failed: %s", exc)
            report_data = {}

        existing = (
            db.query(DailyReport)
            .filter(
                DailyReport.date
                >= datetime(target_date.year, target_date.month, target_date.day),
                DailyReport.date
                < datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59),
            )
            .first()
        )
        if not existing:
            existing = DailyReport(date=datetime(target_date.year, target_date.month, target_date.day))
            db.add(existing)

        existing.executive_summary = report_data.get("executive_summary", "")
        existing.top_announcements_json = json.dumps(report_data.get("top_announcements", []))
        existing.top_movers_json = json.dumps(price_dicts[:10])
        existing.sector_themes = json.dumps(report_data.get("sector_themes", {}))
        existing.unusual_moves = report_data.get("unusual_moves", "")
        existing.watchlist_tomorrow = json.dumps(report_data.get("watchlist_tomorrow", []))
        existing.full_report_text = report_data.get("full_report_text", "")
        db.commit()

        logger.info("=" * 60)
        logger.info(
            "PIPELINE DONE [%s] %s — %d announcements, %d priced",
            label,
            target_date,
            len(anns_all),
            len(prices_all),
        )
        logger.info("=" * 60)

        if report_data.get("executive_summary"):
            logger.info("\n--- MARKET WRAP ---\n%s\n---\n", report_data["executive_summary"])

    except Exception as exc:
        logger.exception("Pipeline failed for %s: %s", target_date, exc)
    finally:
        db.close()
