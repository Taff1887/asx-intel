"""SQLAlchemy ORM models for ASX Intel."""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Sector(Base):
    __tablename__ = "sectors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    companies = relationship("Company", back_populates="sector_rel")


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    sector_id = Column(Integer, ForeignKey("sectors.id"), nullable=True)
    market_cap = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sector_rel = relationship("Sector", back_populates="companies")
    # No ORM relationship to Announcement/PriceData — ticker is a string, not a FK.
    # Use explicit db.query() joins in routes instead.


class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False, index=True)
    company_name = Column(String(255), nullable=False)
    sector = Column(String(100), nullable=True)
    title = Column(String(500), nullable=False)
    announcement_type = Column(String(100), nullable=True)
    announcement_datetime = Column(DateTime, nullable=False, index=True)
    source_url = Column(String(1000), nullable=True)
    raw_text = Column(Text, nullable=True)
    cleaned_text = Column(Text, nullable=True)
    page_count = Column(Integer, nullable=True)

    # LLM-generated fields
    summary_short = Column(Text, nullable=True)
    summary_detailed = Column(Text, nullable=True)
    why_it_matters = Column(Text, nullable=True)
    market_impact = Column(Text, nullable=True)
    key_numbers = Column(Text, nullable=True)
    risks_caveats = Column(Text, nullable=True)

    # On-demand AI summary (generated only when user clicks "Generate AI Summary").
    # Kept separate from the rule-based fields above so the original stays intact.
    ai_business_overview = Column(Text, nullable=True)  # what the company does
    ai_summary = Column(Text, nullable=True)            # newline-joined bullet points
    ai_summary_short = Column(Text, nullable=True)      # one-line headline
    ai_why_it_matters = Column(Text, nullable=True)     # significance + price reaction

    # Classification + scoring
    importance_score = Column(Float, nullable=True)
    importance_reason = Column(Text, nullable=True)

    # Price linkage (populated after market close)
    price_move_pct = Column(Float, nullable=True)
    abnormal_move_pct = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Prevent duplicate ingestion of the same announcement
    __table_args__ = (UniqueConstraint("ticker", "title", "announcement_datetime", name="uq_announcement"),)


class AnnouncementSummary(Base):
    """Stores versioned LLM summaries separately so we can re-run without losing originals."""

    __tablename__ = "announcement_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    announcement_id = Column(Integer, ForeignKey("announcements.id"), nullable=False, index=True)
    model_name = Column(String(100), nullable=True)
    summary_short = Column(Text, nullable=True)
    summary_detailed = Column(Text, nullable=True)
    why_it_matters = Column(Text, nullable=True)
    market_impact = Column(Text, nullable=True)
    key_numbers = Column(Text, nullable=True)
    risks_caveats = Column(Text, nullable=True)
    importance_score = Column(Float, nullable=True)
    importance_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    announcement = relationship("Announcement")


class PriceData(Base):
    __tablename__ = "price_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    open = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    close = Column(Float, nullable=True)
    prev_close = Column(Float, nullable=True)
    volume = Column(Float, nullable=True)
    avg_volume_20d = Column(Float, nullable=True)
    daily_move_pct = Column(Float, nullable=True)
    open_to_close_pct = Column(Float, nullable=True)
    volume_spike_ratio = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("ticker", "date", name="uq_price_date"),)


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, nullable=False, unique=True, index=True)
    executive_summary = Column(Text, nullable=True)
    top_announcements_json = Column(Text, nullable=True)   # JSON list of announcement IDs
    top_movers_json = Column(Text, nullable=True)           # JSON list of ticker/move pairs
    sector_themes = Column(Text, nullable=True)
    unusual_moves = Column(Text, nullable=True)
    watchlist_tomorrow = Column(Text, nullable=True)
    full_report_text = Column(Text, nullable=True)
    model_name = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
