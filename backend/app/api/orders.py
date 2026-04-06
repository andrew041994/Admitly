from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.ticket_holds import get_current_user_id
from app.core.config import settings
from app.db.session import get_db
from app.schemas.mmg import (
    CreateOrderMMGAgentResponse,
    CreateOrderMMGCheckoutResponse,
    SubmitMMGAgentPaymentRequest,
    SubmitMMGAgentPaymentResponse,
)
from app.schemas.order import CreatePendingOrderFromHoldsRequest, OrderItemResponse, OrderResponse
from app.services.orders import (
    EmptyHoldSelectionError,
    HoldAlreadyAttachedError,
    HoldEventMismatchError,
    HoldExpiredError,
    HoldNotFoundError,
    HoldOwnershipError,
    OrderNotPayableError,
    create_pending_order_from_holds,
    get_order_for_user,
)
from app.services.payments import (
    MMGProviderError,
    PaymentAuthorizationError,
    PaymentError,
    PaymentMethodMismatchError,
    create_mmg_agent_checkout_for_order,
    create_mmg_checkout_for_order,
    submit_mmg_agent_payment,
)

router = APIRouter(prefix="/orders", tags=["orders"])


def _require_mmg_enabled() -> None:
    if not settings.mmg_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MMG payments are currently disabled.",
        )


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


@router.post("/{order_id}/payments/mmg/initiate", response_model=CreateOrderMMGCheckoutResponse)
def initiate_mmg_checkout(
    order_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> CreateOrderMMGCheckoutResponse:
    _require_mmg_enabled()
    try:
        snapshot = create_mmg_checkout_for_order(db, order_id=order_id, user_id=user_id)
    except PaymentAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except (OrderNotPayableError, PaymentMethodMismatchError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except MMGProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except PaymentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return CreateOrderMMGCheckoutResponse(
        order_id=snapshot.order_id,
        provider=snapshot.provider,
        payment_method=snapshot.payment_method,
        payment_reference=snapshot.payment_reference,
        checkout_url=snapshot.checkout_url,
        amount=float(snapshot.amount),
        currency=snapshot.currency,
        status=snapshot.status,
        payment_verification_status=snapshot.payment_verification_status,
    )


@router.post("/{order_id}/payments/mmg-agent/initiate", response_model=CreateOrderMMGAgentResponse)
def initiate_mmg_agent_checkout(
    order_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> CreateOrderMMGAgentResponse:
    _require_mmg_enabled()
    try:
        snapshot = create_mmg_agent_checkout_for_order(db, order_id=order_id, user_id=user_id)
    except PaymentAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except (OrderNotPayableError, PaymentMethodMismatchError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PaymentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return CreateOrderMMGAgentResponse(
        order_id=snapshot.order_id,
        provider=snapshot.provider,
        payment_method=snapshot.payment_method,
        payment_reference=snapshot.payment_reference,
        amount=float(snapshot.amount),
        currency=snapshot.currency,
        status=snapshot.status,
        payment_verification_status=snapshot.payment_verification_status,
        instructions=snapshot.instructions,
    )


@router.post("/{order_id}/payments/mmg-agent/submit", response_model=SubmitMMGAgentPaymentResponse)
def submit_agent_payment(
    order_id: int,
    payload: SubmitMMGAgentPaymentRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> SubmitMMGAgentPaymentResponse:
    _require_mmg_enabled()
    try:
        snapshot = submit_mmg_agent_payment(
            db,
            order_id=order_id,
            user_id=user_id,
            submitted_reference_code=payload.submitted_reference_code,
        )
    except PaymentAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except (OrderNotPayableError, PaymentMethodMismatchError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PaymentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return SubmitMMGAgentPaymentResponse(
        order_id=snapshot.order_id,
        provider=snapshot.provider,
        payment_method=snapshot.payment_method,
        payment_reference=snapshot.payment_reference,
        status=snapshot.status,
        payment_verification_status=snapshot.payment_verification_status,
        message=snapshot.message or "Payment submission accepted.",
    )
