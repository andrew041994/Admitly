from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.enums import EventStatus, OrderStatus
from app.models.event import Event
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.organizer_profile import OrganizerProfile
from app.models.ticket_tier import TicketTier
from app.services.events import _build_ticket_tier_code
from app.services.ticket_holds import get_guyana_now


class OrganizerEventError(ValueError):
    pass


class OrganizerEventNotFoundError(OrganizerEventError):
    pass


class OrganizerEventAuthorizationError(OrganizerEventError):
    pass


class OrganizerEventValidationError(OrganizerEventError):
    def __init__(self, *, code: str, errors: list[dict[str, str]]):
        super().__init__(code)
        self.code = code
        self.errors = errors


@dataclass
class OrganizerDashboardMetrics:
    sold_count: int
    gross_revenue: Decimal


def _get_owner_profile(db: Session, *, user_id: int) -> OrganizerProfile | None:
    return db.execute(select(OrganizerProfile).where(OrganizerProfile.user_id == user_id)).scalar_one_or_none()


def get_owned_event_for_update(db: Session, *, actor_user_id: int, event_id: int) -> Event:
    event = db.execute(select(Event).where(Event.id == event_id).with_for_update()).scalar_one_or_none()
    if event is None:
        raise OrganizerEventNotFoundError("Event not found.")
    owner_profile = _get_owner_profile(db, user_id=actor_user_id)
    if owner_profile is None or owner_profile.id != event.organizer_id:
        raise OrganizerEventAuthorizationError("Not authorized to manage this event.")
    db.refresh(event, attribute_names=["ticket_tiers", "venue"])
    return event


def get_owned_event(db: Session, *, actor_user_id: int, event_id: int) -> Event:
    event = (
        db.execute(
            select(Event)
            .options(joinedload(Event.venue), joinedload(Event.ticket_tiers))
            .where(Event.id == event_id)
        )
        .scalars()
        .first()
    )
    if event is None:
        raise OrganizerEventNotFoundError("Event not found.")
    owner_profile = _get_owner_profile(db, user_id=actor_user_id)
    if owner_profile is None or owner_profile.id != event.organizer_id:
        raise OrganizerEventAuthorizationError("Not authorized to manage this event.")
    return event


def validate_event_publishable(event: Event) -> None:
    errors: list[dict[str, str]] = []
    if not event.title or not event.title.strip():
        errors.append({"field": "title", "message": "Title is required."})
    venue_name = event.venue.name if event.venue is not None else event.custom_venue_name
    if not venue_name or not venue_name.strip():
        errors.append({"field": "venue_name", "message": "Venue name is required."})
    if event.start_at is None:
        errors.append({"field": "start_at", "message": "Start date/time is required."})
    if event.end_at is None:
        errors.append({"field": "end_at", "message": "End date/time is required."})
    if event.start_at is not None and event.end_at is not None and event.end_at <= event.start_at:
        errors.append({"field": "end_at", "message": "End date/time must be after start date/time."})

    tiers = list(event.ticket_tiers)
    if not tiers:
        errors.append({"field": "ticket_tiers", "message": "At least one ticket tier is required."})
    else:
        active_with_valid_price = any(t.is_active and Decimal(t.price_amount) >= Decimal("0.00") for t in tiers)
        if not active_with_valid_price:
            errors.append({"field": "ticket_tiers", "message": "At least one active ticket tier with a valid price is required."})

    if errors:
        raise OrganizerEventValidationError(code="publish_validation_failed", errors=errors)


def publish_event(db: Session, *, actor_user_id: int, event_id: int) -> Event:
    event = get_owned_event_for_update(db, actor_user_id=actor_user_id, event_id=event_id)
    if event.status == EventStatus.CANCELLED:
        raise OrganizerEventValidationError(code="invalid_status", errors=[{"field": "status", "message": "Cancelled events cannot be published."}])
    validate_event_publishable(event)
    now = get_guyana_now()
    event.status = EventStatus.PUBLISHED
    event.published_at = now
    event.updated_at = now
    db.flush()
    return event


