from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.models.user import User
from app.services.ticket_holds import (
    InsufficientAvailabilityError,
    TicketHoldError,
    TicketHoldWindowClosedError,
    create_ticket_hold,
)
from app.models.event import Event
from app.models.enums import EventApprovalStatus, EventStatus
from app.models.ticket_tier import TicketTier
from sqlalchemy import select

from app.api.rate_limit import apply_rate_limit, request_client_ip
from app.api.auth import get_current_user, get_current_user_id
from app.core.config import settings
from app.db.session import get_db
from app.schemas.mmg import (
    CompleteDevTestCheckoutResponse,
    CreateOrderMMGAgentResponse,
    CreateOrderMMGCheckoutResponse,
    CompleteMMGAgentPaymentRequest,
    CompleteMMGAgentPaymentResponse,
)
from app.schemas.notification import NotificationDispatchResponse
from app.schemas.order import (
    CreateOrderFromSelectionRequest,
    CreatePendingOrderFromHoldsRequest,
    OrderCancelRequest,
    OrderItemResponse,
    OrderRefundRequest,
    OrderResponse,
)
from app.services.orders import (
    EmptyHoldSelectionError,
    HoldAlreadyAttachedError,
    HoldEventMismatchError,
    HoldExpiredError,
    HoldNotFoundError,
    HoldOwnershipError,
    OrderAuthorizationError,
    OrderCancellationError,
    OrderNotFoundError,
    OrderNotPayableError,
    OrderRefundError,
    PromoCodeValidationError,
    cancel_pending_order,
    create_pending_order_from_holds,
    get_order_for_user,
    refund_completed_order,
    resend_order_confirmation,
    OrderResendError,
)
from app.services.payments import (
    MMGProviderError,
    PaymentAuthorizationError,
    PaymentError,
    PaymentMethodMismatchError,
    complete_dev_test_checkout_for_order,
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


def _require_dev_test_checkout_enabled() -> None:
    if settings.is_production or not settings.enable_dev_test_checkout:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dev test checkout is disabled.",
        )


def _to_order_response(order) -> OrderResponse:
    return OrderResponse(
        id=order.id,
        user_id=order.user_id,
        event_id=order.event_id,
        status=order.status.value,
        subtotal_amount=float(order.subtotal_amount),
        discount_amount=float(order.discount_amount),
        total_amount=float(order.total_amount),
        pricing_source=order.pricing_source.value if order.pricing_source else None,
        is_comp=order.is_comp,
        promo_code_text=order.promo_code_text,
        currency=order.currency,
        refund_status=order.refund_status,
        cancelled_at=order.cancelled_at,
        cancelled_by_user_id=order.cancelled_by_user_id,
        cancel_reason=order.cancel_reason,
        refunded_at=order.refunded_at,
        refunded_by_user_id=order.refunded_by_user_id,
        refund_reason=order.refund_reason,
        created_at=order.created_at,
        reference_code=order.reference_code,
        payment_method=order.payment_method,
        payment_verification_status=order.payment_verification_status,
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



def _to_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _format_time_remaining(seconds: int) -> str:
    seconds = max(0, seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if not parts:
        parts.append(f"{remaining_seconds} second{'s' if remaining_seconds != 1 else ''}")
    return " and ".join(parts)


def _event_ended_detail(event: Event, now: datetime) -> dict:
    return {
        "code": "EVENT_ENDED",
        "message": "This event has ended and tickets are no longer available.",
        "event_id": event.id,
        "event_title": event.title,
        "event_end_at": _to_aware_datetime(event.end_at).isoformat(),
        "server_now": now.isoformat(),
    }


def _event_not_sellable_detail(event: Event) -> dict:
    return {
        "code": "EVENT_NOT_SELLABLE",
        "message": "This event is not currently available for ticket purchases.",
        "event_id": event.id,
        "event_title": event.title,
    }


def _started_event_confirmation_detail(event: Event, now: datetime) -> dict:
    seconds_until_end = max(0, int((_to_aware_datetime(event.end_at) - now).total_seconds()))
    time_remaining = _format_time_remaining(seconds_until_end)
    return {
        "code": "EVENT_ALREADY_STARTED_CONFIRMATION_REQUIRED",
        "event_id": event.id,
        "event_title": event.title,
        "event_start_at": _to_aware_datetime(event.start_at).isoformat(),
        "event_end_at": _to_aware_datetime(event.end_at).isoformat(),
        "server_now": now.isoformat(),
        "seconds_until_event_end": seconds_until_end,
        "human_readable_time_remaining": time_remaining,
        "message": f"This event has already started and ends in {time_remaining}. Do you want to continue buying tickets?",
    }


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order_from_selection(
    payload: CreateOrderFromSelectionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    client_ip: str = Depends(request_client_ip),
) -> OrderResponse:
    apply_rate_limit(
        scope="order_create",
        key=f"{current_user.id}:{client_ip}",
        limit=settings.rate_limit_order_create_count,
        window_seconds=settings.rate_limit_order_create_window_seconds,
    )

    hold_ids: list[int] = []
    reference_now = datetime.now(timezone.utc)
    event = db.execute(select(Event).where(Event.id == payload.event_id)).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    if (
        event.status != EventStatus.PUBLISHED
        or event.approval_status != EventApprovalStatus.APPROVED
        or event.cancelled_at is not None
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_event_not_sellable_detail(event))
    if reference_now >= _to_aware_datetime(event.end_at):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_event_ended_detail(event, reference_now))
    if _to_aware_datetime(event.start_at) <= reference_now and not payload.acknowledge_started_event:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_started_event_confirmation_detail(event, reference_now),
        )

    for item in payload.items:
        tier = db.execute(select(TicketTier).where(TicketTier.id == item.ticket_tier_id)).scalar_one_or_none()
        if tier is None or tier.event_id != payload.event_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ticket tier selection.")
        if item.quantity < tier.min_per_order or item.quantity > tier.max_per_order:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ticket quantity is outside allowed range.")

        try:
            hold_result = create_ticket_hold(
                db,
                user_id=current_user.id,
                ticket_tier_id=item.ticket_tier_id,
                quantity=item.quantity,
                now=reference_now,
            )
        except InsufficientAvailabilityError as exc:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except TicketHoldWindowClosedError as exc:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except TicketHoldError as exc:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        hold_ids.append(hold_result.hold.id)

    order = create_pending_order_from_holds(db, user_id=current_user.id, hold_ids=hold_ids)
    db.commit()
    db.refresh(order)

    return _to_order_response(order)


