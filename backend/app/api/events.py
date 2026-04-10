from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.api.ticket_holds import get_current_user_id
from app.db.session import get_db
from app.models.event import Event
from app.models.event_staff import EventStaff
from app.models.enums import EventRefundBatchStatus, EventStaffRole
from app.models.enums import EventApprovalStatus, EventStatus, EventVisibility
from app.models.order import Order
from app.models.organizer_profile import OrganizerProfile
from app.models.ticket import Ticket
from app.models.ticket_tier import TicketTier
from app.models.user import User
from app.models.venue import Venue
from app.schemas.event import (
    EventCancelRequest,
    EventCreateRequest,
    EventCreateResponse,
    EventCreateTicketTierResponse,
    EventDashboardCheckInRow,
    EventDashboardResponse,
    EventDashboardTierResponse,
    EventDiscoveryDetailResponse,
    EventDiscoveryItemResponse,
    EventPriceSummaryResponse,
    EventRefundBatchResponse,
    EventResponse,
    EventDiscoveryTicketTierResponse,
    MyEventItemResponse,
    EventStaffCreateRequest,
    EventStaffResponse,
    EventStaffUpdateRequest,
    OrganizerEventDashboardItemResponse,
    OrganizerEventDetailResponse,
    OrganizerEventUpdateRequest,
)
from app.services.event_permissions import EventPermissionDeniedError, EventPermissionNotFoundError
from app.services.event_staff import (
    EventStaffConflictError,
    EventStaffNotFoundError,
    EventStaffValidationError,
    add_event_staff,
    list_event_staff,
    remove_event_staff,
    update_event_staff_role,
)
from app.services.ticket_holds import get_ticket_tier_capacity_summary
from app.services.events import (
    EventAuthorizationError,
    EventCancellationError,
    EventCreationValidationError,
    EventNotFoundError,
    cancel_event,
    create_event_with_ticket_tiers,
    get_event_refund_batch,
    list_event_refund_batches,
)
from app.services.organizer_events import (
    OrganizerEventAuthorizationError,
    OrganizerEventNotFoundError,
    OrganizerEventValidationError,
    calculate_event_metrics,
    get_owned_event,
    publish_event,
    unpublish_event,
    update_event_and_tiers,
)
from app.services.reporting import get_event_reporting_summary, get_event_tier_summary

router = APIRouter(prefix="/events", tags=["events"])


def _discoverable_event_query() -> select:
    return (
        select(Event)
        .options(joinedload(Event.venue), joinedload(Event.organizer), joinedload(Event.ticket_tiers))
        .where(
            Event.status == EventStatus.PUBLISHED,
            Event.visibility == EventVisibility.PUBLIC,
            Event.approval_status == EventApprovalStatus.APPROVED,
            Event.published_at.is_not(None),
        )
    )


def _to_price_summary(event: Event) -> EventPriceSummaryResponse | None:
    active_tiers = [tier for tier in event.ticket_tiers if tier.is_active]
    if not active_tiers:
        return None
    min_tier = min(active_tiers, key=lambda tier: tier.price_amount)
    min_price = str(min_tier.price_amount)
    return EventPriceSummaryResponse(
        currency=min_tier.currency,
        min_price=min_price,
        is_free=float(min_tier.price_amount) <= 0,
    )


def _to_discovery_item(event: Event) -> EventDiscoveryItemResponse:
    return EventDiscoveryItemResponse(
        id=event.id,
        title=event.title,
        short_description=event.short_description,
        category=event.category,
        cover_image_url=event.cover_image_url,
        start_at=event.start_at,
        end_at=event.end_at,
        venue_name=event.venue.name if event.venue else None,
        venue_city=event.venue.city if event.venue else None,
        venue_country=event.venue.country if event.venue else None,
        custom_venue_name=event.custom_venue_name,
        custom_address_text=event.custom_address_text,
        organizer_name=event.organizer.display_name if event.organizer else None,
        price_summary=_to_price_summary(event),
    )


