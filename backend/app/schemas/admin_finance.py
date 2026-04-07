from datetime import datetime

from pydantic import BaseModel


class AdminFinanceSummaryResponse(BaseModel):
    gross_sales_amount: float
    refunded_amount: float
    dispute_amount: float
    discount_amount: float
    promo_discount_amount: float
    comp_amount: float
    platform_fee_amount: float
    organizer_net_amount: float
    settled_amount: float
    pending_payout_amount: float
    payout_eligible_amount: float
    refunded_order_count: int
    dispute_count: int
    promo_usage_count: int
    reconciliation_exception_count: int
    order_count: int
    currency: str
    date_from: datetime | None
    date_to: datetime | None
    generated_at: datetime


class AdminSettlementRowResponse(BaseModel):
    payout_status: str
    order_count: int
    gross_amount: float
    refunded_amount: float
    net_amount: float


class AdminRefundDisputeRowResponse(BaseModel):
    kind: str
    record_id: int
    order_id: int
    status: str
    amount: float
    created_at: datetime
    resolved_at: datetime | None
