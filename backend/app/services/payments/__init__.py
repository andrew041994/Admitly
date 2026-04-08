from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.enums import OrderStatus
from app.models.order import Order
from app.models.payment_attempt import PaymentAttempt
from app.services.orders import (
    OrderNotPayableError,
    complete_paid_order,
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

logger = logging.getLogger(__name__)


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


def _record_payment_attempt(
    db: Session,
    *,
    order: Order,
    payment_method: str,
    status: str,
    verification_status: str,
    provider_reference: str | None = None,
    request_payload: dict | None = None,
    response_payload: dict | None = None,
) -> None:
    db.add(
        PaymentAttempt(
            order_id=order.id,
            provider="mmg",
            payment_method=payment_method,
            status=status,
            verification_status=verification_status,
            provider_reference=provider_reference,
            request_payload=json.dumps(request_payload) if request_payload else None,
            response_payload=json.dumps(response_payload) if response_payload else None,
        )
    )


def _load_order_for_payment(db: Session, *, order_id: int) -> Order:
    order = (
        db.execute(
            select(Order)
            .options(joinedload(Order.ticket_holds), joinedload(Order.order_items), joinedload(Order.tickets))
            .where(Order.id == order_id)
            .with_for_update()
        )
        .unique()
        .scalar_one_or_none()
    )
    if order is None:
        raise PaymentError("Order not found.")
    return order


def _assert_order_owner(order: Order, *, user_id: int) -> None:
    if order.user_id != user_id:
        raise PaymentAuthorizationError("Order does not belong to the authenticated user.")


def _derive_reference_now_from_order(order: Order) -> datetime:
    first_hold = order.ticket_holds[0].expires_at
    if first_hold.tzinfo is None:
        first_hold = first_hold.replace(tzinfo=timezone.utc)
    return first_hold.astimezone(get_guyana_now().tzinfo) - timedelta(minutes=1)


def create_mmg_checkout_for_order(db: Session, *, order_id: int, user_id: int) -> OrderPaymentSnapshot:
    tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
    with tx_ctx:
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
        order.status = OrderStatus.AWAITING_PAYMENT
        order.payment_verification_status = "pending"

        _record_payment_attempt(
            db,
            order=order,
            payment_method="mmg_checkout",
            status=order.status.value,
            verification_status=order.payment_verification_status,
            provider_reference=order.payment_reference,
            response_payload={"checkout_url": order.payment_checkout_url},
        )
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
    tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
    with tx_ctx:
        order = _load_order_for_payment(db, order_id=order_id)
        _assert_order_owner(order, user_id=user_id)
        validate_mmg_provider_config()
        reference_now = _derive_reference_now_from_order(order)
        validate_order_still_payable(order, now=reference_now)

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
        order.status = OrderStatus.AWAITING_PAYMENT
        order.payment_verification_status = "pending"

        _record_payment_attempt(
            db,
            order=order,
            payment_method="mmg_agent",
            status=order.status.value,
            verification_status=order.payment_verification_status,
            provider_reference=order.payment_reference,
        )
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
            instructions="Pay at any MMG agent, then tap Complete Payment in Admitly.",
        )


def submit_mmg_agent_payment(
    db: Session,
    *,
    order_id: int,
    user_id: int,
    submitted_reference_code: str,
) -> OrderPaymentSnapshot:
    tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
    with tx_ctx:
        order = _load_order_for_payment(db, order_id=order_id)
        _assert_order_owner(order, user_id=user_id)
        if order.status == OrderStatus.COMPLETED and order.payment_verification_status == "verified":
            logger.info("Ignoring duplicate MMG agent submit for finalized order", extra={"order_id": order.id})
            return OrderPaymentSnapshot(
                order_id=order.id,
                provider="mmg",
                payment_method=order.payment_method or "mmg_agent",
                payment_reference=order.payment_reference or "",
                amount=order.total_amount,
                currency=order.currency,
                status=order.status.value,
                payment_verification_status=order.payment_verification_status,
                message="Payment already verified.",
            )

        validate_order_still_payable(order)

        if order.payment_method != "mmg_agent" or not order.payment_reference:
            raise PaymentMethodMismatchError("Order is not configured for MMG agent payments.")

        order.payment_submitted_at = get_guyana_now()
        order.status = OrderStatus.PAYMENT_SUBMITTED

        outcome = verify_agent_payment_reference(
            order_reference=order.payment_reference,
            submitted_reference=submitted_reference_code,
        )

        order.payment_verification_status = outcome.status.value

        if outcome.status == MMGVerificationResult.VERIFIED:
            order.payment_verification_status = "verified"
            complete_paid_order(db, order, paid_at=get_guyana_now(), payment_reference=order.payment_reference)
        elif outcome.status == MMGVerificationResult.REJECTED:
            order.status = OrderStatus.FAILED

        _record_payment_attempt(
            db,
            order=order,
            payment_method="mmg_agent",
            status=order.status.value,
            verification_status=order.payment_verification_status,
            provider_reference=order.payment_reference,
            request_payload={"submitted_reference_code": submitted_reference_code},
            response_payload={"message": outcome.message},
        )
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
    tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
    with tx_ctx:
        order = _load_order_for_payment(db, order_id=order_id)
        if order.payment_method != "mmg_agent":
            raise PaymentMethodMismatchError("Order is not configured for MMG agent payments.")

        order.payment_verification_status = "verified"
        complete_paid_order(db, order, paid_at=get_guyana_now(), payment_reference=payment_reference)
        db.flush()
        return order


def handle_mmg_callback(db: Session, *, payload: dict) -> OrderPaymentSnapshot:
    parsed = parse_checkout_callback(payload)
    tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
    with tx_ctx:
        order = (
            db.execute(
                select(Order)
                .options(joinedload(Order.ticket_holds), joinedload(Order.order_items), joinedload(Order.tickets))
                .where(Order.payment_reference == parsed.payment_reference)
                .with_for_update()
            )
            .unique()
            .scalar_one_or_none()
        )
        if order is None:
            raise PaymentError("Order not found for payment reference.")

        if parsed.paid:
            if order.status == OrderStatus.COMPLETED and order.payment_verification_status == "verified":
                logger.info("Duplicate paid callback ignored for finalized order", extra={"order_id": order.id})
            else:
                order.payment_verification_status = "verified"
                complete_paid_order(db, order, paid_at=get_guyana_now(), payment_reference=parsed.payment_reference)
        else:
            if order.status == OrderStatus.COMPLETED and order.payment_verification_status == "verified":
                logger.info("Out-of-order unpaid callback ignored for finalized order", extra={"order_id": order.id})
            else:
                order.status = OrderStatus.PAYMENT_SUBMITTED
                order.payment_verification_status = "pending_verification"

        _record_payment_attempt(
            db,
            order=order,
            payment_method=order.payment_method or "mmg_checkout",
            status=order.status.value,
            verification_status=order.payment_verification_status,
            provider_reference=order.payment_reference or parsed.payment_reference,
            response_payload=payload,
        )
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
