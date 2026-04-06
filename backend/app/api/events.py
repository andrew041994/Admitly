from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.ticket_holds import get_current_user_id
from app.db.session import get_db
from app.schemas.event import EventCancelRequest, EventResponse
from app.services.events import (
    EventAuthorizationError,
    EventCancellationError,
    EventNotFoundError,
    cancel_event,
)

router = APIRouter(prefix="/events", tags=["events"])


@router.post("/{event_id}/cancel", response_model=EventResponse)
def cancel_existing_event(
    event_id: int,
    payload: EventCancelRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> EventResponse:
    try:
        event = cancel_event(
            db,
            event_id=event_id,
            actor_user_id=user_id,
            reason=payload.reason,
        )
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
    )
