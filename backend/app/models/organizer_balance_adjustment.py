from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Enum, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import BalanceAdjustmentType
from app.models.mixins import TimestampMixin


class OrganizerBalanceAdjustment(TimestampMixin, Base):
    __tablename__ = "organizer_balance_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    organizer_id: Mapped[int] = mapped_column(ForeignKey("organizer_profiles.id"), nullable=False, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    refund_id: Mapped[int] = mapped_column(ForeignKey("refunds.id"), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    adjustment_type: Mapped[BalanceAdjustmentType] = mapped_column(
        Enum(BalanceAdjustmentType, name="balance_adjustment_type"), nullable=False, index=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
