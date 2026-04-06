from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.ticket_holds import get_current_user_id
from app.db.session import get_db
from app.schemas.order import CreatePendingOrderFromHoldsRequest, OrderItemResponse, OrderResponse
from app.services.orders import (
    EmptyHoldSelectionError,
    HoldAlreadyAttachedError,
    HoldEventMismatchError,
    HoldExpiredError,
    HoldNotFoundError,
    HoldOwnershipError,
    create_pending_order_from_holds,
    get_order_for_user,
)

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("/from-holds", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order_from_holds(
    payload: CreatePendingOrderFromHoldsRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> OrderResponse:
    try:
        order = create_pending_order_from_holds(db, user_id=user_id, hold_ids=payload.hold_ids)
    except EmptyHoldSelectionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except HoldNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except HoldOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except HoldExpiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except HoldAlreadyAttachedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except HoldEventMismatchError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return OrderResponse(
        id=order.id,
        user_id=order.user_id,
        event_id=order.event_id,
        status=order.status.value,
        total_amount=float(order.total_amount),
        currency=order.currency,
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=[
            OrderItemResponse(
                id=item.id,
                ticket_tier_id=item.ticket_tier_id,
                quantity=item.quantity,
                unit_price=float(item.unit_price),
            )
            for item in order.order_items
        ],
    )


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> OrderResponse:
    order = get_order_for_user(db, order_id=order_id, user_id=user_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")

    return OrderResponse(
        id=order.id,
        user_id=order.user_id,
        event_id=order.event_id,
        status=order.status.value,
        total_amount=float(order.total_amount),
        currency=order.currency,
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=[
            OrderItemResponse(
                id=item.id,
                ticket_tier_id=item.ticket_tier_id,
                quantity=item.quantity,
                unit_price=float(item.unit_price),
            )
            for item in order.order_items
        ],
    )
