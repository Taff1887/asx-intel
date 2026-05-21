"""
Historical backfill script.

Usage:
    python scripts/backfill.py --start 2026-01-01 --end 2026-05-14
    python scripts/backfill.py --start 2026-01-01 --end 2026-05-14 --mock
    python scripts/backfill.py --start 2026-01-01 --end 2026-05-14 --skip-weekends
"""

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from scripts.run_daily_ingestion import run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("backfill")

ASX_TRADING_DAYS = {0, 1, 2, 3, 4}  # Mon–Fri (public holidays not filtered here)


def date_range(start: date, end: date, skip_weekends: bool):
    current = start
    while current <= end:
        if not skip_weekends or current.weekday() in ASX_TRADING_DAYS:
            yield current
        current += timedelta(days=1)


def main() -> None:
    parser = argparse.ArgumentParser(description="ASX Intel historical backfill")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--mock", action="store_true", help="Use mock data")
    parser.add_argument("--skip-weekends", action="store_true", default=True, help="Skip Sat/Sun (default: True)")
    parser.add_argument("--skip-prices", action="store_true", help="Skip price fetch")
    parser.add_argument("--skip-summarise", action="store_true", help="Skip LLM summarisation")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds between days (default: 2)")
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()

    days = list(date_range(start, end, skip_weekends=args.skip_weekends))
    logger.info("Backfilling %d trading days from %s to %s", len(days), start, end)

    for i, d in enumerate(days, 1):
        logger.info("Processing day %d/%d: %s", i, len(days), d)
        try:
            run(d, use_mock=args.mock, skip_prices=args.skip_prices, skip_summarise=args.skip_summarise)
        except Exception as exc:
            logger.error("Failed for %s: %s", d, exc)
        if i < len(days) and args.delay > 0:
            time.sleep(args.delay)

    logger.info("Backfill complete.")


if __name__ == "__main__":
    main()
