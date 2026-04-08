from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import PromoCodeDiscountType
from app.models.mixins import TimestampMixin
from app.models.sa_enum import db_enum

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.order import Order
    from app.models.promo_code_redemption import PromoCodeRedemption
    from app.models.promo_code_ticket_tier import PromoCodeTicketTier


class PromoCode(TimestampMixin, Base):
    __tablename__ = "promo_codes"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "code_normalized",
            name="uq_promo_codes_event_id_code_normalized",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    code_normalized: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    discount_type: Mapped[PromoCodeDiscountType] = mapped_column(
        db_enum(PromoCodeDiscountType, name="promo_code_discount_type"), nullable=False
    )
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    max_total_redemptions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_redemptions_per_user: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_order_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    applies_to_all_tiers: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    event: Mapped["Event"] = relationship(back_populates="promo_codes")
    redemptions: Mapped[list["PromoCodeRedemption"]] = relationship(
        back_populates="promo_code", cascade="all, delete-orphan"
    )
    tier_scopes: Mapped[list["PromoCodeTicketTier"]] = relationship(
        back_populates="promo_code", cascade="all, delete-orphan"
    )
    orders: Mapped[list["Order"]] = relationship(back_populates="promo_code")
