from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.venue import Venue


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def normalize_venue_name(value: str) -> str:
    return _collapse_whitespace(value).lower()


def normalize_address_text(value: str) -> str:
    return _collapse_whitespace(value).lower()


def get_venue_address_text(venue: Venue) -> str | None:
    parts = [venue.address_line1, venue.address_line2, venue.city, venue.country]
    cleaned = [_collapse_whitespace(part) for part in parts if part and part.strip()]
    if not cleaned:
        return None
    return ", ".join(cleaned)


def find_venue_by_name_and_address(
    db: Session,
    *,
    organizer_id: int,
    venue_name: str,
    address_text: str,
) -> Venue | None:
    normalized_name = normalize_venue_name(venue_name)
    normalized_address = normalize_address_text(address_text)
    candidates = db.execute(
        select(Venue).where(Venue.organizer_id == organizer_id).order_by(Venue.id.asc())
    ).scalars().all()
    for venue in candidates:
        if normalize_venue_name(venue.name or "") != normalized_name:
            continue
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
    existing = find_venue_by_name_and_address(
        db,
        organizer_id=organizer_id,
        venue_name=venue_name,
        address_text=address_text,
    )
    if existing is not None:
        return existing

    venue = Venue(
        organizer_id=organizer_id,
        name=_collapse_whitespace(venue_name),
        address_line1=_collapse_whitespace(address_text),
    )
    db.add(venue)
    db.flush()
    return venue
