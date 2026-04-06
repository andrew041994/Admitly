from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.ticket_holds import get_current_user_id
from app.db.session import get_db
from app.schemas.ticket import TicketCheckInRequest, TicketCheckInResponse, TicketResponse, TicketTransferRequest
from app.services.tickets import (
    TicketAuthorizationError,
    TicketCheckInConflictError,
    TicketCrossEventError,
    TicketNotFoundError,
    TicketTransferError,
    check_in_ticket_for_event,
    list_tickets_for_order_owner,
    list_tickets_for_user,
    transfer_ticket_to_user,
)

router = APIRouter(tags=["tickets"])


def _to_ticket_response(ticket) -> TicketResponse:
    return TicketResponse(
        id=ticket.id,
        event_id=ticket.event_id,
        order_id=ticket.order_id,
        order_item_id=ticket.order_item_id,
        purchaser_user_id=ticket.purchaser_user_id,
        owner_user_id=ticket.owner_user_id,
        ticket_tier_id=ticket.ticket_tier_id,
        status=ticket.status.value,
        ticket_code=ticket.ticket_code,
        qr_payload=ticket.qr_payload,
        issued_at=ticket.issued_at,
        checked_in_at=ticket.checked_in_at,
        transferred_at=ticket.transferred_at,
        transfer_count=ticket.transfer_count,
    )


@router.get("/me/tickets", response_model=list[TicketResponse])
def get_my_tickets(
    event_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[TicketResponse]:
    tickets = list_tickets_for_user(db, user_id=user_id, event_id=event_id)
    return [_to_ticket_response(t) for t in tickets]


@router.get("/orders/{order_id}/tickets", response_model=list[TicketResponse])
def get_order_tickets(
    order_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[TicketResponse]:
    try:
        tickets = list_tickets_for_order_owner(db, order_id=order_id, user_id=user_id)
    except TicketAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return [_to_ticket_response(t) for t in tickets]


@router.post("/tickets/{ticket_id}/transfer", response_model=TicketResponse)
def transfer_ticket(
    ticket_id: int,
    payload: TicketTransferRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> TicketResponse:
    try:
        ticket = transfer_ticket_to_user(
            db,
            ticket_id=ticket_id,
            from_user_id=user_id,
            to_user_id=payload.to_user_id,
        )
    except TicketAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TicketTransferError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _to_ticket_response(ticket)


@router.post("/events/{event_id}/tickets/check-in", response_model=TicketCheckInResponse)
def check_in_event_ticket(
    event_id: int,
    payload: TicketCheckInRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> TicketCheckInResponse:
    try:
        ticket = check_in_ticket_for_event(
            db,
            scanner_user_id=user_id,
            event_id=event_id,
            qr_payload=payload.qr_payload,
            ticket_code=payload.ticket_code,
        )
    except TicketAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TicketCrossEventError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except TicketCheckInConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return TicketCheckInResponse(
        success=True,
        ticket_id=ticket.id,
        event_id=ticket.event_id,
        status=ticket.status.value,
        checked_in_at=ticket.checked_in_at,
        checked_in_by_user_id=ticket.checked_in_by_user_id,
        message="Ticket checked in successfully.",
    )
