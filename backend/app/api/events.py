from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.api.ticket_holds import get_current_user_id
from app.db.session import get_db
from app.models.event import Event
from app.models.enums import EventRefundBatchStatus, EventStaffRole
from app.models.enums import EventApprovalStatus, EventStatus, EventVisibility
from app.models.user import User
from app.models.venue import Venue
from app.schemas.event import (
    EventCancelRequest,
    EventDiscoveryDetailResponse,
    EventDiscoveryItemResponse,
    EventPriceSummaryResponse,
    EventRefundBatchResponse,
    EventResponse,
    EventDiscoveryTicketTierResponse,
    EventStaffCreateRequest,
    EventStaffResponse,
    EventStaffUpdateRequest,
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
    EventNotFoundError,
    cancel_event,
    get_event_refund_batch,
    list_event_refund_batches,
)

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
