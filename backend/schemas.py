"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AnnouncementBase(BaseModel):
    ticker: str
    company_name: str
    sector: Optional[str] = None
    title: str
    announcement_type: Optional[str] = None
    announcement_datetime: datetime
    source_url: Optional[str] = None
    page_count: Optional[int] = None


class AnnouncementOut(AnnouncementBase):
    id: int
    summary_short: Optional[str] = None
    summary_detailed: Optional[str] = None
    why_it_matters: Optional[str] = None
    market_impact: Optional[str] = None
    key_numbers: Optional[str] = None
    risks_caveats: Optional[str] = None
    ai_business_overview: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_summary_short: Optional[str] = None
    ai_why_it_matters: Optional[str] = None
    importance_score: Optional[float] = None
    importance_reason: Optional[str] = None
    price_move_pct: Optional[float] = None
    abnormal_move_pct: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AnnouncementDetail(AnnouncementOut):
    raw_text: Optional[str] = None
    cleaned_text: Optional[str] = None


class PriceDataOut(BaseModel):
    id: int
    ticker: str
    date: datetime
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    prev_close: Optional[float] = None
    volume: Optional[float] = None
    avg_volume_20d: Optional[float] = None
    daily_move_pct: Optional[float] = None
    open_to_close_pct: Optional[float] = None
    volume_spike_ratio: Optional[float] = None

    model_config = {"from_attributes": True}


class CompanyOut(BaseModel):
    id: int
    ticker: str
    name: str
    sector_id: Optional[int] = None
    market_cap: Optional[float] = None

    model_config = {"from_attributes": True}


class SectorOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None

    model_config = {"from_attributes": True}


class DailyReportOut(BaseModel):
    id: int
    date: datetime
    executive_summary: Optional[str] = None
    top_announcements_json: Optional[str] = None
    top_movers_json: Optional[str] = None
    sector_themes: Optional[str] = None
    unusual_moves: Optional[str] = None
    watchlist_tomorrow: Optional[str] = None
    full_report_text: Optional[str] = None
    model_name: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class IngestResponse(BaseModel):
    date: str
    announcements_fetched: int
    announcements_saved: int
    errors: list[str]


class DailyReportRequest(BaseModel):
    date: str
