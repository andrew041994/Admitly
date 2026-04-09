from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session


from app.api.ticket_holds import get_current_user_id
from app.db.session import get_db
from app.schemas.notification import NotificationDispatchResponse
from app.schemas.ticket import (
    TicketCheckInAttemptResponse,
    TicketCheckInConfirmRequest,
    TicketCheckInOverrideRequest,
    TicketCheckInRequest,
    TicketCheckInResponse,
    TicketCheckInSummaryResponse,
    TicketCheckInValidateRequest,
    TicketCheckInValidateResponse,
    TicketDetailResponse,
    TicketResponse,
    TicketTransferRequest,
    TicketTransferPendingResponse,
    TicketVoidRequest,
    TicketQrResponse,
    TicketScanRequest,
    TicketScanResponse,
)
from app.schemas.ticket_wallet import (
    WalletEventSummary,
    WalletOrganizerSummary,
    WalletOwnershipSummary,
    WalletTicketCardItemResponse,
    WalletTicketDetailResponse,
    WalletVenueSummary,
)
from app.services.tickets import (
    CHECK_IN_METHOD_MANUAL,
    CHECK_IN_METHOD_QR,
    CHECK_IN_STATUS_TRANSFER_PENDING,
    TicketAuthorizationError,
    TicketCheckInConflictError,
    TicketCrossEventError,
    TicketNotFoundError,
    TicketTransferError,
    TicketVoidError,
    check_in_ticket,
    get_event_check_in_summary,
    get_ticket_by_qr_payload,
    get_ticket_for_owner,
    list_tickets_for_order_owner,
    list_recent_check_in_attempts,
    override_ticket_check_in,
    build_transfer_claim_url,
    create_ticket_transfer_invite,
    validate_ticket_for_check_in,
    void_ticket,
    resend_ticket_notification,
    scan_ticket,
    check_in_ticket_manually,
)
from app.services.ticket_wallet import WalletTicketView, get_wallet_ticket, list_wallet_tickets
from app.services.ticket_qr import (
    build_ticket_qr_payload,
    ensure_ticket_qr,
    generate_qr_png_bytes,
    generate_ticket_qr_data_uri,
    get_ticket_public_url,
    get_ticket_qr_image_url,
)
from app.models.event import Event


router = APIRouter(tags=["tickets"])

_CHECK_IN_PUBLIC_CODE_MAP = {
    "valid": "admitted",
    "already_checked_in": "already_used",
    "wrong_event": "wrong_event",
    "invalid": "invalid_qr",
    "not_found": "not_found",
    "refunded_or_invalidated": "voided",
    "unauthorized": "unauthorized",
    "canceled_event": "event_not_admittable",
    "order_not_admittable": "event_not_admittable",
    CHECK_IN_STATUS_TRANSFER_PENDING: "transfer_pending",
}

_CHECK_IN_PUBLIC_MESSAGE_MAP = {
    "admitted": "Admitted",
    "already_used": "Ticket already used",
    "wrong_event": "Wrong event",
    "invalid_qr": "Invalid ticket",
    "not_found": "Ticket not found",
    "voided": "Ticket voided",
    "unauthorized": "You are not authorized to check in tickets for this event",
    "event_not_admittable": "Event is not accepting check-ins",
    "transfer_pending": "Ticket transfer is pending acceptance",
}


def _normalize_check_in_status(status: str | None) -> str:
    if not status:
        return "invalid_qr"
    return _CHECK_IN_PUBLIC_CODE_MAP.get(status, status)


def _build_check_in_response(*, event_id: int, result) -> TicketCheckInResponse:
    code = _normalize_check_in_status(result.status)
    success = code == "admitted" and bool(result.valid)
    message = _CHECK_IN_PUBLIC_MESSAGE_MAP.get(code, result.message)
    return TicketCheckInResponse(
        success=success,
        code=code,
        ticket_id=result.ticket.id if result.ticket else None,
        event_id=event_id,
        status=result.ticket.status.value if result.ticket else None,
        checked_in_at=result.checked_in_at,
        checked_in_by_user_id=result.ticket.checked_in_by_user_id if result.ticket else None,
        message=message,
        ui_signal="green" if success else "red",
    )




def _build_venue_address(event) -> str | None:
    if event is None:
        return None
    if event.custom_address_text:
        return event.custom_address_text
    venue = event.venue
    if venue is None:
        return None
    parts = [venue.address_line1, venue.address_line2, venue.city, venue.country]
    clean = [p.strip() for p in parts if p and p.strip()]
    return ", ".join(clean) if clean else None


