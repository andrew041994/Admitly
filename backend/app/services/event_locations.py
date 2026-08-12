from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.venue import Venue
from app.services.venues import get_venue_address_text


class EventLocationValidationError(ValueError):
    pass


@dataclass(frozen=True)
class EventLocationState:
    venue_id: int | None
    custom_venue_name: str | None
    custom_address_text: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    is_location_pinned: bool


def validate_event_location(
    db: Session,
    *,
    venue_id: int | None,
    custom_venue_name: str | None,
    custom_address_text: str | None,
    latitude: Decimal | None,
    longitude: Decimal | None,
    is_location_pinned: bool,
) -> tuple[EventLocationState, Venue | None]:
    name = custom_venue_name.strip() if custom_venue_name and custom_venue_name.strip() else None
    address = custom_address_text.strip() if custom_address_text and custom_address_text.strip() else None
    if venue_id is not None and (name is not None or address is not None):
        raise EventLocationValidationError("Use either venue_id or custom venue fields, not both.")
    if venue_id is None and name is None:
        raise EventLocationValidationError("Provide either venue_id or custom_venue_name.")
    if address is not None and name is None:
        raise EventLocationValidationError("custom_address_text requires custom_venue_name.")
    if (latitude is None) != (longitude is None):
        raise EventLocationValidationError("latitude and longitude must be provided together.")
    if latitude is not None and not Decimal("-90") <= latitude <= Decimal("90"):
        raise EventLocationValidationError("latitude must be between -90 and 90.")
    if longitude is not None and not Decimal("-180") <= longitude <= Decimal("180"):
        raise EventLocationValidationError("longitude must be between -180 and 180.")
    if is_location_pinned and latitude is None:
        raise EventLocationValidationError("Pinned locations require latitude and longitude.")

    venue = db.get(Venue, venue_id) if venue_id is not None else None
    if venue_id is not None and venue is None:
        raise EventLocationValidationError("Venue not found.")
    return EventLocationState(
        venue_id=venue_id,
        custom_venue_name=name,
        custom_address_text=address,
        latitude=latitude,
        longitude=longitude,
        is_location_pinned=is_location_pinned,
    ), venue


def describe_event_location(
    db: Session,
    *,
    venue_id: int | None,
    custom_venue_name: str | None,
    custom_address_text: str | None,
) -> str:
    if custom_venue_name:
        return f"{custom_venue_name} — {custom_address_text}" if custom_address_text else custom_venue_name
    venue = db.get(Venue, venue_id) if venue_id is not None else None
    if venue is None:
        return "Venue details unavailable"
    address = get_venue_address_text(venue)
    return f"{venue.name} — {address}" if address else venue.name