def _to_discovery_detail(event: Event, db: Session) -> EventDiscoveryDetailResponse:
    item = _to_discovery_item(event)
    tiers = []
    for tier in sorted(event.ticket_tiers, key=lambda t: (t.sort_order, t.id)):
        capacity = get_ticket_tier_capacity_summary(db, ticket_tier_id=tier.id)
        tiers.append(EventDiscoveryTicketTierResponse(
            id=tier.id,
            name=tier.name,
            description=tier.description,
            price_amount=str(tier.price_amount),
            currency=tier.currency,
            min_per_order=tier.min_per_order,
            max_per_order=tier.max_per_order,
            available_quantity=capacity.available_quantity,
            is_active=tier.is_active,
        ))
    return EventDiscoveryDetailResponse(**item.model_dump(), long_description=event.long_description, ticket_tiers=tiers)


def _require_admin(db: Session, *, user_id: int) -> None:
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None or not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")


def _to_batch_response(batch) -> EventRefundBatchResponse:  # noqa: ANN001
    return EventRefundBatchResponse(
        id=batch.id,
        event_id=batch.event_id,
        status=batch.status.value,
        total_orders=batch.total_orders,
        processed_orders=batch.processed_orders,
        successful_refunds=batch.successful_refunds,
        skipped_orders=batch.skipped_orders,
        failed_orders=batch.failed_orders,
        started_at=batch.started_at,
        completed_at=batch.completed_at,
        created_at=batch.created_at,
        last_error=batch.last_error,
    )


def _ensure_organizer_profile(db: Session, *, user_id: int) -> OrganizerProfile:
    profile = db.execute(select(OrganizerProfile).where(OrganizerProfile.user_id == user_id)).scalar_one_or_none()
    if profile is not None:
        return profile
    user = db.execute(select(User).where(User.id == user_id)).scalar_one()
    profile = OrganizerProfile(
        user_id=user_id,
        business_name=user.full_name,
        display_name=user.full_name,
        contact_email=user.email,
        contact_phone=user.phone,
    )
    db.add(profile)
    db.flush()
    return profile


def _is_event_owner(db: Session, *, event: Event, user_id: int) -> bool:
    organizer_user_id = db.execute(
        select(OrganizerProfile.user_id).where(OrganizerProfile.id == event.organizer_id)
    ).scalar_one_or_none()
    return organizer_user_id == user_id


def _is_effective_staff_active(staff: EventStaff, *, event: Event | None = None) -> bool:
    source_event = event or staff.event
    if source_event is None:
        return False
    now = datetime.now(UTC)
    return bool(
        staff.is_active
        and source_event.end_at > now
        and source_event.status != EventStatus.CANCELLED
        and source_event.cancelled_at is None
    )


@router.post("/{event_id}/cancel", response_model=EventResponse)
def cancel_existing_event(
    event_id: int,
    payload: EventCancelRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> EventResponse:
    try:
        event, batch = cancel_event(
            db,
            event_id=event_id,
            actor_user_id=user_id,
            reason=payload.reason,
        )
        db.commit()
    except EventNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EventAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except EventCancellationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return EventResponse(
        id=event.id,
        organizer_id=event.organizer_id,
        status=event.status.value,
        cancelled_at=event.cancelled_at,
        cancelled_by_user_id=event.cancelled_by_user_id,
        cancellation_reason=event.cancellation_reason,
        updated_at=event.updated_at,
        refund_batch_id=batch.id,
        refund_batch_status=batch.status.value,
    )


@router.get("/discover", response_model=list[EventDiscoveryItemResponse])
def discover_events(
    q: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None, max_length=100),
    city: str | None = Query(default=None, max_length=120),
    date_bucket: str | None = Query(default=None, pattern="^(today|this_week|upcoming)$"),
    is_free: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    _user_id: int = Depends(get_current_user_id),
) -> list[EventDiscoveryItemResponse]:
    query = _discoverable_event_query()

    if q:
        like_q = f"%{q.strip()}%"
        query = query.where(
            or_(
                Event.title.ilike(like_q),
                Event.short_description.ilike(like_q),
                Event.long_description.ilike(like_q),
                Event.category.ilike(like_q),
            )
        )

    if category:
        query = query.where(func.lower(Event.category) == category.strip().lower())

    if city:
        query = query.join(Venue, Venue.id == Event.venue_id).where(func.lower(Venue.city) == city.strip().lower())

    now_expr = func.now()
    if date_bucket == "today":
        query = query.where(func.date(Event.start_at) == func.current_date())
    elif date_bucket == "this_week":
        query = query.where(
            and_(
                Event.start_at >= now_expr,
                Event.start_at < now_expr + func.make_interval(days=7),
            )
        )
    else:
        query = query.where(Event.start_at >= now_expr)

    events = db.execute(query.order_by(Event.start_at.asc()).limit(100)).scalars().unique().all()

    if is_free is not None:
        filtered: list[Event] = []
        for event in events:
            summary = _to_price_summary(event)
            if summary is None:
                if is_free:
                    filtered.append(event)
                continue
            if summary.is_free == is_free:
                filtered.append(event)
        events = filtered

    return [_to_discovery_item(event) for event in events]


