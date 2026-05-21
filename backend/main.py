"""ASX Intel — FastAPI application entrypoint."""

import logging
import os
import threading
from datetime import date, datetime, timedelta

import pytz
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.api import announcements, companies, sectors, reports, market

AEST = pytz.timezone("Australia/Sydney")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ASX Intel API",
    description="Daily ASX announcement intelligence platform",
    version="0.1.0",
)

# CORS — open to all origins in production (Vercel URL varies), locked down locally
_cors_origins = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if os.environ.get("PRODUCTION") else _cors_origins,
    allow_credentials=False,   # must be False when allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(announcements.router, prefix="/announcements", tags=["announcements"])
app.include_router(companies.router, prefix="/companies", tags=["companies"])
app.include_router(sectors.router, prefix="/sectors", tags=["sectors"])
app.include_router(reports.router, tags=["reports"])
app.include_router(market.router, tags=["market"])


def _start_scheduler_thread() -> None:
    """Start the APScheduler pipeline in a background daemon thread (used in cloud)."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from scripts.scheduler import run_pipeline, is_trading_day

        scheduler = BackgroundScheduler(timezone=AEST)

        def _guard(is_final=False):
            def wrapper():
                today = datetime.now(AEST).date()
                if not is_trading_day(today):
                    return
                run_pipeline(today, is_final=is_final)
            return wrapper

        for hour in range(10, 17):
            scheduler.add_job(
                _guard(is_final=False),
                CronTrigger(day_of_week="mon-fri", hour=hour, minute=0, timezone=AEST),
                id=f"hourly_{hour:02d}",
                misfire_grace_time=300,
            )
        scheduler.add_job(
            _guard(is_final=True),
            CronTrigger(day_of_week="mon-fri", hour=16, minute=30, timezone=AEST),
            id="eod_close",
            misfire_grace_time=300,
        )
        scheduler.start()
        logger.info("Background scheduler started (cloud mode).")
    except Exception as exc:
        logger.warning("Could not start background scheduler: %s", exc)


def _most_recent_trading_date(now: datetime) -> date:
    """
    Most recent trading day relative to `now` (AEST):
      - Weekend            → previous Friday
      - Weekday before 10:00 → previous trading day
      - Weekday from 10:00 → today
    """
    d = now.date()
    wd = d.weekday()  # Mon=0 … Sun=6
    if wd >= 5:                       # Sat/Sun → previous Friday
        return d - timedelta(days=wd - 4)
    if now.hour < 10:                 # before market open → previous trading day
        prev = d - timedelta(days=1)
        while prev.weekday() >= 5:
            prev -= timedelta(days=1)
        return prev
    return d


def _startup_pipeline() -> None:
    """
    Repopulate the DB once at startup (cloud only).

    Render's free tier wipes the SQLite DB on every redeploy, so we ALWAYS rebuild
    the most recent trading day's data — regardless of the time of day. (Previously
    this skipped outside trading hours, which left the DB empty after an after-hours
    deploy.) Runs in a daemon thread so uvicorn starts immediately.

    The pipeline is LLM-free and fast (~6 min for ingest + classify/score + prices);
    real AI summaries are generated lazily on click via /announcements/{id}/enrich.
    """
    import time
    time.sleep(5)  # wait for DB init to complete
    now = datetime.now(AEST)
    target = _most_recent_trading_date(now)
    # EOD/final run if rebuilding today's data after the market has closed
    is_final = target == now.date() and (now.hour > 16 or (now.hour == 16 and now.minute >= 30))
    logger.info(
        "Startup pipeline — rebuilding %s (final=%s) after redeploy [now %s AEST]…",
        target, is_final, now.strftime("%a %H:%M"),
    )
    try:
        from backend.pipeline import run_pipeline
        run_pipeline(target, is_final=is_final)
    except Exception as exc:
        logger.exception("Startup pipeline failed: %s", exc)


@app.on_event("startup")
def on_startup() -> None:
    logger.info("Initialising database…")
    init_db()
    logger.info("ASX Intel API ready.")

    if os.environ.get("PRODUCTION"):
        # Run a catch-up pipeline on startup (handles Render free-tier redeploys)
        t = threading.Thread(target=_startup_pipeline, daemon=True)
        t.start()
        # Also start the hourly APScheduler
        t2 = threading.Thread(target=_start_scheduler_thread, daemon=True)
        t2.start()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/llm/status")
def llm_status(test: bool = False) -> dict:
    """
    Report LLM configuration. Pass ?test=true for a full live diagnostic that
    tries every model/SDK and surfaces the exact error for each — useful right
    after setting GEMINI_API_KEY.
    """
    from backend.processing import llm_client

    if test:
        return llm_client.test_call()
    return llm_client.status()


@app.get("/schedule/status")
def schedule_status() -> dict:
    now = datetime.now(AEST)
    today = now.date()
    is_weekday = today.weekday() < 5

    run_hours = [10, 11, 12, 13, 14, 15, 16]
    run_times = [now.replace(hour=h, minute=0, second=0, microsecond=0) for h in run_hours]
    run_times.append(now.replace(hour=16, minute=30, second=0, microsecond=0))
    run_times.sort()

    next_run = None
    for rt in run_times:
        if rt > now:
            next_run = rt
            break

    if next_run is None:
        tomorrow = today + timedelta(days=1)
        while tomorrow.weekday() >= 5:
            tomorrow += timedelta(days=1)
        next_run = AEST.localize(
            datetime(tomorrow.year, tomorrow.month, tomorrow.day, 10, 0, 0)
        )

    market_open = is_weekday and now.hour >= 10 and (now.hour < 16 or (now.hour == 16 and now.minute <= 12))

    return {
        "aest_now": now.strftime("%A %d %b %Y %H:%M:%S AEST"),
        "is_trading_day": is_weekday,
        "market_open": market_open,
        "next_run": next_run.strftime("%H:%M AEST") if next_run.date() == today else next_run.strftime("%a %d %b %H:%M AEST"),
        "next_run_iso": next_run.isoformat(),
        "schedule": "10:00 → 16:00 hourly + 16:30 EOD (Mon–Fri AEST)",
    }
