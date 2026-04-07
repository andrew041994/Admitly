from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.ticket_holds import get_current_user_id
from app.db.session import get_db
from app.models.enums import PayoutStatus
from app.models.user import User
from app.schemas.finance import InternalOrderFinanceResponse, PayoutStatusUpdateRequest, ReconcileOrderRequest
from app.services.finance_reporting import (
    FinanceReportingAuthorizationError,
    FinanceReportingNotFoundError,
    mark_order_payout_status,
    mark_order_reconciled,
)

router = APIRouter(prefix="/internal/orders", tags=["internal-finance"])


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
) -> InternalOrderFinanceResponse:
    _require_admin(db, user_id=user_id)
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
) -> InternalOrderFinanceResponse:
    _require_admin(db, user_id=user_id)
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
