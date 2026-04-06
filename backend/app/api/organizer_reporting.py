from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.ticket_holds import get_current_user_id
from app.db.session import get_db
from app.models.enums import OrderStatus, TicketStatus
from app.schemas.reporting import (
    OrganizerCheckInRowResponse,
    OrganizerCheckInSummaryResponse,
    OrganizerEventSummaryResponse,
    OrganizerOrderRowResponse,
    OrganizerTicketRowResponse,
    OrganizerTierSummaryRowResponse,
)
from app.services.reporting import (
    EventReportingAuthorizationError,
    EventReportingNotFoundError,
    get_event_checkin_summary,
    get_event_reporting_summary,
    get_event_tier_summary,
    list_event_checkins,
    list_event_orders_for_organizer,
    list_event_tickets_for_organizer,
    validate_event_reporting_access,
)

router = APIRouter(prefix="/organizer/events", tags=["organizer-reporting"])


def _authorize(db: Session, *, user_id: int, event_id: int) -> None:
    try:
        validate_event_reporting_access(db, user_id=user_id, event_id=event_id)
    except EventReportingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EventReportingAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/{event_id}/summary", response_model=OrganizerEventSummaryResponse)
def get_organizer_event_summary(
    event_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> OrganizerEventSummaryResponse:
    _authorize(db, user_id=user_id, event_id=event_id)
    summary = get_event_reporting_summary(db, event_id=event_id)
    return OrganizerEventSummaryResponse(
        event_id=summary.event_id,
        event_title=summary.event_title,
        event_status=summary.event_status,
        starts_at=summary.starts_at,
        ends_at=summary.ends_at,
        gross_revenue=float(summary.gross_revenue),
        refunded_amount=float(summary.refunded_amount),
        net_revenue=float(summary.net_revenue),
        completed_order_count=summary.completed_order_count,
        pending_order_count=summary.pending_order_count,
        cancelled_order_count=summary.cancelled_order_count,
        refunded_order_count=summary.refunded_order_count,
        tickets_sold_count=summary.tickets_sold_count,
        tickets_issued_count=summary.tickets_issued_count,
        tickets_checked_in_count=summary.tickets_checked_in_count,
        tickets_voided_count=summary.tickets_voided_count,
        tickets_remaining_count=summary.tickets_remaining_count,
        check_in_rate=summary.check_in_rate,
        total_capacity=summary.total_capacity,
        generated_at=summary.generated_at,
    )


@router.get("/{event_id}/tiers", response_model=list[OrganizerTierSummaryRowResponse])
def get_organizer_tier_summary(
    event_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[OrganizerTierSummaryRowResponse]:
    _authorize(db, user_id=user_id, event_id=event_id)
    tiers = get_event_tier_summary(db, event_id=event_id)
    return [
        OrganizerTierSummaryRowResponse(
            ticket_tier_id=t.ticket_tier_id,
            name=t.name,
            price=float(t.price),
            currency=t.currency,
            configured_quantity=t.configured_quantity,
            sold_count=t.sold_count,
            active_hold_count=t.active_hold_count,
            issued_count=t.issued_count,
            checked_in_count=t.checked_in_count,
            voided_count=t.voided_count,
            remaining_count=t.remaining_count,
            gross_revenue=float(t.gross_revenue),
        )
        for t in tiers
    ]


@router.get("/{event_id}/orders", response_model=list[OrganizerOrderRowResponse])
def get_organizer_event_orders(
    event_id: int,
    status_filter: OrderStatus | None = Query(default=None, alias="status"),
    refund_status: str | None = Query(default=None),
    created_after: datetime | None = Query(default=None),
    created_before: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[OrganizerOrderRowResponse]:
    _authorize(db, user_id=user_id, event_id=event_id)
    orders = list_event_orders_for_organizer(
        db,
        event_id=event_id,
        status=status_filter,
        refund_status=refund_status,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
        offset=offset,
    )
    return [
        OrganizerOrderRowResponse(
            order_id=o.order_id,
            user_id=o.user_id,
            status=o.status,
            refund_status=o.refund_status,
            payment_provider=o.payment_provider,
            payment_method=o.payment_method,
            total_amount=float(o.total_amount),
            currency=o.currency,
            item_count=o.item_count,
            created_at=o.created_at,
            updated_at=o.updated_at,
            cancelled_at=o.cancelled_at,
            refunded_at=o.refunded_at,
        )
        for o in orders
    ]


@router.get("/{event_id}/tickets", response_model=list[OrganizerTicketRowResponse])
def get_organizer_event_tickets(
    event_id: int,
    status_filter: TicketStatus | None = Query(default=None, alias="status"),
    owner_user_id: int | None = Query(default=None),
    purchaser_user_id: int | None = Query(default=None),
    ticket_tier_id: int | None = Query(default=None),
    checked_in: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[OrganizerTicketRowResponse]:
    _authorize(db, user_id=user_id, event_id=event_id)
    tickets = list_event_tickets_for_organizer(
        db,
        event_id=event_id,
        status=status_filter,
        owner_user_id=owner_user_id,
        purchaser_user_id=purchaser_user_id,
        ticket_tier_id=ticket_tier_id,
        checked_in=checked_in,
        limit=limit,
        offset=offset,
    )
    return [
        OrganizerTicketRowResponse(
            ticket_id=t.ticket_id,
            order_id=t.order_id,
            order_item_id=t.order_item_id,
            ticket_tier_id=t.ticket_tier_id,
            purchaser_user_id=t.purchaser_user_id,
            owner_user_id=t.owner_user_id,
            status=t.status,
            transfer_count=t.transfer_count,
            ticket_code=t.ticket_code,
            issued_at=t.issued_at,
            checked_in_at=t.checked_in_at,
            checked_in_by_user_id=t.checked_in_by_user_id,
            voided_at=t.voided_at,
        )
        for t in tickets
    ]


@router.get("/{event_id}/checkins/summary", response_model=OrganizerCheckInSummaryResponse)
def get_organizer_checkin_summary(
    event_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> OrganizerCheckInSummaryResponse:
    _authorize(db, user_id=user_id, event_id=event_id)
    summary = get_event_checkin_summary(db, event_id=event_id)
    return OrganizerCheckInSummaryResponse(
        event_id=summary.event_id,
        total_checked_in=summary.total_checked_in,
        total_not_checked_in=summary.total_not_checked_in,
        first_check_in_at=summary.first_check_in_at,
        last_check_in_at=summary.last_check_in_at,
        check_in_rate=summary.check_in_rate,
    )


@router.get("/{event_id}/checkins", response_model=list[OrganizerCheckInRowResponse])
def get_organizer_checkins(
    event_id: int,
    checked_in_by_user_id: int | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[OrganizerCheckInRowResponse]:
    _authorize(db, user_id=user_id, event_id=event_id)
    checkins = list_event_checkins(
        db,
        event_id=event_id,
        checked_in_by_user_id=checked_in_by_user_id,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return [
        OrganizerCheckInRowResponse(
            ticket_id=c.ticket_id,
            ticket_tier_id=c.ticket_tier_id,
            checked_in_at=c.checked_in_at,
            checked_in_by_user_id=c.checked_in_by_user_id,
            purchaser_user_id=c.purchaser_user_id,
            owner_user_id=c.owner_user_id,
            order_id=c.order_id,
        )
        for c in checkins
    ]
