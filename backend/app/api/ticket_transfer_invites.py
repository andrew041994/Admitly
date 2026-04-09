from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.rate_limit import apply_rate_limit, request_client_ip
from app.api.ticket_holds import get_current_user_id
from app.core.config import settings
from app.db.session import get_db
from app.schemas.ticket_transfer_invite import (
    AcceptTicketTransferInviteResponse,
    CreateTicketTransferInviteRequest,
    RevokeTicketTransferInviteResponse,
    TicketTransferInvitePreviewResponse,
    TicketTransferInviteResponse,
)
from app.services.tickets import (
    TicketAuthorizationError,
    TicketNotFoundError,
    TicketTransferError,
    accept_ticket_transfer_invite,
    create_ticket_transfer_invite,
    build_transfer_claim_url,
    get_ticket_transfer_invite_by_token,
    list_ticket_transfer_invites_for_user,
    revoke_ticket_transfer_invite,
)

router = APIRouter(tags=["ticket-transfer-invites"])


def _to_invite_response(invite) -> TicketTransferInviteResponse:
    return TicketTransferInviteResponse(
        id=invite.id,
        ticket_id=invite.ticket_id,
        sender_user_id=invite.sender_user_id,
        recipient_user_id=invite.recipient_user_id,
        recipient_email=invite.recipient_email,
        recipient_phone=invite.recipient_phone,
        recipient_name=invite.recipient_name,
        invite_token=invite.invite_token,
        status=invite.status.value,
        expires_at=invite.expires_at,
        accepted_at=invite.accepted_at,
        revoked_at=invite.revoked_at,
        claim_url=build_transfer_claim_url(invite_token=invite.invite_token),
        created_at=invite.created_at,
        updated_at=invite.updated_at,
    )


def _to_invite_preview_response(invite) -> TicketTransferInvitePreviewResponse:
    ticket = invite.ticket
    event = ticket.event if ticket else None
    return TicketTransferInvitePreviewResponse(
        transfer_id=invite.id,
        ticket_id=invite.ticket_id,
        event_title=event.title if event else None,
        starts_at=event.start_at if event else None,
        venue_name=(event.custom_venue_name or (event.venue.name if event and event.venue else None)) if event else None,
        ticket_tier_name=ticket.ticket_tier.name if ticket and ticket.ticket_tier else None,
        sender_name=invite.sender.full_name if invite.sender else None,
        recipient_name=invite.recipient_name,
        recipient_email=invite.recipient_email,
        recipient_phone=invite.recipient_phone,
        status=invite.status.value,
        expires_at=invite.expires_at,
        accepted_at=invite.accepted_at,
        canceled_at=invite.revoked_at,
        claim_url=build_transfer_claim_url(invite_token=invite.invite_token),
    )


@router.post("/tickets/{ticket_id}/transfer-invites", response_model=TicketTransferInviteResponse, status_code=status.HTTP_201_CREATED)
def create_transfer_invite(
    ticket_id: int,
    payload: CreateTicketTransferInviteRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    client_ip: str = Depends(request_client_ip),
) -> TicketTransferInviteResponse:
    apply_rate_limit(
        scope="transfer_invite_create",
        key=f"{user_id}:{ticket_id}:{client_ip}",
        limit=settings.rate_limit_transfer_invite_count,
        window_seconds=settings.rate_limit_transfer_invite_window_seconds,
    )
    try:
        invite = create_ticket_transfer_invite(
            db,
            ticket_id=ticket_id,
            sender_user_id=user_id,
            recipient_user_id=payload.recipient_user_id,
            recipient_email=payload.recipient_email,
            recipient_phone=payload.recipient_phone,
            recipient_name=payload.recipient_name,
            expires_at=payload.expires_at,
        )
    except TicketAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TicketTransferError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _to_invite_response(invite)


@router.post("/ticket-transfer-invites/{invite_token}/accept", response_model=AcceptTicketTransferInviteResponse)
def accept_transfer_invite(
    invite_token: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    client_ip: str = Depends(request_client_ip),
) -> AcceptTicketTransferInviteResponse:
    apply_rate_limit(
        scope="transfer_invite_accept",
        key=f"{user_id}:{invite_token}:{client_ip}",
        limit=settings.rate_limit_payment_submit_count,
        window_seconds=settings.rate_limit_payment_submit_window_seconds,
    )
    try:
        ticket = accept_ticket_transfer_invite(db, invite_token=invite_token, accepting_user_id=user_id)
    except TicketAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TicketTransferError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return AcceptTicketTransferInviteResponse(ticket_id=ticket.id, owner_user_id=ticket.owner_user_id, status=ticket.status.value)


@router.post("/ticket-transfer-invites/{invite_token}/revoke", response_model=RevokeTicketTransferInviteResponse)
def revoke_transfer_invite(
    invite_token: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> RevokeTicketTransferInviteResponse:
    try:
        invite = revoke_ticket_transfer_invite(db, invite_token=invite_token, actor_user_id=user_id)
    except TicketAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TicketTransferError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return RevokeTicketTransferInviteResponse(id=invite.id, status=invite.status.value, revoked_at=invite.revoked_at)


@router.get("/ticket-transfer-invites/{invite_token}", response_model=TicketTransferInviteResponse)
def get_transfer_invite(
    invite_token: str,
    db: Session = Depends(get_db),
) -> TicketTransferInviteResponse:
    try:
        invite = get_ticket_transfer_invite_by_token(db, invite_token=invite_token)
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_invite_response(invite)


@router.get("/tickets/transfers/{invite_token}", response_model=TicketTransferInvitePreviewResponse)
def preview_transfer_invite(
    invite_token: str,
    db: Session = Depends(get_db),
) -> TicketTransferInvitePreviewResponse:
    try:
        invite = get_ticket_transfer_invite_by_token(db, invite_token=invite_token)
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_invite_preview_response(invite)


@router.post("/tickets/transfers/{invite_token}/accept", response_model=AcceptTicketTransferInviteResponse)
def accept_transfer_invite_v2(
    invite_token: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    client_ip: str = Depends(request_client_ip),
) -> AcceptTicketTransferInviteResponse:
    apply_rate_limit(
        scope="transfer_invite_accept",
        key=f"{user_id}:{invite_token}:{client_ip}",
        limit=settings.rate_limit_payment_submit_count,
        window_seconds=settings.rate_limit_payment_submit_window_seconds,
    )
    try:
        ticket = accept_ticket_transfer_invite(db, invite_token=invite_token, accepting_user_id=user_id)
    except TicketAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TicketTransferError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return AcceptTicketTransferInviteResponse(ticket_id=ticket.id, owner_user_id=ticket.owner_user_id, status=ticket.status.value)


@router.post("/tickets/transfers/{invite_token}/cancel", response_model=RevokeTicketTransferInviteResponse)
def cancel_transfer_invite(
    invite_token: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> RevokeTicketTransferInviteResponse:
    try:
        invite = revoke_ticket_transfer_invite(db, invite_token=invite_token, actor_user_id=user_id)
    except TicketAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TicketTransferError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return RevokeTicketTransferInviteResponse(id=invite.id, status=invite.status.value, revoked_at=invite.revoked_at)


@router.get("/me/ticket-transfer-invites", response_model=list[TicketTransferInviteResponse])
def get_my_transfer_invites(
    sent: bool = Query(default=False),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[TicketTransferInviteResponse]:
    invites = list_ticket_transfer_invites_for_user(db, user_id=user_id, sent=sent)
    return [_to_invite_response(invite) for invite in invites]