@router.get("/discover/{event_id}", response_model=EventDiscoveryDetailResponse)
def discover_event_detail(
    event_id: int,
    db: Session = Depends(get_db),
    _user_id: int = Depends(get_current_user_id),
) -> EventDiscoveryDetailResponse:
    event = (
        db.execute(_discoverable_event_query().where(Event.id == event_id))
        .scalars()
        .unique()
        .one_or_none()
    )
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    return _to_discovery_detail(event, db)




def _to_event_staff_response(staff) -> EventStaffResponse:  # noqa: ANN001
    return EventStaffResponse(
        id=staff.id,
        event_id=staff.event_id,
        user_id=staff.user_id,
        role=staff.role.value,
        created_at=staff.created_at,
        invited_by_user_id=staff.invited_by_user_id,
        is_active=staff.is_active,
        is_effective_active=_is_effective_staff_active(staff),
    )


@router.post("", response_model=EventCreateResponse, status_code=status.HTTP_201_CREATED)
def create_event(
    payload: EventCreateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> EventCreateResponse:
    if payload.venue_id is not None:
        venue = db.execute(select(Venue).where(Venue.id == payload.venue_id)).scalar_one_or_none()
        if venue is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found.")
    organizer_profile = _ensure_organizer_profile(db, user_id=user_id)
    try:
        event, tiers = create_event_with_ticket_tiers(db, organizer_profile=organizer_profile, payload=payload)
        db.commit()
    except EventCreationValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    db.refresh(event)
    for tier in tiers:
        db.refresh(tier)
    return EventCreateResponse(
        id=event.id,
        organizer_id=event.organizer_id,
        title=event.title,
        slug=event.slug,
        status=event.status.value,
        visibility=event.visibility.value,
        approval_status=event.approval_status.value,
        start_at=event.start_at,
        end_at=event.end_at,
        doors_open_at=event.doors_open_at,
        sales_start_at=event.sales_start_at,
        sales_end_at=event.sales_end_at,
        timezone=event.timezone,
        venue_id=event.venue_id,
        custom_venue_name=event.custom_venue_name,
        custom_address_text=event.custom_address_text,
        refund_policy_text=event.refund_policy_text,
        terms_text=event.terms_text,
        latitude=str(event.latitude) if event.latitude is not None else None,
        longitude=str(event.longitude) if event.longitude is not None else None,
        is_location_pinned=bool(event.is_location_pinned),
        published_at=event.published_at,
        created_at=event.created_at,
        ticket_tiers=[
            EventCreateTicketTierResponse(
                id=tier.id,
                event_id=tier.event_id,
                name=tier.name,
                description=tier.description,
                tier_code=tier.tier_code,
                price_amount=str(Decimal(tier.price_amount)),
                currency=tier.currency,
                quantity_total=tier.quantity_total,
                min_per_order=tier.min_per_order,
                max_per_order=tier.max_per_order,
                is_active=bool(tier.is_active),
                sort_order=tier.sort_order,
            )
            for tier in tiers
        ],
    )


def _to_my_event_item(event: Event) -> MyEventItemResponse:
    now = datetime.now(UTC)
    is_ended = event.end_at <= now or event.status == EventStatus.CANCELLED
    is_upcoming = event.start_at > now and not is_ended
    is_active = not is_ended
    return MyEventItemResponse(
        id=event.id,
        title=event.title,
        start_at=event.start_at,
        end_at=event.end_at,
        timezone=event.timezone,
        status=event.status.value,
        visibility=event.visibility.value,
        venue_name=event.venue.name if event.venue else None,
        venue_city=event.venue.city if event.venue else None,
        custom_venue_name=event.custom_venue_name,
        is_active=is_active,
        is_upcoming=is_upcoming,
        is_ended=is_ended,
    )


def _to_organizer_event_detail(event: Event) -> OrganizerEventDetailResponse:
    return OrganizerEventDetailResponse(
        id=event.id,
        title=event.title,
        short_description=event.short_description,
        long_description=event.long_description,
        category=event.category,
        cover_image_url=event.cover_image_url,
        start_at=event.start_at,
        end_at=event.end_at,
        doors_open_at=event.doors_open_at,
        sales_start_at=event.sales_start_at,
        sales_end_at=event.sales_end_at,
        timezone=event.timezone,
        visibility=event.visibility.value,
        status=event.status.value,
        custom_venue_name=event.custom_venue_name,
        custom_address_text=event.custom_address_text,
        ticket_tiers=[
            EventCreateTicketTierResponse(
                id=tier.id,
                event_id=tier.event_id,
                name=tier.name,
                description=tier.description,
                tier_code=tier.tier_code,
                price_amount=str(Decimal(tier.price_amount)),
                currency=tier.currency,
                quantity_total=tier.quantity_total,
                min_per_order=tier.min_per_order,
                max_per_order=tier.max_per_order,
                is_active=bool(tier.is_active),
                sort_order=tier.sort_order,
            )
            for tier in sorted(event.ticket_tiers, key=lambda t: (t.sort_order, t.id))
        ],
    )


def _list_events_for_organizer(db: Session, *, user_id: int, active_only: bool) -> list[Event]:
    now = datetime.now(UTC)
    query = (
        select(Event)
        .join(OrganizerProfile, OrganizerProfile.id == Event.organizer_id)
        .options(joinedload(Event.venue), joinedload(Event.ticket_tiers))
        .where(OrganizerProfile.user_id == user_id)
    )
    if active_only:
        query = query.where(
            Event.status != EventStatus.CANCELLED,
            Event.end_at > now,
        )
    return db.execute(query.order_by(Event.start_at.asc())).scalars().all()


@router.get("/mine", response_model=list[MyEventItemResponse])
def get_my_events(
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[MyEventItemResponse]:
    events = _list_events_for_organizer(db, user_id=user_id, active_only=active_only)
    return [_to_my_event_item(event) for event in events]


@router.get("/organizer/events", response_model=list[OrganizerEventDashboardItemResponse])
def get_organizer_events(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[OrganizerEventDashboardItemResponse]:
    events = _list_events_for_organizer(db, user_id=user_id, active_only=False)
    rows: list[OrganizerEventDashboardItemResponse] = []
    for event in sorted(events, key=lambda ev: ev.created_at, reverse=True):
        metrics = calculate_event_metrics(db, event_id=event.id)
        tiers = list(event.ticket_tiers)
        rows.append(
            OrganizerEventDashboardItemResponse(
                id=event.id,
                title=event.title,
                cover_image_url=event.cover_image_url,
                venue_name=event.venue.name if event.venue else event.custom_venue_name,
                city=event.venue.city if event.venue else None,
                start_at=event.start_at,
                end_at=event.end_at,
                status=event.status.value,
                total_ticket_types=len(tiers),
                total_quantity=sum(int(t.quantity_total) for t in tiers),
                sold_count=metrics.sold_count,
                gross_revenue=float(metrics.gross_revenue),
                created_at=event.created_at,
                updated_at=event.updated_at,
            )
        )
    return rows


@router.get("/organizer/events/{event_id}", response_model=OrganizerEventDetailResponse)
def get_organizer_event(
    event_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> OrganizerEventDetailResponse:
    try:
        event = get_owned_event(db, actor_user_id=user_id, event_id=event_id)
    except OrganizerEventNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OrganizerEventAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return _to_organizer_event_detail(event)


@router.patch("/organizer/events/{event_id}", response_model=OrganizerEventDetailResponse)
def patch_organizer_event(
    event_id: int,
    payload: OrganizerEventUpdateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> OrganizerEventDetailResponse:
    try:
        event = update_event_and_tiers(db, actor_user_id=user_id, event_id=event_id, payload=payload)
        db.commit()
    except OrganizerEventNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OrganizerEventAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except OrganizerEventValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code, "errors": exc.errors}) from exc
    return _to_organizer_event_detail(event)


@router.post("/organizer/events/{event_id}/publish", response_model=OrganizerEventDetailResponse)
def publish_organizer_event(
    event_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> OrganizerEventDetailResponse:
    try:
        event = publish_event(db, actor_user_id=user_id, event_id=event_id)
        db.commit()
    except OrganizerEventNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OrganizerEventAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except OrganizerEventValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code, "errors": exc.errors}) from exc
    return _to_organizer_event_detail(event)


@router.post("/organizer/events/{event_id}/unpublish", response_model=OrganizerEventDetailResponse)
def unpublish_organizer_event(
    event_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> OrganizerEventDetailResponse:
    try:
        event = unpublish_event(db, actor_user_id=user_id, event_id=event_id)
        db.commit()
    except OrganizerEventNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OrganizerEventAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except OrganizerEventValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code, "errors": exc.errors}) from exc
    return _to_organizer_event_detail(event)


@router.post("/organizer/events/{event_id}/cancel", response_model=OrganizerEventDetailResponse)
def cancel_organizer_event(
    event_id: int,
    payload: EventCancelRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> OrganizerEventDetailResponse:
    cancel_existing_event(event_id=event_id, payload=payload, db=db, user_id=user_id)
    event = get_owned_event(db, actor_user_id=user_id, event_id=event_id)
    return _to_organizer_event_detail(event)


@router.get("/mine/active", response_model=list[MyEventItemResponse])
def get_my_active_events(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[MyEventItemResponse]:
    events = _list_events_for_organizer(db, user_id=user_id, active_only=True)
    return [_to_my_event_item(event) for event in events]


@router.get("/{event_id}/dashboard", response_model=EventDashboardResponse)
def get_event_dashboard(
    event_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> EventDashboardResponse:
    event = db.execute(select(Event).where(Event.id == event_id)).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    if not _is_event_owner(db, event=event, user_id=user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only organizer can view dashboard.")

    summary = get_event_reporting_summary(db, event_id=event_id)
    tier_rows = get_event_tier_summary(db, event_id=event_id)
    refunded_count = db.execute(
        select(func.count(Order.id)).where(Order.event_id == event_id, Order.refund_status == "refunded")
    ).scalar_one()
    transfer_count = db.execute(select(func.coalesce(func.sum(Ticket.transfer_count), 0)).where(Ticket.event_id == event_id)).scalar_one()
    event_operational = event.end_at > datetime.now(UTC) and event.status != EventStatus.CANCELLED and event.cancelled_at is None
    active_staff = (
        db.execute(
            select(func.count(EventStaff.id)).where(
                EventStaff.event_id == event_id,
                EventStaff.is_active.is_(True),
            )
        ).scalar_one()
        if event_operational
        else 0
    )
    recent_rows = db.execute(
        select(Ticket.id, Ticket.checked_in_at, Ticket.checked_in_by_user_id)
        .where(Ticket.event_id == event_id, Ticket.checked_in_at.is_not(None))
        .order_by(Ticket.checked_in_at.desc())
        .limit(10)
    ).all()

    return EventDashboardResponse(
        event_id=event_id,
        tickets_sold=summary.tickets_sold_count,
        gross_revenue=float(summary.gross_revenue),
        attendees_admitted=summary.tickets_checked_in_count,
        attendees_remaining=summary.tickets_remaining_count,
        total_ticket_capacity=summary.total_capacity,
        transfer_count=int(transfer_count or 0),
        voided_ticket_count=summary.tickets_voided_count,
        refunded_ticket_count=int(refunded_count or 0),
        live_checkin_percentage=summary.check_in_rate,
        active_staff_assigned=int(active_staff or 0),
        tier_metrics=[
            EventDashboardTierResponse(
                ticket_tier_id=row.ticket_tier_id,
                name=row.name,
                sold_count=row.sold_count,
                remaining_count=row.remaining_count,
                gross_revenue=float(row.gross_revenue),
                currency=row.currency,
            )
            for row in tier_rows
        ],
        recent_checkins=[
            EventDashboardCheckInRow(
                ticket_id=int(row[0]),
                checked_in_at=row[1],
                checked_in_by_user_id=row[2],
            )
            for row in recent_rows
        ],
    )


@router.get("/{event_id}/staff", response_model=list[EventStaffResponse])
def get_event_staff_assignments(
    event_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[EventStaffResponse]:
    try:
        staff = list_event_staff(db, actor_user_id=user_id, event_id=event_id)
    except EventPermissionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EventPermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return [_to_event_staff_response(row) for row in staff]


@router.post("/{event_id}/staff", response_model=EventStaffResponse, status_code=status.HTTP_201_CREATED)
def create_event_staff_assignment(
    event_id: int,
    payload: EventStaffCreateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> EventStaffResponse:
    try:
        role = EventStaffRole(payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid role.") from exc

    try:
        staff = add_event_staff(db, actor_user_id=user_id, event_id=event_id, user_id=payload.user_id, role=role)
        db.commit()
    except EventPermissionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EventPermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except EventStaffConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except EventStaffValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _to_event_staff_response(staff)


@router.patch("/{event_id}/staff/{staff_id}", response_model=EventStaffResponse)
def patch_event_staff_assignment(
    event_id: int,
    staff_id: int,
    payload: EventStaffUpdateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> EventStaffResponse:
    try:
        role = EventStaffRole(payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid role.") from exc

    try:
        staff = update_event_staff_role(
            db,
            actor_user_id=user_id,
            event_id=event_id,
            staff_id=staff_id,
            role=role,
        )
        db.commit()
    except EventPermissionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EventPermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except EventStaffNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EventStaffValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _to_event_staff_response(staff)


@router.delete("/{event_id}/staff/{staff_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event_staff_assignment(
    event_id: int,
    staff_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> None:
    try:
        remove_event_staff(db, actor_user_id=user_id, event_id=event_id, staff_id=staff_id)
        db.commit()
    except EventPermissionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EventPermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except EventStaffNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/admin/event-refund-batches", response_model=list[EventRefundBatchResponse])
def admin_list_event_refund_batches(
    status_filter: str | None = Query(default=None, alias="status"),
    event_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[EventRefundBatchResponse]:
    _require_admin(db, user_id=user_id)
    parsed_status = None
    if status_filter is not None:
        try:
            parsed_status = EventRefundBatchStatus(status_filter)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid batch status.") from exc
    batches = list_event_refund_batches(db, status=parsed_status, event_id=event_id)
    return [_to_batch_response(batch) for batch in batches]


@router.get("/admin/event-refund-batches/{batch_id}", response_model=EventRefundBatchResponse)
def admin_get_event_refund_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> EventRefundBatchResponse:
    _require_admin(db, user_id=user_id)
    batch = get_event_refund_batch(db, batch_id=batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refund batch not found.")
    return _to_batch_response(batch)
