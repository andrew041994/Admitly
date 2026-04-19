from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.venue import Venue


def normalize_venue_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).lower()


def normalize_address_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).lower()


def get_venue_address_text(venue: Venue) -> str | None:
    parts = [venue.address_line1, venue.address_line2, venue.city, venue.country]
    cleaned = [part.strip() for part in parts if part and part.strip()]
    if not cleaned:
        return None
    return ", ".join(cleaned)


def find_venue_by_name_and_address(
    db: Session,
    *,
    venue_name: str,
    address_text: str,
) -> Venue | None:
    normalized_name = normalize_venue_name(venue_name)
    normalized_address = normalize_address_text(address_text)
    candidates = db.execute(
        select(Venue).where(func.lower(Venue.name) == normalized_name).order_by(Venue.id.asc())
    ).scalars().all()
    for venue in candidates:
        existing_address = get_venue_address_text(venue)
        if existing_address and normalize_address_text(existing_address) == normalized_address:
            return venue
    return None


def resolve_or_create_venue(
    db: Session,
    *,
    organizer_id: int,
    venue_name: str,
    address_text: str,
) -> Venue:
    existing = find_venue_by_name_and_address(db, venue_name=venue_name, address_text=address_text)
    if existing is not None:
        return existing

    venue = Venue(
        organizer_id=organizer_id,
        name=re.sub(r"\s+", " ", venue_name.strip()),
        address_line1=re.sub(r"\s+", " ", address_text.strip()),
    )
    db.add(venue)
    db.flush()
    return venue
