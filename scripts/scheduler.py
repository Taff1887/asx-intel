"""
ASX Intel — Daily Trading Scheduler

Runs automatically on ASX trading days (Mon–Fri, excluding public holidays):

  10:00 AEST  — First announcement fetch of the day
  11:00 AEST  — Hourly re-fetch (picks up new announcements released since last run)
  12:00 AEST  —  "
  13:00 AEST  —  "
  14:00 AEST  —  "
  15:00 AEST  —  "
  16:00 AEST  —  "
  16:30 AEST  — End-of-day: final price fetch, importance scoring, daily report

Each run:
  1. Fetches all new ASX announcements for today (duplicates skipped automatically)
  2. Classifies each: sector, announcement type, importance score
  3. Fetches live share prices for every company that announced
  4. Updates the daily report

Usage:
  python scripts/scheduler.py              # run the scheduler
  python scripts/scheduler.py --now        # run the pipeline immediately then schedule
  python scripts/scheduler.py --dry-run    # print the schedule without running anything

Auto-start on Windows login:
  Run scripts/setup_autostart.bat as Administrator (one time only)
"""

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

import pytz

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# Build log handlers — FileHandler is optional (fails gracefully if data/ missing)
_log_handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
try:
    _data_dir = ROOT / "data"
    _data_dir.mkdir(exist_ok=True)
    _log_handlers.append(logging.FileHandler(_data_dir / "scheduler.log", encoding="utf-8"))
except Exception:
    pass  # Cloud / ephemeral filesystem — stdout-only logging is fine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=_log_handlers,
)
logger = logging.getLogger("asx_scheduler")

AEST = pytz.timezone("Australia/Sydney")

# ASX public holidays (update annually or use the `holidays` package)
# Format: set of (month, day) tuples — approximate; add exact dates each year
ASX_HOLIDAYS_2026: set[date] = {
    date(2026, 1, 1),   # New Year's Day
    date(2026, 1, 26),  # Australia Day
    date(2026, 4, 3),   # Good Friday
    date(2026, 4, 6),   # Easter Monday
    date(2026, 4, 25),  # Anzac Day
    date(2026, 6, 8),   # King's Birthday (QLD — ASX follows NSW/ACT)
    date(2026, 12, 25), # Christmas Day
    date(2026, 12, 26), # Boxing Day
}

ASX_HOLIDAYS_2027: set[date] = {
    date(2027, 1, 1),
    date(2027, 1, 26),
    date(2027, 3, 26),  # Good Friday
    date(2027, 3, 29),  # Easter Monday
    date(2027, 4, 25),
    date(2027, 6, 14),
    date(2027, 12, 25),
    date(2027, 12, 26),
}

ALL_HOLIDAYS = ASX_HOLIDAYS_2026 | ASX_HOLIDAYS_2027


def is_trading_day(d: date | None = None) -> bool:
    """Return True if d (defaults to today AEST) is an ASX trading day."""
    if d is None:
        d = datetime.now(AEST).date()
    return d.weekday() < 5 and d not in ALL_HOLIDAYS


def run_pipeline(target_date: date, is_final: bool = False, use_mock: bool = False) -> None:
    """
    Execute the full ingestion + analysis pipeline for a given date.
    Delegates to backend.pipeline.run_pipeline (single source of truth).
    """
    from backend.pipeline import run_pipeline as _run
    _run(target_date, is_final=is_final, use_mock=use_mock)


def print_schedule() -> None:
    now_aest = datetime.now(AEST)
    logger.info("ASX Intel Scheduler — current time: %s", now_aest.strftime("%A %d %b %Y %H:%M AEST"))
    logger.info("")
    logger.info("Daily schedule (AEST, Mon–Fri, excluding ASX public holidays):")
    logger.info("  10:00  — Morning: first announcement fetch of the day")
    logger.info("  11:00  — Hourly re-fetch")
    logger.info("  12:00  — Hourly re-fetch")
    logger.info("  13:00  — Hourly re-fetch")
    logger.info("  14:00  — Hourly re-fetch")
    logger.info("  15:00  — Hourly re-fetch")
    logger.info("  16:00  — Hourly re-fetch")
    logger.info("  16:30  — EOD: final price close + daily report generation")
    logger.info("")
    today = now_aest.date()
    logger.info("Today (%s) is %s",
                today,
                "a TRADING DAY ✓" if is_trading_day(today) else "NOT a trading day (weekend/holiday)")
    logger.info("")


def main() -> None:
    parser = argparse.ArgumentParser(description="ASX Intel daily scheduler")
    parser.add_argument("--now", action="store_true", help="Run the pipeline immediately for today, then start the schedule")
    parser.add_argument("--dry-run", action="store_true", help="Print schedule and exit without running anything")
    parser.add_argument("--mock", action="store_true", help="Use mock data (for testing without a real ASX connection)")
    args = parser.parse_args()

    # Ensure data dir exists for log file
    (ROOT / "data").mkdir(exist_ok=True)

    print_schedule()

    if args.dry_run:
        logger.info("Dry run — exiting.")
        return

    if args.now:
        today = datetime.now(AEST).date()
        logger.info("--now flag: running pipeline immediately for %s", today)
        run_pipeline(today, is_final=False, use_mock=args.mock)

    # ── Build and start the scheduler ──────────────────────────────────────
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.error("APScheduler not installed. Run: pip install apscheduler pytz")
        sys.exit(1)

    scheduler = BlockingScheduler(timezone=AEST)

    def _guard(fn, **kwargs):
        """Wrap a job so it only runs on trading days."""
        def wrapper():
            today = datetime.now(AEST).date()
            if not is_trading_day(today):
                logger.info("Not a trading day (%s) — skipping.", today)
                return
            fn(today, **kwargs)
        return wrapper

    # 10:00am — morning open (first fetch of the day)
    scheduler.add_job(
        _guard(run_pipeline, is_final=False, use_mock=args.mock),
        CronTrigger(day_of_week="mon-fri", hour=10, minute=0, timezone=AEST),
        id="morning_open",
        name="Morning open — first fetch",
        misfire_grace_time=300,
    )

    # 11:00 → 16:00 — hourly intraday re-fetch
    for hour in range(11, 17):
        scheduler.add_job(
            _guard(run_pipeline, is_final=False, use_mock=args.mock),
            CronTrigger(day_of_week="mon-fri", hour=hour, minute=0, timezone=AEST),
            id=f"hourly_{hour:02d}00",
            name=f"Hourly re-fetch {hour:02d}:00",
            misfire_grace_time=300,
        )

    # 16:30 — end of day: final prices + report
    scheduler.add_job(
        _guard(run_pipeline, is_final=True, use_mock=args.mock),
        CronTrigger(day_of_week="mon-fri", hour=16, minute=30, timezone=AEST),
        id="eod_close",
        name="EOD — final prices + daily report",
        misfire_grace_time=300,
    )

    logger.info("Scheduler started. Waiting for next trading window…")
    logger.info("Press Ctrl+C to stop.")
    logger.info("")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
