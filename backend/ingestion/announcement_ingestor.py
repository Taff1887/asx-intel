"""
Main announcement ingestion pipeline.

Orchestrates: fetch → parse → deduplicate → save → schedule summarisation.
"""

import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.ingestion.asx_client import fetch_announcements_for_date, fetch_announcement_document
from backend.ingestion.mock_data import get_mock_announcements
from backend.ingestion.pdf_parser import extract_text_from_bytes
from backend.models import Announcement, Company, Sector

logger = logging.getLogger(__name__)

# Known ASX sector mapping (ticker prefix heuristics — extend as needed)
SECTOR_MAP: dict[str, str] = {
    "BHP": "Materials",
    "RIO": "Materials",
    "FMG": "Materials",
    "MIN": "Materials",
    "PLS": "Materials",
    "WDS": "Energy",
    "STO": "Energy",
    "CBA": "Financials",
    "ANZ": "Financials",
    "NAB": "Financials",
    "WBC": "Financials",
    "MQG": "Financials",
    "REA": "Communication Services",
    "NXT": "Information Technology",
    "TWE": "Consumer Staples",
}


def _infer_sector(ticker: str) -> str:
    return SECTOR_MAP.get(ticker.upper(), "Other")


def _ensure_company(db: Session, ticker: str, company_name: str, sector_name: str) -> None:
    """Insert company + sector if not already present."""
    sector = db.query(Sector).filter_by(name=sector_name).first()
    if not sector:
        sector = Sector(name=sector_name)
        db.add(sector)
        db.flush()

    company = db.query(Company).filter_by(ticker=ticker).first()
    if not company:
        db.add(Company(ticker=ticker, name=company_name, sector_id=sector.id))
        db.flush()


def _clean_text(raw: str) -> str:
    """Basic text cleaning — strip excessive whitespace, control chars."""
    import re
    text = re.sub(r"\s+", " ", raw or "").strip()
    return text


def ingest_date(target_date: date, db: Session, use_mock: bool = False) -> dict[str, Any]:
    """
    Full ingestion pipeline for a single date.

    Returns a summary dict with counts and any errors.
    """
    errors: list[str] = []
    fetched: list[dict] = []

    # --- 1. Fetch announcement metadata ---
    if not use_mock:
        try:
            fetched = fetch_announcements_for_date(target_date)
            logger.info("Fetched %d announcements from ASX for %s", len(fetched), target_date)
        except NotImplementedError as exc:
            logger.warning("%s — falling back to mock data", exc)
            use_mock = True
        except Exception as exc:
            logger.error("ASX fetch failed: %s", exc)
            errors.append(f"Fetch error: {exc}")
            use_mock = True

    if use_mock:
        fetched = get_mock_announcements(target_date)
        logger.info("Using %d mock announcements for %s", len(fetched), target_date)

    saved = 0

    for raw in fetched:
        ticker: str = raw.get("ticker", "").upper().strip()
        company_name: str = raw.get("company_name", ticker)
        title: str = raw.get("title", "")
        ann_dt: datetime = raw.get("announcement_datetime") or datetime.utcnow()
        ann_type: str = raw.get("announcement_type", "Other")
        source_url: str = raw.get("source_url", "")
        page_count: int | None = raw.get("page_count")
        raw_text: str = raw.get("raw_text", "")
        sector_name: str = raw.get("sector") or _infer_sector(ticker)

        if not ticker or not title:
            errors.append(f"Skipped record with missing ticker/title: {raw}")
            continue

        # --- 2. Document download is deferred — too slow for bulk ingest.
        #        PDFs are fetched lazily for high-importance announcements only.

        cleaned = _clean_text(raw_text)

        # --- 3. Ensure company/sector records exist ---
        try:
            _ensure_company(db, ticker, company_name, sector_name)
        except Exception as exc:
            logger.warning("Could not ensure company %s: %s", ticker, exc)

        # --- 4. Save announcement (skip duplicates) ---
        ann = Announcement(
            ticker=ticker,
            company_name=company_name,
            sector=sector_name,
            title=title,
            announcement_type=ann_type,
            announcement_datetime=ann_dt,
            source_url=source_url,
            raw_text=raw_text,
            cleaned_text=cleaned,
            page_count=page_count,
        )
        try:
            db.add(ann)
            db.commit()
            db.refresh(ann)
            saved += 1
            logger.debug("Saved announcement id=%d %s — %s", ann.id, ticker, title)
        except IntegrityError:
            db.rollback()
            logger.debug("Duplicate skipped: %s %s %s", ticker, title, ann_dt)
        except Exception as exc:
            db.rollback()
            msg = f"DB error for {ticker} '{title}': {exc}"
            logger.error(msg)
            errors.append(msg)

    return {
        "date": str(target_date),
        "announcements_fetched": len(fetched),
        "announcements_saved": saved,
        "errors": errors,
    }
