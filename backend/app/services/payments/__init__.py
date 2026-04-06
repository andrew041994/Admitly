from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.enums import OrderStatus
from app.models.order import Order
from app.services.orders import (
    OrderNotPayableError,
    complete_paid_order,
    get_order_with_holds,
    validate_order_still_payable,
)
from app.services.payments.mmg import (
    MMGProviderError,
    MMGVerificationResult,
    create_agent_payment_reference,
    create_checkout_for_order,
    initiate_refund_with_provider,
    parse_checkout_callback,
    validate_mmg_provider_config,
    verify_agent_payment_reference,
    verify_refund_status,
)
from app.services.ticket_holds import get_guyana_now


class PaymentError(ValueError):
    """Base payment flow error."""


class PaymentAuthorizationError(PaymentError):
    """Raised when user attempts payment on someone else's order."""


class PaymentMethodMismatchError(PaymentError):
    """Raised when payment method does not match expected rail."""


@dataclass(slots=True)
class OrderPaymentSnapshot:
    order_id: int
    provider: str
    payment_method: str
    payment_reference: str
    amount: Decimal
    currency: str
    status: str
    payment_verification_status: str
    checkout_url: str | None = None
    instructions: str | None = None
    message: str | None = None


def _load_order_for_payment(db: Session, *, order_id: int) -> Order:
    order = get_order_with_holds(db, order_id=order_id)
    if order is None:
        raise PaymentError("Order not found.")
    return order


def _assert_order_owner(order: Order, *, user_id: int) -> None:
    if order.user_id != user_id:
        raise PaymentAuthorizationError("Order does not belong to the authenticated user.")


def create_mmg_checkout_for_order(db: Session, *, order_id: int, user_id: int) -> OrderPaymentSnapshot:
    order = _load_order_for_payment(db, order_id=order_id)
    _assert_order_owner(order, user_id=user_id)
    validate_mmg_provider_config()
    validate_order_still_payable(order)

    if order.payment_method == "mmg_agent":
        raise PaymentMethodMismatchError("Order has already started MMG agent checkout.")

    checkout = create_checkout_for_order(
        order_id=order.id,
        amount=f"{order.total_amount:.2f}",
        currency=order.currency,
        existing_reference=order.payment_reference if order.payment_method == "mmg_checkout" else None,
        existing_checkout_url=order.payment_checkout_url if order.payment_method == "mmg_checkout" else None,
    )

    order.payment_provider = "mmg"
    order.payment_method = "mmg_checkout"
    order.payment_reference = checkout.payment_reference
    order.payment_checkout_url = checkout.checkout_url
    order.payment_verification_status = "pending"
    db.flush()

    return OrderPaymentSnapshot(
        order_id=order.id,
        provider="mmg",
        payment_method=order.payment_method,
        payment_reference=order.payment_reference,
        checkout_url=order.payment_checkout_url,
        amount=order.total_amount,
        currency=order.currency,
        status=order.status.value,
        payment_verification_status=order.payment_verification_status,
    )


def create_mmg_agent_checkout_for_order(db: Session, *, order_id: int, user_id: int) -> OrderPaymentSnapshot:
    order = _load_order_for_payment(db, order_id=order_id)
    _assert_order_owner(order, user_id=user_id)
    validate_mmg_provider_config()
    validate_order_still_payable(order)

    if order.payment_method == "mmg_checkout":
        raise PaymentMethodMismatchError("Order has already started MMG checkout.")

    payment_reference = create_agent_payment_reference(
        order_id=order.id,
        existing_reference=order.payment_reference if order.payment_method == "mmg_agent" else None,
    )

    order.payment_provider = "mmg"
    order.payment_method = "mmg_agent"
    order.payment_reference = payment_reference
    order.payment_checkout_url = None
    order.payment_verification_status = "pending"
    db.flush()

    return OrderPaymentSnapshot(
        order_id=order.id,
        provider="mmg",
        payment_method=order.payment_method,
        payment_reference=order.payment_reference,
        amount=order.total_amount,
        currency=order.currency,
        status=order.status.value,
        payment_verification_status=order.payment_verification_status,
        instructions="Pay at any MMG agent, then submit this reference in Admitly.",
    )


