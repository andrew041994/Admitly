from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.rate_limit import apply_rate_limit, request_client_ip
from app.api.ticket_holds import get_current_user_id
from app.core.config import settings
from app.db.session import get_db
from app.schemas.ticket_transfer_invite import (
    CreateTicketTransferRequest,
    ResolveTicketTransferRecipientRequest,
    ResolveTicketTransferRecipientResponse,
    TicketTransferActionResponse,
    TicketTransferSummaryResponse,
)
from app.services.tickets import (
    TicketAuthorizationError,
    TicketNotFoundError,
    TicketTransferConflictError,
    TicketTransferError,
    TicketTransferResolutionExpiredError,
    accept_ticket_transfer,
    cancel_ticket_transfer,
    create_ticket_transfer_from_resolution,
    decline_ticket_transfer,
    list_ticket_transfers_for_user,
    mask_transfer_identifier,
    resolve_ticket_transfer_recipient,
)

router = APIRouter(tags=["ticket-transfers"])


def _raise_transfer_error(exc: Exception) -> None:
    if isinstance(exc, TicketTransferResolutionExpiredError):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from exc
    if isinstance(exc, TicketAuthorizationError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if isinstance(exc, TicketNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, TicketTransferConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _summary(invite, *, user_id: int) -> TicketTransferSummaryResponse:
    ticket = invite.ticket
    identifier = invite.recipient_email or invite.recipient_phone or ""
    return TicketTransferSummaryResponse(
        id=invite.id,
        ticket_id=invite.ticket_id,
        direction="outgoing" if invite.sender_user_id == user_id else "incoming",
        status=invite.status.value,
        recipient_identifier=mask_transfer_identifier(identifier),
        event_title=ticket.event.title,
        ticket_tier_name=ticket.ticket_tier.name,
        starts_at=ticket.event.start_at,
        expires_at=invite.expires_at,
        accepted_at=invite.accepted_at,
        declined_at=invite.declined_at,
        canceled_at=invite.canceled_at,
        created_at=invite.created_at,
        updated_at=invite.updated_at,
    )


def _action(invite) -> TicketTransferActionResponse:
    return TicketTransferActionResponse(
        id=invite.id,
        ticket_id=invite.ticket_id,
        status=invite.status.value,
        accepted_at=invite.accepted_at,
        declined_at=invite.declined_at,
        canceled_at=invite.canceled_at,
    )


@router.post(
    "/tickets/{ticket_id}/transfer-recipient-resolutions",
    response_model=ResolveTicketTransferRecipientResponse,
)
def resolve_transfer_recipient(
    ticket_id: int,
    payload: ResolveTicketTransferRecipientRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    client_ip: str = Depends(request_client_ip),
) -> ResolveTicketTransferRecipientResponse:
    apply_rate_limit(
        scope="ticket_transfer_recipient_resolve",
        key=f"{user_id}:{ticket_id}:{client_ip}",
        limit=settings.rate_limit_transfer_invite_count,
        window_seconds=settings.rate_limit_transfer_invite_window_seconds,
    )
    try:
        resolution, recipient, reference = resolve_ticket_transfer_recipient(
            db,
            ticket_id=ticket_id,
            sender_user_id=user_id,
            recipient_email=str(payload.email),
        )
    except (TicketAuthorizationError, TicketNotFoundError, TicketTransferConflictError, TicketTransferError) as exc:
        _raise_transfer_error(exc)
    normalized_email = str(payload.email)
    return ResolveTicketTransferRecipientResponse(
        recipient_display_name=(recipient.full_name or "").strip() or normalized_email,
        recipient_email=normalized_email,
        masked_email=mask_transfer_identifier(normalized_email),
        recipient_resolution_reference=reference,
        resolution_expires_at=resolution.expires_at,
    )


@router.post(
    "/tickets/{ticket_id}/transfers",
    response_model=TicketTransferActionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_transfer(
    ticket_id: int,
    payload: CreateTicketTransferRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    client_ip: str = Depends(request_client_ip),
) -> TicketTransferActionResponse:
    apply_rate_limit(
        scope="ticket_transfer_create",
        key=f"{user_id}:{ticket_id}:{client_ip}",
        limit=settings.rate_limit_transfer_invite_count,
        window_seconds=settings.rate_limit_transfer_invite_window_seconds,
    )
    try:
        invite = create_ticket_transfer_from_resolution(
            db,
            ticket_id=ticket_id,
            sender_user_id=user_id,
            recipient_resolution_reference=payload.recipient_resolution_reference,
        )
    except (TicketAuthorizationError, TicketNotFoundError, TicketTransferConflictError, TicketTransferError) as exc:
        _raise_transfer_error(exc)
    return _action(invite)


@router.get("/me/ticket-transfers", response_model=list[TicketTransferSummaryResponse])
def list_my_transfers(
    direction: str = Query(default="all", pattern="^(all|incoming|outgoing)$"),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[TicketTransferSummaryResponse]:
    invites = list_ticket_transfers_for_user(db, user_id=user_id, direction=direction)
    return [_summary(invite, user_id=user_id) for invite in invites]


@router.post("/ticket-transfers/{transfer_id}/accept", response_model=TicketTransferActionResponse)
def accept_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    client_ip: str = Depends(request_client_ip),
) -> TicketTransferActionResponse:
    apply_rate_limit(
        scope="ticket_transfer_accept",
        key=f"{user_id}:{transfer_id}:{client_ip}",
        limit=settings.rate_limit_payment_submit_count,
        window_seconds=settings.rate_limit_payment_submit_window_seconds,
    )
    try:
        return _action(accept_ticket_transfer(db, transfer_id=transfer_id, accepting_user_id=user_id))
    except (TicketAuthorizationError, TicketNotFoundError, TicketTransferConflictError, TicketTransferError) as exc:
        _raise_transfer_error(exc)


@router.post("/ticket-transfers/{transfer_id}/decline", response_model=TicketTransferActionResponse)
def decline_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    client_ip: str = Depends(request_client_ip),
) -> TicketTransferActionResponse:
    apply_rate_limit(
        scope="ticket_transfer_decline",
        key=f"{user_id}:{transfer_id}:{client_ip}",
        limit=settings.rate_limit_payment_submit_count,
        window_seconds=settings.rate_limit_payment_submit_window_seconds,
    )
    try:
        return _action(decline_ticket_transfer(db, transfer_id=transfer_id, recipient_user_id=user_id))
    except (TicketAuthorizationError, TicketNotFoundError, TicketTransferConflictError, TicketTransferError) as exc:
        _raise_transfer_error(exc)


@router.post("/ticket-transfers/{transfer_id}/cancel", response_model=TicketTransferActionResponse)
def cancel_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    client_ip: str = Depends(request_client_ip),
) -> TicketTransferActionResponse:
    apply_rate_limit(
        scope="ticket_transfer_cancel",
        key=f"{user_id}:{transfer_id}:{client_ip}",
        limit=settings.rate_limit_payment_submit_count,
        window_seconds=settings.rate_limit_payment_submit_window_seconds,
    )
    try:
        return _action(cancel_ticket_transfer(db, transfer_id=transfer_id, sender_user_id=user_id))
    except (TicketAuthorizationError, TicketNotFoundError, TicketTransferConflictError, TicketTransferError) as exc:
        _raise_transfer_error(exc)
