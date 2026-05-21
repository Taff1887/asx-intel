"""Sector API endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Announcement, Sector
from backend.schemas import AnnouncementOut, SectorOut

router = APIRouter()


@router.get("", response_model=list[SectorOut])
def list_sectors(db: Session = Depends(get_db)):
    return db.query(Sector).order_by(Sector.name).all()


@router.get("/{name}/announcements", response_model=list[AnnouncementOut])
def sector_announcements(name: str, limit: int = 50, db: Session = Depends(get_db)):
    return (
        db.query(Announcement)
        .filter(Announcement.sector.ilike(f"%{name}%"))
        .order_by(Announcement.importance_score.desc(), Announcement.announcement_datetime.desc())
        .limit(limit)
        .all()
    )
