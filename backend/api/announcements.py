"""Announcement API endpoints."""

from collections import defaultdict
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Announcement
from backend.schemas import AnnouncementOut, AnnouncementDetail

router = APIRouter()


@router.get("", response_model=list[AnnouncementOut])
def list_announcements(
    date: Optional[str] = Query(None, description="Filter by date YYYY-MM-DD"),
    ticker: Optional[str] = Query(None),
    sector: Optional[str] = Query(None),
    announcement_type: Optional[str] = Query(None),
    min_importance: Optional[float] = Query(None),
    search: Optional[str] = Query(None, description="Search in title"),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    q = db.query(Announcement)

    if date:
        try:
            target = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "date must be YYYY-MM-DD")

        day_start = datetime(target.year, target.month, target.day)
        day_end = datetime(target.year, target.month, target.day, 23, 59, 59)

        # Weekend / holiday / before-open fallback: if the requested date has no
        # announcements, use the most recent date that does — so Friday's data
        # stays visible all weekend until Monday's open repopulates.
        has_data = (
            db.query(Announcement.id)
            .filter(
                Announcement.announcement_datetime >= day_start,
                Announcement.announcement_datetime < day_end,
            )
            .first()
        )
        if not has_data:
            latest = db.query(func.max(Announcement.announcement_datetime)).scalar()
            if latest:
                target = latest.date()
                day_start = datetime(target.year, target.month, target.day)
                day_end = datetime(target.year, target.month, target.day, 23, 59, 59)

        q = q.filter(
            Announcement.announcement_datetime >= day_start,
            Announcement.announcement_datetime < day_end,
        )

    if ticker:
        q = q.filter(Announcement.ticker.ilike(ticker))

    if sector:
        q = q.filter(Announcement.sector.ilike(f"%{sector}%"))

    if announcement_type:
        q = q.filter(Announcement.announcement_type.ilike(f"%{announcement_type}%"))

    if min_importance is not None:
        q = q.filter(Announcement.importance_score >= min_importance)

    if search:
        q = q.filter(Announcement.title.ilike(f"%{search}%"))

    q = q.order_by(Announcement.importance_score.desc(), Announcement.announcement_datetime.desc())

    return q.offset(offset).limit(limit).all()


@router.get("/sectors/summary")
def sectors_summary(
    date: Optional[str] = Query(None, description="YYYY-MM-DD, defaults to today"),
    db: Session = Depends(get_db),
):
    """
    Return announcements grouped by sector for a given date.
    Each sector entry includes count, avg importance, top announcement, and avg price move.
    """
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
        .all()
    )

    groups: dict[str, list] = defaultdict(list)
    for ann in anns:
        sector = ann.sector or "Other / Unknown"
        groups[sector].append(ann)

    result = []
    for sector, items in sorted(groups.items(), key=lambda x: -max((a.importance_score or 0) for a in x[1])):
        scores = [a.importance_score for a in items if a.importance_score is not None]
        moves = [a.price_move_pct for a in items if a.price_move_pct is not None]
        top = items[0]  # already sorted by importance desc
        result.append({
            "sector": sector,
            "count": len(items),
            "avg_importance": round(sum(scores) / len(scores), 1) if scores else None,
            "avg_price_move": round(sum(moves) / len(moves), 2) if moves else None,
            "max_price_move": round(max(moves, key=abs), 2) if moves else None,
            "top_announcement": {
                "id": top.id,
                "ticker": top.ticker,
                "company_name": top.company_name,
                "title": top.title,
                "importance_score": top.importance_score,
                "price_move_pct": top.price_move_pct,
                "why_it_matters": top.why_it_matters or top.summary_short or "",
            },
        })

    return {"date": str(target), "sectors": result}


@router.get("/{id}", response_model=AnnouncementDetail)
def get_announcement(id: int, db: Session = Depends(get_db)):
    ann = db.query(Announcement).filter_by(id=id).first()
    if not ann:
        raise HTTPException(404, f"Announcement {id} not found")
    return ann
