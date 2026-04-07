import csv
from datetime import datetime
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.ticket_holds import get_current_user_id
from app.db.session import get_db
from app.models.enums import PayoutStatus, ReconciliationStatus
from app.models.user import User
from app.schemas.admin_finance import (
    AdminFinanceSummaryResponse,
    AdminRefundDisputeRowResponse,
    AdminSettlementRowResponse,
)
from app.schemas.finance import EventFinanceOrderRowResponse
from app.services.finance_reporting import (
    get_admin_finance_summary,
    list_admin_finance_orders,
    list_admin_refund_dispute_rows,
    list_admin_settlement_rows,
)

router = APIRouter(prefix="/admin/finance", tags=["admin-finance"])


def _require_admin(db: Session, *, user_id: int) -> None:
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None or not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")


def _csv_response(*, filename: str, headers: list[str], rows: list[list[str]]) -> Response:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/summary", response_model=AdminFinanceSummaryResponse)
def get_admin_summary(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    event_id: int | None = Query(default=None),
    organizer_user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> AdminFinanceSummaryResponse:
    _require_admin(db, user_id=user_id)
    summary = get_admin_finance_summary(
        db,
        date_from=date_from,
        date_to=date_to,
        event_id=event_id,
        organizer_user_id=organizer_user_id,
    )
    return AdminFinanceSummaryResponse(
        gross_sales_amount=float(summary.gross_sales_amount),
        refunded_amount=float(summary.refunded_amount),
        dispute_amount=float(summary.dispute_amount),
        discount_amount=float(summary.discount_amount),
        promo_discount_amount=float(summary.promo_discount_amount),
        comp_amount=float(summary.comp_amount),
        platform_fee_amount=float(summary.platform_fee_amount),
        organizer_net_amount=float(summary.organizer_net_amount),
        settled_amount=float(summary.settled_amount),
        pending_payout_amount=float(summary.pending_payout_amount),
        payout_eligible_amount=float(summary.payout_eligible_amount),
        refunded_order_count=summary.refunded_order_count,
        dispute_count=summary.dispute_count,
        promo_usage_count=summary.promo_usage_count,
        reconciliation_exception_count=summary.reconciliation_exception_count,
        order_count=summary.order_count,
        currency=summary.currency,
        date_from=summary.date_from,
        date_to=summary.date_to,
        generated_at=summary.generated_at,
    )


@router.get("/orders", response_model=list[EventFinanceOrderRowResponse])
def list_admin_orders(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    event_id: int | None = Query(default=None),
    organizer_user_id: int | None = Query(default=None),
    payout_status: PayoutStatus | None = Query(default=None),
    reconciliation_status: ReconciliationStatus | None = Query(default=None),
    refund_status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[EventFinanceOrderRowResponse]:
    _require_admin(db, user_id=user_id)
    rows = list_admin_finance_orders(
        db,
        date_from=date_from,
        date_to=date_to,
        event_id=event_id,
        organizer_user_id=organizer_user_id,
        payout_status=payout_status,
        reconciliation_status=reconciliation_status,
        refund_status=refund_status,
        limit=limit,
        offset=offset,
    )
    return [
        EventFinanceOrderRowResponse(
            order_id=row.order_id,
            buyer_user_id=row.buyer_user_id,
            status=row.status,
            refund_status=row.refund_status,
            reconciliation_status=row.reconciliation_status,
            payout_status=row.payout_status,
            subtotal_amount=float(row.subtotal_amount),
            discount_amount=float(row.discount_amount),
            total_amount=float(row.total_amount),
            is_comp=row.is_comp,
            pricing_source=row.pricing_source,
            refunded_amount=float(row.refunded_amount),
            payout_eligible_amount=float(row.payout_eligible_amount),
            currency=row.currency,
            payment_provider=row.payment_provider,
            payment_method=row.payment_method,
            payment_reference=row.payment_reference,
            created_at=row.created_at,
            completed_at=row.completed_at,
            refunded_at=row.refunded_at,
            reconciled_at=row.reconciled_at,
        )
        for row in rows
    ]


@router.get("/settlements", response_model=list[AdminSettlementRowResponse])
def list_admin_settlements(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    event_id: int | None = Query(default=None),
    organizer_user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[AdminSettlementRowResponse]:
    _require_admin(db, user_id=user_id)
    rows = list_admin_settlement_rows(
        db,
        date_from=date_from,
        date_to=date_to,
        event_id=event_id,
        organizer_user_id=organizer_user_id,
    )
    return [
        AdminSettlementRowResponse(
            payout_status=row.payout_status,
            order_count=row.order_count,
            gross_amount=float(row.gross_amount),
            refunded_amount=float(row.refunded_amount),
            net_amount=float(row.net_amount),
        )
        for row in rows
    ]


@router.get("/refund-disputes", response_model=list[AdminRefundDisputeRowResponse])
def list_admin_refund_disputes(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    event_id: int | None = Query(default=None),
    organizer_user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[AdminRefundDisputeRowResponse]:
    _require_admin(db, user_id=user_id)
    rows = list_admin_refund_dispute_rows(
        db,
        date_from=date_from,
        date_to=date_to,
        event_id=event_id,
        organizer_user_id=organizer_user_id,
    )
    return [
        AdminRefundDisputeRowResponse(
            kind=row.kind,
            record_id=row.record_id,
            order_id=row.order_id,
            status=row.status,
            amount=float(row.amount),
            created_at=row.created_at,
            resolved_at=row.resolved_at,
        )
        for row in rows
    ]


@router.get("/orders/export.csv")
def export_admin_orders_csv(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    event_id: int | None = Query(default=None),
    organizer_user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> Response:
    _require_admin(db, user_id=user_id)
    rows = list_admin_finance_orders(db, date_from=date_from, date_to=date_to, event_id=event_id, organizer_user_id=organizer_user_id, limit=10000)
    headers = [
        "order_id", "event_id", "buyer_user_id", "status", "refund_status", "reconciliation_status", "payout_status", "subtotal_amount", "discount_amount", "total_amount", "refunded_amount", "payout_eligible_amount", "currency", "paid_at"
    ]
    csv_rows = [[
        str(row.order_id), "", str(row.buyer_user_id), row.status, row.refund_status, row.reconciliation_status, row.payout_status,
        f"{row.subtotal_amount:.2f}", f"{row.discount_amount:.2f}", f"{row.total_amount:.2f}", f"{row.refunded_amount:.2f}", f"{row.payout_eligible_amount:.2f}", row.currency, row.completed_at.isoformat() if row.completed_at else ""
    ] for row in rows]
    return _csv_response(filename="finance-orders.csv", headers=headers, rows=csv_rows)


@router.get("/settlements/export.csv")
def export_admin_settlements_csv(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    event_id: int | None = Query(default=None),
    organizer_user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> Response:
    _require_admin(db, user_id=user_id)
    rows = list_admin_settlement_rows(db, date_from=date_from, date_to=date_to, event_id=event_id, organizer_user_id=organizer_user_id)
    headers = ["payout_status", "order_count", "gross_amount", "refunded_amount", "net_amount"]
    csv_rows = [[row.payout_status, str(row.order_count), f"{row.gross_amount:.2f}", f"{row.refunded_amount:.2f}", f"{row.net_amount:.2f}"] for row in rows]
    return _csv_response(filename="finance-settlements.csv", headers=headers, rows=csv_rows)


@router.get("/refund-disputes/export.csv")
def export_admin_refund_disputes_csv(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    event_id: int | None = Query(default=None),
    organizer_user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> Response:
    _require_admin(db, user_id=user_id)
    rows = list_admin_refund_dispute_rows(db, date_from=date_from, date_to=date_to, event_id=event_id, organizer_user_id=organizer_user_id)
    headers = ["kind", "record_id", "order_id", "status", "amount", "created_at", "resolved_at"]
    csv_rows = [[row.kind, str(row.record_id), str(row.order_id), row.status, f"{row.amount:.2f}", row.created_at.isoformat(), row.resolved_at.isoformat() if row.resolved_at else ""] for row in rows]
    return _csv_response(filename="finance-refund-disputes.csv", headers=headers, rows=csv_rows)