def _to_ticket_response(db: Session, ticket) -> TicketResponse:
    ensure_ticket_qr(db, ticket)
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
        display_code=ticket.display_code,
        qr_payload=build_ticket_qr_payload(ticket),
        public_ticket_url=get_ticket_public_url(ticket),
        qr_image_url=get_ticket_qr_image_url(ticket),
        event_title=ticket.event.title if ticket.event else None,
        starts_at=ticket.event.start_at if ticket.event else None,
        venue_name=(ticket.event.custom_venue_name or (ticket.event.venue.name if ticket.event and ticket.event.venue else None)) if ticket.event else None,
        ticket_tier_name=ticket.ticket_tier.name if ticket.ticket_tier else None,
        issued_at=ticket.issued_at,
        checked_in_at=ticket.checked_in_at,
        check_in_method=ticket.check_in_method,
        transferred_at=ticket.transferred_at,
        voided_at=ticket.voided_at,
        voided_by_user_id=ticket.voided_by_user_id,
        void_reason=ticket.void_reason,
        transfer_count=ticket.transfer_count,
    )


def _to_ticket_detail_response(db: Session, ticket) -> TicketDetailResponse:
    base = _to_ticket_response(db, ticket)

    base_data = base.model_dump()
    event = ticket.event

# remove fields that will be overridden explicitly
    base_data.pop("ticket_tier_name", None)

    return TicketDetailResponse(
        **base_data,
        ticket_id=ticket.id,
        ticket_public_id=ticket.display_code,
        attendee_name=ticket.owner.full_name if ticket.owner else None,
        attendee_email=ticket.owner.email if ticket.owner else None,
        event_description=event.long_description if event else None,
        venue_address=_build_venue_address(event),
        ends_at=event.end_at if event else None,
        timezone=event.timezone if event else None,
        order_reference=ticket.order.reference_code if ticket.order else None,
        ticket_tier_name=ticket.ticket_tier.name if ticket.ticket_tier else None,
        ticket_status=ticket.status.value,
        transferred_from_user_id=ticket.purchaser_user_id if ticket.owner_user_id != ticket.purchaser_user_id else None,
        transferred_to_user_id=ticket.owner_user_id if ticket.owner_user_id != ticket.purchaser_user_id else None,
        created_at=ticket.created_at,
        subtitle=ticket.ticket_tier.name if ticket.ticket_tier else None,
    )


def _to_wallet_ticket_card(view: WalletTicketView) -> WalletTicketCardItemResponse:
    ticket = view.ticket
    event = ticket.event
    return WalletTicketCardItemResponse(
        id=ticket.id,
        ticket_code=ticket.ticket_code,
        display_code=ticket.display_code,
        ticket_status=ticket.status.value,
        display_status=view.display_status,
        is_valid_for_entry=view.is_valid_for_entry,
        can_display_entry_code=view.can_display_entry_code,
        event=WalletEventSummary(
            id=event.id,
            title=event.title,
            start_at=event.start_at,
            end_at=event.end_at,
            timezone=event.timezone,
            banner_image_url=event.cover_image_url,
            is_upcoming=view.event_is_upcoming,
            status=event.status.value,
        ),
        venue=WalletVenueSummary(
            name=event.custom_venue_name or (event.venue.name if event.venue else None),
            address_summary=_build_venue_address(event),
        ),
        organizer=WalletOrganizerSummary(name=event.organizer.display_name if event.organizer else None),
        ticket_tier_name=ticket.ticket_tier.name,
        ownership=WalletOwnershipSummary(
            is_current_owner=True,
            purchaser_user_id=ticket.purchaser_user_id,
            owner_user_id=ticket.owner_user_id,
            acquired_via_transfer=ticket.owner_user_id != ticket.purchaser_user_id,
        ),
        order_id=ticket.order_id,
        order_reference=ticket.order.reference_code if ticket.order else None,
        issued_at=ticket.issued_at,
        checked_in_at=ticket.checked_in_at,
        transferred_at=ticket.transferred_at,
        transfer_count=ticket.transfer_count,
    )