def unpublish_event(db: Session, *, actor_user_id: int, event_id: int) -> Event:
    event = get_owned_event_for_update(db, actor_user_id=actor_user_id, event_id=event_id)
    if event.status == EventStatus.CANCELLED:
        raise OrganizerEventValidationError(code="invalid_status", errors=[{"field": "status", "message": "Cancelled events cannot be unpublished."}])
    event.status = EventStatus.UNPUBLISHED
    event.updated_at = get_guyana_now()
    db.flush()
    return event


def calculate_event_metrics(db: Session, *, event_id: int) -> OrganizerDashboardMetrics:
    sold_count = db.execute(select(func.coalesce(func.sum(TicketTier.quantity_sold), 0)).where(TicketTier.event_id == event_id)).scalar_one()
    gross = db.execute(
        select(func.coalesce(func.sum(OrderItem.quantity * OrderItem.unit_price), 0))
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.event_id == event_id, Order.status == OrderStatus.COMPLETED)
    ).scalar_one()
    return OrganizerDashboardMetrics(sold_count=int(sold_count or 0), gross_revenue=Decimal(gross or 0))


def update_event_and_tiers(db: Session, *, actor_user_id: int, event_id: int, payload) -> Event:  # noqa: ANN001
    event = get_owned_event_for_update(db, actor_user_id=actor_user_id, event_id=event_id)
    tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
    with tx_ctx:
        for field in [
            "title",
            "short_description",
            "long_description",
            "category",
            "cover_image_url",
            "start_at",
            "end_at",
            "doors_open_at",
            "sales_start_at",
            "sales_end_at",
            "visibility",
            "custom_venue_name",
            "custom_address_text",
        ]:
            value = getattr(payload, field, None)
            if value is not None:
                setattr(event, field, value)

        if event.end_at <= event.start_at:
            raise OrganizerEventValidationError(code="invalid_event", errors=[{"field": "end_at", "message": "end_at must be after start_at."}])

        existing = {tier.id: tier for tier in event.ticket_tiers}
        for idx, tier_payload in enumerate(payload.ticket_tiers or []):
            if tier_payload.id is None:
                tier = TicketTier(
                    event_id=event.id,
                    name=tier_payload.name.strip(),
                    description=tier_payload.description,
                    tier_code=_build_ticket_tier_code(db, event_id=event.id, name=tier_payload.name),
                    price_amount=tier_payload.price_amount,
                    currency=tier_payload.currency,
                    quantity_total=tier_payload.quantity_total,
                    min_per_order=tier_payload.min_per_order,
                    max_per_order=tier_payload.max_per_order,
                    is_active=True if tier_payload.is_active is None else bool(tier_payload.is_active),
                    sort_order=tier_payload.sort_order if tier_payload.sort_order is not None else idx,
                )
                db.add(tier)
                continue

            tier = existing.get(tier_payload.id)
            if tier is None:
                raise OrganizerEventValidationError(code="invalid_tier", errors=[{"field": "ticket_tiers", "message": f"Tier {tier_payload.id} does not belong to event."}])

            sold_or_reserved = max(int(tier.quantity_sold), int(tier.quantity_held))
            if tier_payload.delete:
                if sold_or_reserved > 0:
                    raise OrganizerEventValidationError(
                        code="invalid_tier",
                        errors=[{"field": "ticket_tiers", "message": f"Tier '{tier.name}' has sales/reservations and cannot be deleted. Deactivate instead."}],
                    )
                db.delete(tier)
                continue

            if tier_payload.quantity_total < sold_or_reserved:
                raise OrganizerEventValidationError(
                    code="invalid_tier",
                    errors=[{"field": "ticket_tiers", "message": f"Tier '{tier.name}' quantity cannot be below sold/reserved count ({sold_or_reserved})."}],
                )

            tier.name = tier_payload.name.strip()
            tier.description = tier_payload.description
            tier.price_amount = tier_payload.price_amount
            tier.currency = tier_payload.currency
            tier.quantity_total = tier_payload.quantity_total
            tier.min_per_order = tier_payload.min_per_order
            tier.max_per_order = tier_payload.max_per_order
            if tier_payload.is_active is not None:
                tier.is_active = bool(tier_payload.is_active)
            if tier_payload.sort_order is not None:
                tier.sort_order = tier_payload.sort_order

        event.updated_at = get_guyana_now()
        db.flush()
    return event
