from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.promo_code import PromoCode
    from app.models.user import User


class PromoCodeRedemption(TimestampMixin, Base):
    __tablename__ = "promo_code_redemptions"
    __table_args__ = (UniqueConstraint("order_id", name="uq_promo_code_redemptions_order_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    promo_code_id: Mapped[int] = mapped_column(ForeignKey("promo_codes.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    redeemed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    promo_code: Mapped["PromoCode"] = relationship(back_populates="redemptions")
    order: Mapped["Order"] = relationship(back_populates="promo_code_redemption")
    user: Mapped["User"] = relationship()
