from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.ticket_holds import get_current_user_id
from app.db.session import get_db
from app.models.venue import Venue
from app.schemas.venue import VenueSearchItemResponse
from app.services.venues import get_venue_address_text

router = APIRouter(prefix="/venues", tags=["venues"])


@router.get("/search", response_model=list[VenueSearchItemResponse])
def search_venues(
    q: str = Query(min_length=1, max_length=120),
    limit: int = Query(default=8, ge=1, le=20),
    db: Session = Depends(get_db),
    _user_id: int = Depends(get_current_user_id),
) -> list[VenueSearchItemResponse]:
    trimmed = q.strip()
    if not trimmed:
        return []
    rows = db.execute(
        select(Venue)
        .where(func.lower(Venue.name).contains(trimmed.lower()))
        .order_by(Venue.name.asc(), Venue.id.asc())
        .limit(limit)
    ).scalars().all()
    return [
        VenueSearchItemResponse(id=venue.id, name=venue.name, address_text=get_venue_address_text(venue))
        for venue in rows
    ]
