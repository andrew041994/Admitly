from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.enums import EventApprovalStatus, EventStatus, OrderStatus
from app.models.event import Event
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.organizer_profile import OrganizerProfile
from app.models.ticket_tier import TicketTier
from app.models.user import User
from app.services.events import _build_ticket_tier_code
from app.services.event_locations import EventLocationValidationError, validate_event_location
from app.services.event_permissions import EventPermissionAction, has_event_permission
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
    if not has_event_permission(db, user_id=actor_user_id, event=event, action=EventPermissionAction.EDIT_EVENT):
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
    if not has_event_permission(db, user_id=actor_user_id, event=event, action=EventPermissionAction.EDIT_EVENT):
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
    creator = db.get(User, event.organizer.user_id)
    if creator is None or creator.creator_age_identity_verification_status != "verified":
        raise OrganizerEventValidationError(
            code="creator_age_identity_verification_required",
            errors=[{
                "field": "creator_age_identity_verification",
                "message": "Creator age and identity verification is required before publication.",
            }],
        )
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
    schedule_fields = {"start_at", "end_at", "doors_open_at", "sales_start_at", "sales_end_at"}
    venue_fields = {"venue_id", "custom_venue_name", "custom_address_text", "latitude", "longitude", "is_location_pinned"}
    if event.approval_status == EventApprovalStatus.APPROVED:
        changed_material_fields = [
            field
            for field in (schedule_fields | venue_fields).intersection(payload.model_fields_set)
            if getattr(payload, field) != getattr(event, field)
        ]
        if changed_material_fields:
            raise OrganizerEventValidationError(
                code="material_change_required",
                errors=[{
                    "field": field,
                    "message": "Approved event schedules and venues must be changed through Reschedule or Change Venue.",
                } for field in sorted(changed_material_fields)],
            )
    for field in [
        "title",
        "short_description",
        "long_description",
        "category",
        "start_at",
        "end_at",
        "doors_open_at",
        "sales_start_at",
        "sales_end_at",
        "visibility",
    ]:
        value = getattr(payload, field, None)
        if value is not None:
            setattr(event, field, value)

    if venue_fields.intersection(payload.model_fields_set):
        requested_venue_id = payload.venue_id if "venue_id" in payload.model_fields_set else event.venue_id
        requested_name = payload.custom_venue_name if "custom_venue_name" in payload.model_fields_set else event.custom_venue_name
        requested_address = payload.custom_address_text if "custom_address_text" in payload.model_fields_set else event.custom_address_text
        if "venue_id" in payload.model_fields_set and payload.venue_id is not None:
            requested_name = None
            requested_address = None
        elif "custom_venue_name" in payload.model_fields_set and payload.custom_venue_name:
            requested_venue_id = None
        try:
            location, venue = validate_event_location(
                db,
                venue_id=requested_venue_id,
                custom_venue_name=requested_name,
                custom_address_text=requested_address,
                latitude=payload.latitude if "latitude" in payload.model_fields_set else event.latitude,
                longitude=payload.longitude if "longitude" in payload.model_fields_set else event.longitude,
                is_location_pinned=payload.is_location_pinned if "is_location_pinned" in payload.model_fields_set else bool(event.is_location_pinned),
            )
        except EventLocationValidationError as exc:
            raise OrganizerEventValidationError(code="invalid_event_location", errors=[{"field": "venue", "message": str(exc)}]) from exc
        event.venue_id = location.venue_id
        event.venue = venue
        event.custom_venue_name = location.custom_venue_name
        event.custom_address_text = location.custom_address_text
        event.latitude = location.latitude
        event.longitude = location.longitude
        event.is_location_pinned = location.is_location_pinned

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
