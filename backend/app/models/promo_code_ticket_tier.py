from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.promo_code import PromoCode
    from app.models.ticket_tier import TicketTier


class PromoCodeTicketTier(TimestampMixin, Base):
    __tablename__ = "promo_code_ticket_tiers"
    __table_args__ = (UniqueConstraint("promo_code_id", "ticket_tier_id", name="uq_promo_code_ticket_tiers_pair"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    promo_code_id: Mapped[int] = mapped_column(ForeignKey("promo_codes.id", ondelete="CASCADE"), nullable=False, index=True)
    ticket_tier_id: Mapped[int] = mapped_column(ForeignKey("ticket_tiers.id", ondelete="CASCADE"), nullable=False, index=True)

    promo_code: Mapped["PromoCode"] = relationship(back_populates="tier_scopes")
    ticket_tier: Mapped["TicketTier"] = relationship(back_populates="promo_code_scopes")