@router.get("/me/tickets", response_model=list[WalletTicketCardItemResponse])
def get_my_tickets(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[WalletTicketCardItemResponse]:
    views = list_wallet_tickets(db, user_id=user_id)
    return [_to_wallet_ticket_card(v) for v in views]


@router.get("/me/tickets/{ticket_id}", response_model=WalletTicketDetailResponse)
def get_my_ticket_detail(
    ticket_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> WalletTicketDetailResponse:
    view = get_wallet_ticket(db, user_id=user_id, ticket_id=ticket_id)
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    card = _to_wallet_ticket_card(view)
    ticket = view.ticket
    ensure_ticket_qr(db, ticket)
    return WalletTicketDetailResponse(
        **card.model_dump(),
        qr_payload=build_ticket_qr_payload(ticket),
        check_in_token=ticket.ticket_code,
        check_in_method=ticket.check_in_method,
        voided_at=ticket.voided_at,
        void_reason=ticket.void_reason,
        order_status=ticket.order.status.value if ticket.order else "unknown",
        order_refund_status=ticket.order.refund_status if ticket.order else "unknown",
    )


@router.get("/tickets/{ticket_id}", response_model=TicketDetailResponse)
def get_ticket_detail(
    ticket_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> TicketDetailResponse:
    ticket = get_ticket_for_owner(db, ticket_id=ticket_id, user_id=user_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return _to_ticket_detail_response(db, ticket)


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

    return [_to_ticket_response(db, t) for t in tickets]


@router.post("/tickets/{ticket_id}/transfer", response_model=TicketTransferPendingResponse)
def transfer_ticket(
    ticket_id: int,
    payload: TicketTransferRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> TicketTransferPendingResponse:
    try:
        invite = create_ticket_transfer_invite(
            db,
            ticket_id=ticket_id,
            sender_user_id=user_id,
            recipient_user_id=payload.to_user_id,
            recipient_email=payload.recipient_email,
            recipient_phone=payload.recipient_phone,
            recipient_name=payload.recipient_name,
        )
    except TicketAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TicketTransferError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return TicketTransferPendingResponse(
        transfer_id=invite.id,
        ticket_id=invite.ticket_id,
        status=invite.status.value,
        recipient_user_id=invite.recipient_user_id,
        recipient_email=invite.recipient_email,
        recipient_phone=invite.recipient_phone,
        recipient_name=invite.recipient_name,
        expires_at=invite.expires_at,
        claim_url=build_transfer_claim_url(invite_token=invite.invite_token),
        created_at=invite.created_at,
    )


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

    return _to_ticket_response(db, ticket)


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
    return _build_check_in_response(event_id=event_id, result=result)


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
    return _build_check_in_response(event_id=event_id, result=result)


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


@router.get("/events/{event_id}/check-in/activity", response_model=list[TicketCheckInAttemptResponse])
def get_event_ticket_check_in_activity(
    event_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[TicketCheckInAttemptResponse]:
    try:
        rows = list_recent_check_in_attempts(db, actor_user_id=user_id, event_id=event_id, limit=limit)
    except TicketAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return [
        TicketCheckInAttemptResponse(
            id=row.id,
            ticket_id=row.ticket_id,
            event_id=row.event_id,
            actor_user_id=row.actor_user_id,
            attempted_at=row.attempted_at,
            result_code=row.result_code,
            reason_code=row.reason_code,
            reason_message=row.reason_message,
            method=row.method,
            source=row.source,
            notes=row.notes,
        )
        for row in rows
    ]


@router.post("/events/{event_id}/check-in/override", response_model=TicketCheckInResponse)
def override_event_ticket_check_in(
    event_id: int,
    payload: TicketCheckInOverrideRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> TicketCheckInResponse:
    try:
        result = override_ticket_check_in(
            db,
            actor_user_id=user_id,
            event_id=event_id,
            qr_payload=payload.qr_payload,
            ticket_code=payload.ticket_code,
            admit=payload.admit,
            notes=payload.notes,
        )
    except TicketAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TicketCrossEventError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except TicketCheckInConflictError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _build_check_in_response(event_id=event_id, result=result)


@router.post("/events/{event_id}/tickets/check-in", response_model=TicketCheckInResponse)
def check_in_event_ticket(
    event_id: int,
    payload: TicketCheckInRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> TicketCheckInResponse:
    result = check_in_ticket(
        db,
        scanner_user_id=user_id,
        event_id=event_id,
        qr_payload=payload.qr_payload,
        ticket_code=payload.ticket_code,
        method=CHECK_IN_METHOD_QR,
    )
    return _build_check_in_response(event_id=event_id, result=result)


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
    ensure_ticket_qr(db, ticket)
    db.flush()
    return TicketQrResponse(
        ticket_public_token=ticket.qr_token or ticket.qr_payload,
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
    ensure_ticket_qr(db, ticket)
    db.flush()
    return TicketQrResponse(
        ticket_public_token=ticket.qr_token or ticket.qr_payload,
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
    ensure_ticket_qr(db, ticket)
    db.flush()
    png_bytes = generate_qr_png_bytes(build_ticket_qr_payload(ticket))
    return Response(content=png_bytes, media_type="image/png")


@router.post("/tickets/scan", response_model=TicketScanResponse)
def scan_ticket_qr(
    payload: TicketScanRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> TicketScanResponse:
    result = scan_ticket(db, payload=payload.payload, user_id=user_id)
    return TicketScanResponse(
        status=result.status,
        ticket_id=result.ticket_id,
        checked_in_at=result.checked_in_at,
        message=result.message,
    )


@router.post("/tickets/{ticket_id}/check-in", response_model=TicketScanResponse)
def check_in_ticket_by_id(
    ticket_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> TicketScanResponse:
    result = check_in_ticket_manually(db, ticket_id=ticket_id, user_id=user_id)
    return TicketScanResponse(
        status=result.status,
        ticket_id=result.ticket_id,
        checked_in_at=result.checked_in_at,
        message=result.message,
    )
