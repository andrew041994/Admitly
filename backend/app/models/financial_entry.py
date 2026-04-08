from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import FinancialEntryType
from app.models.mixins import TimestampMixin
from app.models.sa_enum import db_enum


class FinancialEntry(TimestampMixin, Base):
    __tablename__ = "financial_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id"), nullable=False, index=True
    )
    refund_id: Mapped[int] = mapped_column(
        ForeignKey("refunds.id"), nullable=False, index=True
    )
    organizer_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizer_profiles.id"), nullable=True, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    entry_type: Mapped[FinancialEntryType] = mapped_column(
        db_enum(FinancialEntryType, name="financial_entry_type"),
        nullable=False,
        index=True,
    )
