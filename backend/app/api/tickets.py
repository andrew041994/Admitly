from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.ticket_holds import get_current_user_id
from app.db.session import get_db
from app.schemas.notification import NotificationDispatchResponse
from app.schemas.ticket import (
    TicketCheckInConfirmRequest,
    TicketCheckInRequest,
    TicketCheckInResponse,
    TicketCheckInSummaryResponse,
    TicketCheckInValidateRequest,
    TicketCheckInValidateResponse,
    TicketResponse,
    TicketTransferRequest,
    TicketVoidRequest,
    TicketQrResponse,
)
from app.services.tickets import (
    CHECK_IN_METHOD_MANUAL,
    CHECK_IN_METHOD_QR,
    TicketAuthorizationError,
    TicketCheckInConflictError,
    TicketCrossEventError,
    TicketNotFoundError,
    TicketTransferError,
    TicketVoidError,
    check_in_ticket,
    check_in_ticket_for_event,
    get_event_check_in_summary,
    get_ticket_by_qr_payload,
    get_ticket_for_owner,
    list_tickets_for_order_owner,
    list_tickets_for_user,
    transfer_ticket_to_user,
    validate_ticket_for_check_in,
    void_ticket,
    resend_ticket_notification,
)
from app.services.ticket_qr import (
    build_ticket_qr_payload,
    generate_qr_png_bytes,
    generate_ticket_qr_data_uri,
    get_ticket_public_url,
    get_ticket_qr_image_url,
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
        public_ticket_url=get_ticket_public_url(ticket),
        qr_image_url=get_ticket_qr_image_url(ticket),
        issued_at=ticket.issued_at,
        checked_in_at=ticket.checked_in_at,
        check_in_method=ticket.check_in_method,
        transferred_at=ticket.transferred_at,
        voided_at=ticket.voided_at,
        voided_by_user_id=ticket.voided_by_user_id,
        void_reason=ticket.void_reason,
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


@router.post("/tickets/{ticket_id}/void", response_model=TicketResponse)
def void_existing_ticket(
    ticket_id: int,
    payload: TicketVoidRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> TicketResponse:
    try:
        ticket = void_ticket(
            db,
            ticket_id=ticket_id,
            actor_user_id=user_id,
            reason=payload.reason,
        )
    except TicketAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TicketVoidError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _to_ticket_response(ticket)


@router.post("/events/{event_id}/check-in/validate", response_model=TicketCheckInValidateResponse)
def validate_event_ticket(
    event_id: int,
    payload: TicketCheckInValidateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> TicketCheckInValidateResponse:
    result = validate_ticket_for_check_in(
        db,
        actor_user_id=user_id,
        event_id=event_id,
        qr_payload=payload.qr_payload,
        ticket_code=payload.ticket_code,
    )
    return TicketCheckInValidateResponse(
        valid=result.valid,
        code=result.status,
        message=result.message,
        ticket_id=result.ticket.id if result.ticket else None,
        ticket_code=result.ticket.ticket_code if result.ticket else None,
        event_id=event_id,
        checked_in_at=result.checked_in_at,
    )


@router.post("/events/{event_id}/check-in/confirm", response_model=TicketCheckInResponse)
def confirm_event_ticket_check_in(
    event_id: int,
    payload: TicketCheckInConfirmRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> TicketCheckInResponse:
    method = payload.method or CHECK_IN_METHOD_QR
    result = check_in_ticket(
        db,
        scanner_user_id=user_id,
        event_id=event_id,
        qr_payload=payload.qr_payload,
        ticket_code=payload.ticket_code,
        method=method,
    )
    return TicketCheckInResponse(
        success=result.valid,
        code=result.status,
        ticket_id=result.ticket.id if result.ticket else None,
        event_id=event_id,
        status=result.ticket.status.value if result.ticket else None,
        checked_in_at=result.checked_in_at,
        checked_in_by_user_id=result.ticket.checked_in_by_user_id if result.ticket else None,
        message=result.message,
    )


@router.post("/events/{event_id}/check-in/manual", response_model=TicketCheckInResponse)
def manual_event_ticket_check_in(
    event_id: int,
    payload: TicketCheckInValidateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> TicketCheckInResponse:
    result = check_in_ticket(
        db,
        scanner_user_id=user_id,
        event_id=event_id,
        qr_payload=payload.qr_payload,
        ticket_code=payload.ticket_code,
        method=CHECK_IN_METHOD_MANUAL,
    )
    return TicketCheckInResponse(
        success=result.valid,
        code=result.status,
        ticket_id=result.ticket.id if result.ticket else None,
        event_id=event_id,
        status=result.ticket.status.value if result.ticket else None,
        checked_in_at=result.checked_in_at,
        checked_in_by_user_id=result.ticket.checked_in_by_user_id if result.ticket else None,
        message=result.message,
    )


@router.get("/events/{event_id}/check-in/summary", response_model=TicketCheckInSummaryResponse)
def get_event_ticket_check_in_summary(
    event_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> TicketCheckInSummaryResponse:
    try:
        summary = get_event_check_in_summary(db, actor_user_id=user_id, event_id=event_id)
    except TicketAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    return TicketCheckInSummaryResponse(
        event_id=summary.event_id,
        total_admittable_tickets=summary.total_admittable_tickets,
        checked_in_tickets=summary.checked_in_tickets,
        remaining_tickets=summary.remaining_tickets,
    )


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
        code="valid",
        ticket_id=ticket.id,
        event_id=ticket.event_id,
        status=ticket.status.value,
        checked_in_at=ticket.checked_in_at,
        checked_in_by_user_id=ticket.checked_in_by_user_id,
        message="Ticket checked in successfully.",
    )


@router.post("/tickets/{ticket_id}/resend", response_model=NotificationDispatchResponse)
def resend_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> NotificationDispatchResponse:
    try:
        result = resend_ticket_notification(db, ticket_id=ticket_id, actor_user_id=user_id)
    except TicketAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return NotificationDispatchResponse(success=result.success, channel_results=result.channel_results)


@router.get("/tickets/{ticket_id}/qr", response_model=TicketQrResponse)
def get_ticket_qr_by_ticket_id(
    ticket_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> TicketQrResponse:
    ticket = get_ticket_for_owner(db, ticket_id=ticket_id, user_id=user_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")
    return TicketQrResponse(
        ticket_public_token=ticket.qr_payload,
        qr_payload=build_ticket_qr_payload(ticket),
        public_ticket_url=get_ticket_public_url(ticket),
        qr_image_url=get_ticket_qr_image_url(ticket),
        qr_data_uri=generate_ticket_qr_data_uri(ticket),
    )


@router.get("/t/{ticket_token}", response_model=TicketQrResponse)
def get_public_ticket_qr(
    ticket_token: str,
    db: Session = Depends(get_db),
) -> TicketQrResponse:
    ticket = get_ticket_by_qr_payload(db, qr_payload=ticket_token)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")
    return TicketQrResponse(
        ticket_public_token=ticket.qr_payload,
        qr_payload=build_ticket_qr_payload(ticket),
        public_ticket_url=get_ticket_public_url(ticket),
        qr_image_url=get_ticket_qr_image_url(ticket),
        qr_data_uri=generate_ticket_qr_data_uri(ticket),
    )


@router.get("/t/{ticket_token}/qr")
def get_public_ticket_qr_image(
    ticket_token: str,
    db: Session = Depends(get_db),
) -> Response:
    ticket = get_ticket_by_qr_payload(db, qr_payload=ticket_token)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")
    png_bytes = generate_qr_png_bytes(build_ticket_qr_payload(ticket))
    return Response(content=png_bytes, media_type="image/png")
