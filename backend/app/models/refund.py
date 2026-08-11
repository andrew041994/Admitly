from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import RefundReason, RefundStatus
from app.models.mixins import TimestampMixin
from app.models.sa_enum import db_enum

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.user import User


class Refund(TimestampMixin, Base):
    __tablename__ = "refunds"
    __table_args__ = (
        UniqueConstraint(
            "payment_provider",
            "provider_refund_reference",
            name="uq_refunds_provider_reference",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    approved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[RefundStatus] = mapped_column(
        db_enum(RefundStatus, name="refund_status_enum"),
        nullable=False,
        default=RefundStatus.PENDING,
        index=True,
    )
    reason: Mapped[RefundReason] = mapped_column(
        db_enum(RefundReason, name="refund_reason"), nullable=False
    )
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payment_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_refund_reference: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    provider_status: Mapped[str] = mapped_column(
        String(64), nullable=False, default="not_submitted", server_default="not_submitted"
    )
    provider_submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    provider_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    order: Mapped["Order"] = relationship()
    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    approved_by_user: Mapped["User | None"] = relationship(
        foreign_keys=[approved_by_user_id]
    )
