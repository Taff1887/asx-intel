"""
Daily ingestion runner.

Usage:
    python scripts/run_daily_ingestion.py                  # today
    python scripts/run_daily_ingestion.py --date 2026-05-14
    python scripts/run_daily_ingestion.py --mock            # force mock data
    python scripts/run_daily_ingestion.py --skip-prices     # skip price fetch
    python scripts/run_daily_ingestion.py --skip-summarise  # skip LLM summarisation
"""

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

# Ensure the asx_intel root is on sys.path when run as a script
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from backend.database import SessionLocal, init_db
from backend.ingestion.announcement_ingestor import ingest_date
from backend.market.price_fetcher import fetch_and_save_prices
from backend.models import Announcement
from backend.processing.classifier import classify_announcement
from backend.processing.importance_scorer import score_importance
from backend.processing.summariser import generate_daily_report, summarise_announcement
from backend.models import DailyReport, PriceData

import json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("run_daily_ingestion")


def run(target_date: date, use_mock: bool, skip_prices: bool, skip_summarise: bool) -> None:
    logger.info("=== ASX Intel Daily Ingestion: %s ===", target_date)
    init_db()
    db = SessionLocal()

    try:
        # Step 1 — Ingest announcements
        logger.info("Step 1: Fetching announcements…")
        result = ingest_date(target_date, db, use_mock=use_mock)
        logger.info(
            "Ingested %d announcements (%d saved, %d errors)",
            result["announcements_fetched"],
            result["announcements_saved"],
            len(result["errors"]),
        )
        for err in result["errors"]:
            logger.warning("Ingest error: %s", err)

        # Step 2 — Fetch prices
        if not skip_prices:
            logger.info("Step 2: Fetching share prices…")
            tickers = [
                row[0]
                for row in db.query(Announcement.ticker)
                .filter(
                    Announcement.announcement_datetime >= datetime(target_date.year, target_date.month, target_date.day)
                )
                .distinct()
                .all()
            ]
            if tickers:
                prices = fetch_and_save_prices(tickers, target_date, db)
                logger.info("Fetched prices for %d tickers", len(prices))
                for ticker, p in prices.items():
                    move = p.get("daily_move_pct")
                    db.query(Announcement).filter(
                        Announcement.ticker == ticker,
                        Announcement.announcement_datetime >= datetime(target_date.year, target_date.month, target_date.day),
                        Announcement.announcement_datetime < datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59),
                    ).update({"price_move_pct": move, "abnormal_move_pct": p.get("abnormal_move_pct")})
                db.commit()
            else:
                logger.info("No tickers found for %s", target_date)
        else:
            logger.info("Step 2: Skipping price fetch (--skip-prices)")

        # Step 3 — Summarise + classify + score
        if not skip_summarise:
            logger.info("Step 3: Running LLM summarisation + scoring…")
            anns = (
                db.query(Announcement)
                .filter(
                    Announcement.announcement_datetime >= datetime(target_date.year, target_date.month, target_date.day),
                    Announcement.announcement_datetime < datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59),
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
                    if not ann.announcement_type or ann.announcement_type == "Other":
                        ann.announcement_type = classify_announcement(text, meta)
                        meta["announcement_type"] = ann.announcement_type

                    price_rec = db.query(PriceData).filter_by(ticker=ann.ticker).order_by(PriceData.date.desc()).first()
                    price_data = {"daily_move_pct": price_rec.daily_move_pct if price_rec else None}

                    summary = summarise_announcement(text, meta, price_data)
                    ann.summary_short = summary.get("summary_short", "")
                    ann.summary_detailed = summary.get("summary_detailed", "")
                    ann.why_it_matters = summary.get("why_it_matters", "")
                    ann.market_impact = summary.get("market_impact", "")
                    ann.key_numbers = json.dumps(summary.get("key_numbers", []))
                    ann.risks_caveats = summary.get("risks_caveats", "")

                    score, reason = score_importance(text, meta, price_data)
                    ann.importance_score = score
                    ann.importance_reason = reason

                    db.commit()
                    processed += 1
                    logger.debug("Summarised %s: score=%.1f", ann.ticker, score)
                except Exception as exc:
                    logger.error("Summarise error for ann %d: %s", ann.id, exc)
                    db.rollback()

            logger.info("Summarised %d announcements", processed)
        else:
            logger.info("Step 3: Skipping summarisation (--skip-summarise)")

        # Step 4 — Generate daily report
        logger.info("Step 4: Generating daily report…")
        anns_all = (
            db.query(Announcement)
            .filter(
                Announcement.announcement_datetime >= datetime(target_date.year, target_date.month, target_date.day),
                Announcement.announcement_datetime < datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59),
            )
            .order_by(Announcement.importance_score.desc())
            .limit(50)
            .all()
        )
        prices_all = (
            db.query(PriceData)
            .filter(
                PriceData.date >= datetime(target_date.year, target_date.month, target_date.day),
                PriceData.date < datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59),
            )
            .order_by(PriceData.daily_move_pct.desc())
            .limit(30)
            .all()
        )

        ann_dicts = [
            {"ticker": a.ticker, "company_name": a.company_name, "title": a.title,
             "announcement_type": a.announcement_type, "importance_score": a.importance_score,
             "summary_short": a.summary_short, "why_it_matters": a.why_it_matters,
             "price_move_pct": a.price_move_pct, "sector": a.sector}
            for a in anns_all
        ]
        price_dicts = [
            {"ticker": p.ticker, "company_name": p.ticker, "daily_move_pct": p.daily_move_pct}
            for p in prices_all
        ]

        report_data = generate_daily_report(target_date, ann_dicts, price_dicts)

        existing = db.query(DailyReport).filter(
            DailyReport.date >= datetime(target_date.year, target_date.month, target_date.day),
            DailyReport.date < datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59),
        ).first()

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

        logger.info("=== Ingestion complete for %s ===", target_date)
        if report_data.get("executive_summary"):
            print("\n--- MARKET WRAP ---")
            print(report_data["executive_summary"])
            print("-------------------\n")

    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="ASX Intel daily ingestion pipeline")
    parser.add_argument("--date", type=str, default=None, help="Target date YYYY-MM-DD (default: today)")
    parser.add_argument("--mock", action="store_true", help="Force use of mock data")
    parser.add_argument("--skip-prices", action="store_true", help="Skip price fetch")
    parser.add_argument("--skip-summarise", action="store_true", help="Skip LLM summarisation")
    args = parser.parse_args()

    if args.date:
        target = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target = date.today()

    run(target, use_mock=args.mock, skip_prices=args.skip_prices, skip_summarise=args.skip_summarise)


if __name__ == "__main__":
    main()
