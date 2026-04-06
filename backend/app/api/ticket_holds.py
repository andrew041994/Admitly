from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.ticket_hold import CreateTicketHoldRequest, TicketHoldResponse
from app.services.ticket_holds import (
    InsufficientAvailabilityError,
    TicketHoldError,
    TicketHoldWindowClosedError,
    create_ticket_hold,
)

router = APIRouter(prefix="/ticket-holds", tags=["ticket-holds"])


def get_current_user_id(x_user_id: int | None = Header(default=None)) -> int:
    if x_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return x_user_id


@router.post("", response_model=TicketHoldResponse, status_code=status.HTTP_201_CREATED)
def create_hold(
    payload: CreateTicketHoldRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> TicketHoldResponse:
    try:
        result = create_ticket_hold(
            db,
            user_id=user_id,
            ticket_tier_id=payload.ticket_tier_id,
            quantity=payload.quantity,
        )
    except InsufficientAvailabilityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except TicketHoldWindowClosedError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except TicketHoldError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    hold = result.hold
    return TicketHoldResponse(
        id=hold.id,
        event_id=hold.event_id,
        ticket_tier_id=hold.ticket_tier_id,
        quantity=hold.quantity,
        expires_at=hold.expires_at,
        created_at=hold.created_at,
        availability_remaining=result.availability_remaining,
    )