def submit_mmg_agent_payment(
    db: Session,
    *,
    order_id: int,
    user_id: int,
    submitted_reference_code: str,
) -> OrderPaymentSnapshot:
    order = _load_order_for_payment(db, order_id=order_id)
    _assert_order_owner(order, user_id=user_id)
    validate_order_still_payable(order)

    if order.payment_method != "mmg_agent" or not order.payment_reference:
        raise PaymentMethodMismatchError("Order is not configured for MMG agent payments.")

    order.payment_submitted_at = get_guyana_now()

    outcome = verify_agent_payment_reference(
        order_reference=order.payment_reference,
        submitted_reference=submitted_reference_code,
    )

    order.payment_verification_status = outcome.status.value

    if outcome.status == MMGVerificationResult.VERIFIED:
        order.payment_verification_status = "verified"
        complete_paid_order(db, order, paid_at=get_guyana_now(), payment_reference=order.payment_reference)
    elif outcome.status == MMGVerificationResult.REJECTED:
        order.status = OrderStatus.PENDING

    db.flush()
    return OrderPaymentSnapshot(
        order_id=order.id,
        provider="mmg",
        payment_method=order.payment_method,
        payment_reference=order.payment_reference,
        amount=order.total_amount,
        currency=order.currency,
        status=order.status.value,
        payment_verification_status=order.payment_verification_status,
        message=outcome.message,
    )


def mark_agent_payment_verified(db: Session, *, order_id: int, payment_reference: str | None = None) -> Order:
    order = _load_order_for_payment(db, order_id=order_id)
    if order.payment_method != "mmg_agent":
        raise PaymentMethodMismatchError("Order is not configured for MMG agent payments.")

    order.payment_verification_status = "verified"
    complete_paid_order(db, order, paid_at=get_guyana_now(), payment_reference=payment_reference)
    db.flush()
    return order


def handle_mmg_callback(db: Session, *, payload: dict) -> OrderPaymentSnapshot:
    parsed = parse_checkout_callback(payload)
    order = (
        db.execute(
            select(Order)
            .options(joinedload(Order.ticket_holds))
            .where(Order.payment_reference == parsed.payment_reference)
        )
        .scalars()
        .first()
    )
    if order is None:
        raise PaymentError("Order not found for payment reference.")

    if parsed.paid:
        order.payment_verification_status = "verified"
        complete_paid_order(db, order, paid_at=get_guyana_now(), payment_reference=parsed.payment_reference)
    else:
        order.payment_verification_status = "pending_verification"

    db.flush()
    return OrderPaymentSnapshot(
        order_id=order.id,
        provider="mmg",
        payment_method=order.payment_method or "mmg_checkout",
        payment_reference=order.payment_reference or parsed.payment_reference,
        amount=order.total_amount,
        currency=order.currency,
        status=order.status.value,
        payment_verification_status=order.payment_verification_status,
    )


def mark_refund_recorded(db: Session, *, order: Order) -> str:
    outcome = initiate_refund_with_provider(order_id=order.id, payment_reference=order.payment_reference)
    if outcome.status == "failed":
        order.refund_status = "failed"
    elif outcome.status == "pending":
        order.refund_status = "pending"
    else:
        order.refund_status = "refunded"
    db.flush()
    return order.refund_status


def refresh_refund_status(db: Session, *, order: Order) -> str:
    outcome = verify_refund_status(provider_reference=order.payment_reference)
    if outcome.status in {"refunded", "pending", "failed"}:
        order.refund_status = outcome.status
        db.flush()
    return order.refund_status


__all__ = [
    "MMGProviderError",
    "OrderNotPayableError",
    "PaymentAuthorizationError",
    "PaymentError",
    "PaymentMethodMismatchError",
    "OrderPaymentSnapshot",
    "create_mmg_checkout_for_order",
    "create_mmg_agent_checkout_for_order",
    "submit_mmg_agent_payment",
    "mark_agent_payment_verified",
    "handle_mmg_callback",
    "mark_refund_recorded",
    "refresh_refund_status",
]
