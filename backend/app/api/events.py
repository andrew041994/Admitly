from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.ticket_holds import get_current_user_id
from app.db.session import get_db
from app.models.enums import EventRefundBatchStatus
from app.models.user import User
from app.schemas.event import EventCancelRequest, EventRefundBatchResponse, EventResponse
from app.services.events import (
    EventAuthorizationError,
    EventCancellationError,
    EventNotFoundError,
    cancel_event,
    get_event_refund_batch,
    list_event_refund_batches,
)

router = APIRouter(prefix="/events", tags=["events"])


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
