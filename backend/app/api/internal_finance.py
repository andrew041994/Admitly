from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_admin, get_current_user_id
from app.api.rate_limit import apply_rate_limit, request_client_ip
from app.core.config import settings
from app.db.session import get_db
from app.models.enums import PayoutStatus
from app.models.user import User
from app.schemas.finance import (
    InternalOrderFinanceResponse,
    ManualMMGVerificationRequest,
    ManualMMGVerificationResponse,
    PayoutStatusUpdateRequest,
    ReconcileOrderRequest,
)
from app.services.finance_reporting import (
    FinanceReportingAuthorizationError,
    FinanceReportingNotFoundError,
    mark_order_payout_status,
    mark_order_reconciled,
)
from app.services.orders import OrderNotPayableError
from app.services.payments import (
    PaymentAuthorizationError,
    PaymentError,
    PaymentMethodMismatchError,
    manually_verify_mmg_payment,
)

router = APIRouter(
    prefix="/internal/orders",
    tags=["internal-finance"],
    dependencies=[Depends(get_current_admin)],
)


def _require_admin(db: Session, *, user_id: int) -> None:
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None or not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")


def _to_order_finance_response(order) -> InternalOrderFinanceResponse:
    return InternalOrderFinanceResponse(
        order_id=order.id,
        reconciliation_status=order.reconciliation_status.value,
        reconciled_at=order.reconciled_at,
        reconciled_by_user_id=order.reconciled_by_user_id,
        reconciliation_note=order.reconciliation_note,
        payout_status=order.payout_status.value,
        payout_included_at=order.payout_included_at,
        payout_paid_at=order.payout_paid_at,
        payout_note=order.payout_note,
    )


@router.post("/{order_id}/reconcile", response_model=InternalOrderFinanceResponse)
def reconcile_order(
    order_id: int,
    payload: ReconcileOrderRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    client_ip: str = Depends(request_client_ip),
) -> InternalOrderFinanceResponse:
    _require_admin(db, user_id=user_id)
    apply_rate_limit(
        scope="admin_finance_reconcile",
        key=f"{user_id}:{order_id}:{client_ip}",
        limit=settings.rate_limit_admin_action_count,
        window_seconds=settings.rate_limit_admin_action_window_seconds,
    )
    try:
        order = mark_order_reconciled(db, order_id=order_id, actor_user_id=user_id, note=payload.note)
    except FinanceReportingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FinanceReportingAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    return _to_order_finance_response(order)


@router.post("/{order_id}/payout-status", response_model=InternalOrderFinanceResponse)
def update_order_payout_status(
    order_id: int,
    payload: PayoutStatusUpdateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    client_ip: str = Depends(request_client_ip),
) -> InternalOrderFinanceResponse:
    _require_admin(db, user_id=user_id)
    apply_rate_limit(
        scope="admin_finance_payout",
        key=f"{user_id}:{order_id}:{client_ip}",
        limit=settings.rate_limit_admin_action_count,
        window_seconds=settings.rate_limit_admin_action_window_seconds,
    )
    try:
        parsed_status = PayoutStatus(payload.payout_status)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid payout_status.") from exc

    try:
        order = mark_order_payout_status(
            db,
            order_id=order_id,
            actor_user_id=user_id,
            payout_status=parsed_status,
            note=payload.note,
        )
    except FinanceReportingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FinanceReportingAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    return _to_order_finance_response(order)


@router.post(
    "/{order_id}/payments/mmg/manual-verify",
    response_model=ManualMMGVerificationResponse,
)
def manually_verify_order_mmg_payment(
    order_id: int,
    payload: ManualMMGVerificationRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    client_ip: str = Depends(request_client_ip),
) -> ManualMMGVerificationResponse:
    _require_admin(db, user_id=user_id)
    apply_rate_limit(
        scope="admin_mmg_manual_verify",
        key=f"{user_id}:{order_id}:{client_ip}",
        limit=settings.rate_limit_admin_action_count,
        window_seconds=settings.rate_limit_admin_action_window_seconds,
    )
    try:
        order = manually_verify_mmg_payment(
            db,
            order_id=order_id,
            actor_user_id=user_id,
            payment_reference=payload.payment_reference,
            confirmed_amount=payload.confirmed_amount,
            confirmed_currency=payload.confirmed_currency,
            reason=payload.reason,
        )
        db.commit()
    except PaymentAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except PaymentMethodMismatchError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except OrderNotPayableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PaymentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ManualMMGVerificationResponse(
        order_id=order.id,
        order_reference=order.reference_code,
        status=order.status.value,
        payment_verification_status=order.payment_verification_status,
        payment_reference=order.payment_reference or "",
    )
