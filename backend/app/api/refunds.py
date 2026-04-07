from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.ticket_holds import get_current_user_id
from app.db.session import get_db
from app.models.enums import DisputeStatus, RefundReason, RefundStatus
from app.models.user import User
from sqlalchemy import select
from app.schemas.refunds import (
    DisputeCreateRequest,
    DisputeRejectRequest,
    DisputeResolveRequest,
    DisputeResponse,
    RefundApproveRequest,
    RefundRejectRequest,
    RefundRequestCreate,
    RefundResponse,
)
from app.services.refunds import (
    DisputeNotFoundError,
    DisputeValidationError,
    RefundAuthorizationError,
    RefundNotFoundError,
    RefundValidationError,
    list_disputes,
    list_refunds,
    list_user_refunds,
    approve_refund,
    reject_dispute,
    reject_refund,
    request_refund,
    resolve_dispute,
    submit_dispute,
)

router = APIRouter(tags=["refunds"])

def _require_admin(db: Session, *, user_id: int) -> None:
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None or not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")


def _to_refund_response(refund) -> RefundResponse:
    return RefundResponse(
        id=refund.id,
        order_id=refund.order_id,
        user_id=refund.user_id,
        amount=float(refund.amount),
        status=refund.status.value,
        reason=refund.reason.value,
        admin_notes=refund.admin_notes,
        processed_at=refund.processed_at,
        created_at=refund.created_at,
    )


def _to_dispute_response(dispute) -> DisputeResponse:
    return DisputeResponse(
        id=dispute.id,
        order_id=dispute.order_id,
        user_id=dispute.user_id,
        message=dispute.message,
        status=dispute.status.value,
        admin_notes=dispute.admin_notes,
        resolution=dispute.resolution,
        resolved_at=dispute.resolved_at,
        created_at=dispute.created_at,
    )


@router.post("/refunds/request", response_model=RefundResponse, status_code=status.HTTP_201_CREATED)
def create_refund_request(
    payload: RefundRequestCreate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> RefundResponse:
    try:
        reason = RefundReason(payload.reason)
        refund = request_refund(
            db,
            user_id=user_id,
            order_id=payload.order_id,
            reason=reason,
            amount=Decimal(str(payload.amount)) if payload.amount is not None else None,
            note=payload.note,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid refund reason.") from exc
    except RefundNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RefundAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except RefundValidationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _to_refund_response(refund)


@router.get("/refunds/my", response_model=list[RefundResponse])
def get_my_refunds(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[RefundResponse]:
    return [_to_refund_response(refund) for refund in list_user_refunds(db, user_id=user_id)]


@router.post("/disputes", response_model=DisputeResponse, status_code=status.HTTP_201_CREATED)
def create_dispute(
    payload: DisputeCreateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> DisputeResponse:
    try:
        dispute = submit_dispute(db, user_id=user_id, order_id=payload.order_id, message=payload.message)
        db.commit()
    except (DisputeNotFoundError,) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RefundAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except DisputeValidationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _to_dispute_response(dispute)


@router.get("/admin/refunds", response_model=list[RefundResponse])
def admin_list_refunds(
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[RefundResponse]:
    _require_admin(db, user_id=user_id)
    parsed = None
    if status_filter is not None:
        try:
            parsed = RefundStatus(status_filter)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid refund status.") from exc
    try:
        refunds = list_refunds(db, status=parsed)
    except RefundAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return [_to_refund_response(refund) for refund in refunds]


@router.post("/admin/refunds/{refund_id}/approve", response_model=RefundResponse)
def admin_approve_refund(
    refund_id: int,
    payload: RefundApproveRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> RefundResponse:
    _require_admin(db, user_id=user_id)
    try:
        refund = approve_refund(
            db,
            refund_id=refund_id,
            actor_user_id=user_id,
            amount=Decimal(str(payload.amount)) if payload.amount is not None else None,
            admin_notes=payload.admin_notes,
        )
        db.commit()
    except RefundAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except RefundNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RefundValidationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _to_refund_response(refund)


@router.post("/admin/refunds/{refund_id}/reject", response_model=RefundResponse)
def admin_reject_refund(
    refund_id: int,
    payload: RefundRejectRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> RefundResponse:
    _require_admin(db, user_id=user_id)
    try:
        refund = reject_refund(db, refund_id=refund_id, actor_user_id=user_id, admin_notes=payload.admin_notes)
        db.commit()
    except RefundAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except RefundNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RefundValidationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _to_refund_response(refund)


@router.get("/admin/disputes", response_model=list[DisputeResponse])
def admin_list_disputes(
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[DisputeResponse]:
    _require_admin(db, user_id=user_id)
    parsed = None
    if status_filter is not None:
        try:
            parsed = DisputeStatus(status_filter)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid dispute status.") from exc

    disputes = list_disputes(db, status=parsed)
    return [_to_dispute_response(dispute) for dispute in disputes]


@router.post("/admin/disputes/{dispute_id}/resolve", response_model=DisputeResponse)
def admin_resolve_dispute(
    dispute_id: int,
    payload: DisputeResolveRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> DisputeResponse:
    parsed_reason = None
    if payload.refund_reason is not None:
        try:
            parsed_reason = RefundReason(payload.refund_reason)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid refund reason.") from exc
    _require_admin(db, user_id=user_id)
    try:
        dispute = resolve_dispute(
            db,
            dispute_id=dispute_id,
            actor_user_id=user_id,
            resolution=payload.resolution,
            admin_notes=payload.admin_notes,
            refund_amount=Decimal(str(payload.refund_amount)) if payload.refund_amount is not None else None,
            refund_reason=parsed_reason,
        )
        db.commit()
    except RefundAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except DisputeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (DisputeValidationError, RefundValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return _to_dispute_response(dispute)


@router.post("/admin/disputes/{dispute_id}/reject", response_model=DisputeResponse)
def admin_reject_dispute(
    dispute_id: int,
    payload: DisputeRejectRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> DisputeResponse:
    _require_admin(db, user_id=user_id)
    try:
        dispute = reject_dispute(db, dispute_id=dispute_id, actor_user_id=user_id, admin_notes=payload.admin_notes)
        db.commit()
    except RefundAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except DisputeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DisputeValidationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _to_dispute_response(dispute)
