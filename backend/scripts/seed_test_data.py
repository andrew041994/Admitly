"""Local/dev seed data for Admitly backend.

Usage (from repo root):
  cd backend && python scripts/seed_test_data.py

This script is intended for local/development environments only and is safe to re-run.
It creates missing records for a known seed dataset without deleting unrelated data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, normalize_email
from app.db.session import SessionLocal
from app.models.enums import EventApprovalStatus, EventStatus, EventVisibility
from app.models.event import Event
from app.models.organizer_profile import OrganizerProfile
from app.models.ticket_tier import TicketTier
from app.models.user import User
from app.models.venue import Venue
from app.services.ticket_holds import get_guyana_now

SEED_PASSWORD = "Password123!"

ADMIN_EMAIL = "admin+seed@admitly.local"
ORGANIZER_EMAIL = "organizer+seed@admitly.local"
BUYER_EMAIL = "buyer+seed@admitly.local"

VENUE_NAME = "Georgetown Event Arena"

EVENT_A_TITLE = "Admitly Live: Launch Night"
EVENT_A_SLUG = "admitly-live-launch-night-seed"
EVENT_B_TITLE = "Admitly Live: Closed Sales Demo"
EVENT_B_SLUG = "admitly-live-closed-sales-demo-seed"
EVENT_C_TITLE = "Admitly Live: Past Showcase"
EVENT_C_SLUG = "admitly-live-past-showcase-seed"


@dataclass
class SeedSummary:
    users: list[User]
    organizer_profile: OrganizerProfile
    venue: Venue
    events: list[Event]
    tiers: list[TicketTier]


def get_or_create_user(
    db: Session,
    *,
    email: str,
    full_name: str,
    phone: str,
    is_admin: bool,
) -> User:
    normalized = normalize_email(email)
    user = db.execute(select(User).where(User.email == normalized)).scalar_one_or_none()
    if user is None:
        user = User(
            email=normalized,
            full_name=full_name,
            phone=phone,
            is_admin=is_admin,
            is_active=True,
            is_verified=True,
            auth_provider="local",
            hashed_password=hash_password(SEED_PASSWORD),
        )
        db.add(user)
        db.flush()
        return user

    user.full_name = full_name
    user.phone = phone
    user.is_admin = is_admin
    user.is_active = True
    user.is_verified = True
    user.auth_provider = "local"
    user.hashed_password = hash_password(SEED_PASSWORD)
    db.add(user)
    db.flush()
    return user


def get_or_create_organizer_profile(db: Session, *, organizer_user: User) -> OrganizerProfile:
    profile = db.execute(
        select(OrganizerProfile).where(OrganizerProfile.user_id == organizer_user.id)
    ).scalar_one_or_none()
    if profile is None:
        profile = OrganizerProfile(
            user_id=organizer_user.id,
            business_name="Admitly Test Events",
            display_name="Admitly Test Events",
            description="Local development organizer profile for Admitly manual testing.",
            contact_email=organizer_user.email,
            contact_phone="+592-600-1001",
            is_verified=True,
            is_approved=True,
        )
        db.add(profile)
        db.flush()
        return profile

    profile.business_name = "Admitly Test Events"
    profile.display_name = "Admitly Test Events"
    profile.description = "Local development organizer profile for Admitly manual testing."
    profile.contact_email = organizer_user.email
    profile.contact_phone = "+592-600-1001"
    profile.is_verified = True
    profile.is_approved = True
    db.add(profile)
    db.flush()
    return profile


def get_or_create_venue(db: Session, *, organizer_profile: OrganizerProfile) -> Venue:
    venue = db.execute(
        select(Venue).where(
            Venue.organizer_id == organizer_profile.id,
            Venue.name == VENUE_NAME,
        )
    ).scalar_one_or_none()
    if venue is None:
        venue = Venue(
            organizer_id=organizer_profile.id,
            name=VENUE_NAME,
            description="Primary venue for local Admitly dev seed events.",
            country="Guyana",
            city="Georgetown",
            address_line1="12 Regent Street",
            address_line2="Kingston",
            latitude=Decimal("6.8013000"),
            longitude=Decimal("-58.1553000"),
            capacity=1000,
        )
        db.add(venue)
        db.flush()
        return venue

    venue.description = "Primary venue for local Admitly dev seed events."
    venue.country = "Guyana"
    venue.city = "Georgetown"
    venue.address_line1 = "12 Regent Street"
    venue.address_line2 = "Kingston"
    venue.latitude = Decimal("6.8013000")
    venue.longitude = Decimal("-58.1553000")
    venue.capacity = 1000
    db.add(venue)
    db.flush()
    return venue


def get_or_create_event(
    db: Session,
    *,
    organizer_profile: OrganizerProfile,
    venue: Venue,
    title: str,
    slug: str,
    start_at,
    end_at,
    sales_start_at,
    sales_end_at,
) -> Event:
    event = db.execute(
        select(Event).where(Event.organizer_id == organizer_profile.id, Event.slug == slug)
    ).scalar_one_or_none()
    if event is None:
        event = Event(
            organizer_id=organizer_profile.id,
            venue_id=venue.id,
            title=title,
            slug=slug,
            short_description="Local/dev seeded event for Admitly testing.",
            long_description="This event is seeded for local validation of discovery, purchase, wallet, and QR flows.",
            category="Live Music",
            cover_image_url=None,
            start_at=start_at,
            end_at=end_at,
            doors_open_at=start_at - timedelta(hours=1),
            sales_start_at=sales_start_at,
            sales_end_at=sales_end_at,
            timezone="America/Guyana",
            status=EventStatus.PUBLISHED,
            visibility=EventVisibility.PUBLIC,
            approval_status=EventApprovalStatus.APPROVED,
            published_at=get_guyana_now(),
            is_location_pinned=False,
        )
        db.add(event)
        db.flush()
        return event

    event.venue_id = venue.id
    event.title = title
    event.short_description = "Local/dev seeded event for Admitly testing."
    event.long_description = "This event is seeded for local validation of discovery, purchase, wallet, and QR flows."
    event.category = "Live Music"
    event.start_at = start_at
    event.end_at = end_at
    event.doors_open_at = start_at - timedelta(hours=1)
    event.sales_start_at = sales_start_at
    event.sales_end_at = sales_end_at
    event.timezone = "America/Guyana"
    event.status = EventStatus.PUBLISHED
    event.visibility = EventVisibility.PUBLIC
    event.approval_status = EventApprovalStatus.APPROVED
    event.published_at = event.published_at or get_guyana_now()
    event.cancelled_at = None
    event.cancelled_by_user_id = None
    event.cancellation_reason = None
    db.add(event)
    db.flush()
    return event


def get_or_create_ticket_tier(
    db: Session,
    *,
    event: Event,
    name: str,
    tier_code: str,
    price_amount: Decimal,
    quantity_total: int,
    quantity_sold: int,
    quantity_held: int,
    sales_start_at,
    sales_end_at,
    is_active: bool,
    sort_order: int,
) -> TicketTier:
    tier = db.execute(
        select(TicketTier).where(TicketTier.event_id == event.id, TicketTier.tier_code == tier_code)
    ).scalar_one_or_none()
    if tier is None:
        tier = TicketTier(
            event_id=event.id,
            name=name,
            description=f"{name} - seeded for local/dev testing.",
            tier_code=tier_code,
            price_amount=price_amount,
            currency="GYD",
            quantity_total=quantity_total,
            quantity_sold=quantity_sold,
            quantity_held=quantity_held,
            min_per_order=1,
            max_per_order=6,
            sales_start_at=sales_start_at,
            sales_end_at=sales_end_at,
            is_active=is_active,
            sort_order=sort_order,
        )
        db.add(tier)
        db.flush()
        return tier

    tier.name = name
    tier.description = f"{name} - seeded for local/dev testing."
    tier.price_amount = price_amount
    tier.currency = "GYD"
    tier.quantity_total = quantity_total
    tier.quantity_sold = quantity_sold
    tier.quantity_held = quantity_held
    tier.min_per_order = 1
    tier.max_per_order = 6
    tier.sales_start_at = sales_start_at
    tier.sales_end_at = sales_end_at
    tier.is_active = is_active
    tier.sort_order = sort_order
    db.add(tier)
    db.flush()
    return tier


def seed() -> SeedSummary:
    now = get_guyana_now()

    with SessionLocal() as db:
        admin_user = get_or_create_user(
            db,
            email=ADMIN_EMAIL,
            full_name="Admitly Seed Admin",
            phone="+592-600-2001",
            is_admin=True,
        )
        organizer_user = get_or_create_user(
            db,
            email=ORGANIZER_EMAIL,
            full_name="Admitly Seed Organizer",
            phone="+592-600-2002",
            is_admin=False,
        )
        buyer_user = get_or_create_user(
            db,
            email=BUYER_EMAIL,
            full_name="Admitly Seed Buyer",
            phone="+592-600-2003",
            is_admin=False,
        )

        organizer_profile = get_or_create_organizer_profile(db, organizer_user=organizer_user)
        venue = get_or_create_venue(db, organizer_profile=organizer_profile)

        event_a = get_or_create_event(
            db,
            organizer_profile=organizer_profile,
            venue=venue,
            title=EVENT_A_TITLE,
            slug=EVENT_A_SLUG,
            start_at=now + timedelta(days=14),
            end_at=now + timedelta(days=14, hours=4),
            sales_start_at=now - timedelta(days=2),
            sales_end_at=now + timedelta(days=13),
        )
        event_b = get_or_create_event(
            db,
            organizer_profile=organizer_profile,
            venue=venue,
            title=EVENT_B_TITLE,
            slug=EVENT_B_SLUG,
            start_at=now + timedelta(days=21),
            end_at=now + timedelta(days=21, hours=3),
            sales_start_at=now - timedelta(days=1),
            sales_end_at=now + timedelta(days=20),
        )
        event_c = get_or_create_event(
            db,
            organizer_profile=organizer_profile,
            venue=venue,
            title=EVENT_C_TITLE,
            slug=EVENT_C_SLUG,
            start_at=now - timedelta(days=10),
            end_at=now - timedelta(days=10, hours=-3),
            sales_start_at=now - timedelta(days=30),
            sales_end_at=now - timedelta(days=11),
        )

        tiers: list[TicketTier] = [
            get_or_create_ticket_tier(
                db,
                event=event_a,
                name="General Admission",
                tier_code="GA",
                price_amount=Decimal("3500.00"),
                quantity_total=250,
                quantity_sold=18,
                quantity_held=4,
                sales_start_at=event_a.sales_start_at,
                sales_end_at=event_a.sales_end_at,
                is_active=True,
                sort_order=1,
            ),
            get_or_create_ticket_tier(
                db,
                event=event_a,
                name="VIP",
                tier_code="VIP",
                price_amount=Decimal("9500.00"),
                quantity_total=80,
                quantity_sold=6,
                quantity_held=1,
                sales_start_at=event_a.sales_start_at,
                sales_end_at=event_a.sales_end_at,
                is_active=True,
                sort_order=2,
            ),
            get_or_create_ticket_tier(
                db,
                event=event_b,
                name="General Admission",
                tier_code="GA_CLOSED",
                price_amount=Decimal("4000.00"),
                quantity_total=120,
                quantity_sold=0,
                quantity_held=0,
                sales_start_at=event_b.sales_start_at,
                sales_end_at=event_b.sales_end_at,
                is_active=False,
                sort_order=1,
            ),
            get_or_create_ticket_tier(
                db,
                event=event_c,
                name="Archive Pass",
                tier_code="ARCHIVE",
                price_amount=Decimal("2500.00"),
                quantity_total=90,
                quantity_sold=57,
                quantity_held=0,
                sales_start_at=event_c.sales_start_at,
                sales_end_at=event_c.sales_end_at,
                is_active=True,
                sort_order=1,
            ),
        ]

        db.commit()

        return SeedSummary(
            users=[admin_user, organizer_user, buyer_user],
            organizer_profile=organizer_profile,
            venue=venue,
            events=[event_a, event_b, event_c],
            tiers=tiers,
        )


def print_summary(summary: SeedSummary) -> None:
    print("\n✅ Admitly local/dev seed data ready")
    print(f"Test password (all seeded users): {SEED_PASSWORD}")
    print("\nUsers:")
    for user in summary.users:
        role = "admin" if user.is_admin else "standard"
        print(f"  - {user.email} (id={user.id}, role={role})")

    print("\nOrganizer / Venue:")
    print(f"  - organizer_profile_id={summary.organizer_profile.id}")
    print(f"  - venue_id={summary.venue.id} ({summary.venue.name})")

    print("\nEvents:")
    for event in summary.events:
        print(f"  - id={event.id} | {event.title} | slug={event.slug}")

    print("\nTicket tiers:")
    for tier in summary.tiers:
        print(f"  - id={tier.id} | event_id={tier.event_id} | {tier.name} ({tier.tier_code})")

    print("\nSuggested frontend paths:")
    for event in summary.events:
        print(f"  - /events/{event.id}")


if __name__ == "__main__":
    print_summary(seed())