@router.post("/from-holds", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order_from_holds(
    payload: CreatePendingOrderFromHoldsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    client_ip: str = Depends(request_client_ip),
) -> OrderResponse:
    apply_rate_limit(
        scope="order_create",
        key=f"{current_user.id}:{client_ip}",
        limit=settings.rate_limit_order_create_count,
        window_seconds=settings.rate_limit_order_create_window_seconds,
    )
    try:
        order = create_pending_order_from_holds(
            db,
            user_id=current_user.id,
            hold_ids=payload.hold_ids,
            promo_code_text=payload.promo_code_text,
        )
        db.commit()
        db.refresh(order)

    except PromoCodeValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
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

    return _to_order_response(order)


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OrderResponse:
    order = get_order_for_user(db, order_id=order_id, user_id=current_user.id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")

    return _to_order_response(order)


@router.post("/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(
    order_id: int,
    payload: OrderCancelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OrderResponse:
    try:
        order = cancel_pending_order(
            db,
            order_id=order_id,
            actor_user_id=current_user.id,
            reason=payload.reason,
        )
    except OrderNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OrderAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except OrderCancellationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    db.commit()
    return _to_order_response(order)


@router.post("/{order_id}/refund", response_model=OrderResponse)
def refund_order(
    order_id: int,
    payload: OrderRefundRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OrderResponse:
    try:
        order = refund_completed_order(
            db,
            order_id=order_id,
            actor_user_id=current_user.id,
            reason=payload.reason,
        )
    except OrderNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OrderAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except OrderRefundError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    db.commit()
    return _to_order_response(order)


@router.post("/{order_id}/payments/mmg/initiate", response_model=CreateOrderMMGCheckoutResponse)
def initiate_mmg_checkout(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    client_ip: str = Depends(request_client_ip),
) -> CreateOrderMMGCheckoutResponse:
    _require_mmg_enabled()
    apply_rate_limit(
        scope="payment_initiate",
        key=f"{current_user.id}:{order_id}:{client_ip}",
        limit=settings.rate_limit_payment_initiate_count,
        window_seconds=settings.rate_limit_payment_initiate_window_seconds,
    )
    try:
        snapshot = create_mmg_checkout_for_order(db, order_id=order_id, user_id=current_user.id)
    except PaymentAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except (OrderNotPayableError, PaymentMethodMismatchError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except MMGProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except PaymentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    db.commit()
    return CreateOrderMMGCheckoutResponse(
        order_id=snapshot.order_id,
        order_reference=snapshot.order_reference,
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
    current_user: User = Depends(get_current_user),
    client_ip: str = Depends(request_client_ip),
) -> CreateOrderMMGAgentResponse:
    _require_mmg_enabled()
    apply_rate_limit(
        scope="payment_initiate",
        key=f"{current_user.id}:{order_id}:{client_ip}",
        limit=settings.rate_limit_payment_initiate_count,
        window_seconds=settings.rate_limit_payment_initiate_window_seconds,
    )
    try:
        snapshot = create_mmg_agent_checkout_for_order(db, order_id=order_id, user_id=current_user.id)
    except PaymentAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except (OrderNotPayableError, PaymentMethodMismatchError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PaymentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    db.commit()
    return CreateOrderMMGAgentResponse(
        order_id=snapshot.order_id,
        order_reference=snapshot.order_reference,
        provider=snapshot.provider,
        payment_method=snapshot.payment_method,
        payment_reference=snapshot.payment_reference,
        amount=float(snapshot.amount),
        currency=snapshot.currency,
        status=snapshot.status,
        payment_verification_status=snapshot.payment_verification_status,
        instructions=snapshot.instructions,
    )


@router.post("/{order_id}/payments/mmg-agent/complete", response_model=CompleteMMGAgentPaymentResponse)
def complete_agent_payment(
    order_id: int,
    payload: CompleteMMGAgentPaymentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    client_ip: str = Depends(request_client_ip),
) -> CompleteMMGAgentPaymentResponse:
    _require_mmg_enabled()
    apply_rate_limit(
        scope="payment_submit",
        key=f"{current_user.id}:{order_id}:{client_ip}",
        limit=settings.rate_limit_payment_submit_count,
        window_seconds=settings.rate_limit_payment_submit_window_seconds,
    )
    try:
        snapshot = submit_mmg_agent_payment(
            db,
            order_id=order_id,
            user_id=current_user.id,
            submitted_reference_code=payload.submitted_reference_code,
        )
    except PaymentAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except (OrderNotPayableError, PaymentMethodMismatchError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PaymentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    db.commit()
    return CompleteMMGAgentPaymentResponse(
        order_id=snapshot.order_id,
        order_reference=snapshot.order_reference,
        provider=snapshot.provider,
        payment_method=snapshot.payment_method,
        payment_reference=snapshot.payment_reference,
        status=snapshot.status,
        payment_verification_status=snapshot.payment_verification_status,
        message=snapshot.message or "Payment submission accepted.",
    )


@router.post("/{order_id}/payments/dev-test/complete", response_model=CompleteDevTestCheckoutResponse)
def complete_dev_test_checkout(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    client_ip: str = Depends(request_client_ip),
) -> CompleteDevTestCheckoutResponse:
    _require_dev_test_checkout_enabled()
    apply_rate_limit(
        scope="payment_submit",
        key=f"{current_user.id}:{order_id}:{client_ip}",
        limit=settings.rate_limit_payment_submit_count,
        window_seconds=settings.rate_limit_payment_submit_window_seconds,
    )
    try:
        snapshot = complete_dev_test_checkout_for_order(
            db,
            order_id=order_id,
            user_id=current_user.id,
        )
    except PaymentAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except (OrderNotPayableError, PaymentMethodMismatchError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PaymentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    db.commit()

    return CompleteDevTestCheckoutResponse(
        order_id=snapshot.order_id,
        order_reference=snapshot.order_reference,
        provider=snapshot.provider,
        payment_method=snapshot.payment_method,
        payment_reference=snapshot.payment_reference,
        status=snapshot.status,
        payment_verification_status=snapshot.payment_verification_status,
        message=snapshot.message or "Dev test checkout completed.",
    )


@router.post("/{order_id}/resend-confirmation", response_model=NotificationDispatchResponse)
def resend_order_confirmation_notification(
    order_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    client_ip: str = Depends(request_client_ip),
) -> NotificationDispatchResponse:
    apply_rate_limit(
        scope="resend_confirmation",
        key=f"{user_id}:{order_id}:{client_ip}",
        limit=settings.rate_limit_payment_submit_count,
        window_seconds=settings.rate_limit_payment_submit_window_seconds,
    )
    try:
        result = resend_order_confirmation(db, order_id=order_id, actor_user_id=user_id)
    except OrderNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OrderAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except OrderResendError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return NotificationDispatchResponse(success=result.success, channel_results=result.channel_results)
