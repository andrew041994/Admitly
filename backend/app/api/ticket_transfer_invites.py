from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.ticket_holds import get_current_user_id
from app.db.session import get_db
from app.schemas.ticket_transfer_invite import (
    AcceptTicketTransferInviteResponse,
    CreateTicketTransferInviteRequest,
    RevokeTicketTransferInviteResponse,
    TicketTransferInviteResponse,
)
from app.services.tickets import (
    TicketAuthorizationError,
    TicketNotFoundError,
    TicketTransferError,
    accept_ticket_transfer_invite,
    create_ticket_transfer_invite,
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
        invite_token=invite.invite_token,
        status=invite.status.value,
        expires_at=invite.expires_at,
        accepted_at=invite.accepted_at,
        revoked_at=invite.revoked_at,
        created_at=invite.created_at,
        updated_at=invite.updated_at,
    )


@router.post("/tickets/{ticket_id}/transfer-invites", response_model=TicketTransferInviteResponse, status_code=status.HTTP_201_CREATED)
def create_transfer_invite(
    ticket_id: int,
    payload: CreateTicketTransferInviteRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> TicketTransferInviteResponse:
    try:
        invite = create_ticket_transfer_invite(
            db,
            ticket_id=ticket_id,
            sender_user_id=user_id,
            recipient_user_id=payload.recipient_user_id,
            recipient_email=payload.recipient_email,
            recipient_phone=payload.recipient_phone,
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
) -> AcceptTicketTransferInviteResponse:
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
    user_id: int = Depends(get_current_user_id),
) -> TicketTransferInviteResponse:
    _ = user_id
    try:
        invite = get_ticket_transfer_invite_by_token(db, invite_token=invite_token)
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_invite_response(invite)


@router.get("/me/ticket-transfer-invites", response_model=list[TicketTransferInviteResponse])
def get_my_transfer_invites(
    sent: bool = Query(default=False),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[TicketTransferInviteResponse]:
    invites = list_ticket_transfer_invites_for_user(db, user_id=user_id, sent=sent)
    return [_to_invite_response(invite) for invite in invites]
