from datetime import datetime

from pydantic import BaseModel


class EventFinanceSummaryResponse(BaseModel):
    event_id: int
    event_status: str
    gross_sales_amount: float
    refunded_amount: float
    net_sales_amount: float
    completed_order_count: int
    refunded_order_count: int
    eligible_payout_amount: float
    reconciled_amount: float
    unreconciled_amount: float
    eligible_order_count: int
    reconciled_order_count: int
    unreconciled_order_count: int
    payout_included_amount: float
    payout_paid_amount: float
    currency: str
    generated_at: datetime


class EventFinanceOrderRowResponse(BaseModel):
    order_id: int
    buyer_user_id: int
    status: str
    refund_status: str
    reconciliation_status: str
    payout_status: str
    total_amount: float
    refunded_amount: float
    payout_eligible_amount: float
    currency: str
    payment_provider: str | None
    payment_method: str | None
    payment_reference: str | None
    created_at: datetime
    completed_at: datetime | None
    refunded_at: datetime | None
    reconciled_at: datetime | None


class OrganizerPayoutSummaryResponse(BaseModel):
    organizer_user_id: int
    total_gross_sales: float
    total_refunded: float
    total_net_sales: float
    total_payout_eligible: float
    total_reconciled: float
    total_unreconciled: float
    total_paid_out: float
    currency: str
    generated_at: datetime


class ReconcileOrderRequest(BaseModel):
    note: str | None = None


class PayoutStatusUpdateRequest(BaseModel):
    payout_status: str
    note: str | None = None


class InternalOrderFinanceResponse(BaseModel):
    order_id: int
    reconciliation_status: str
    reconciled_at: datetime | None
    reconciled_by_user_id: int | None
    reconciliation_note: str | None
    payout_status: str
    payout_included_at: datetime | None
    payout_paid_at: datetime | None
    payout_note: str | None
