from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import SupportCasePriority, SupportCaseStatus
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.support_case_note import SupportCaseNote
    from app.models.user import User


class SupportCase(TimestampMixin, Base):
    __tablename__ = "support_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    status: Mapped[SupportCaseStatus] = mapped_column(
        Enum(SupportCaseStatus, name="support_case_status"), nullable=False, default=SupportCaseStatus.OPEN, index=True
    )
    priority: Mapped[SupportCasePriority] = mapped_column(
        Enum(SupportCasePriority, name="support_case_priority"), nullable=False, default=SupportCasePriority.NORMAL
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="other")
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    assigned_to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped["Order"] = relationship(back_populates="support_cases")
    created_by_user: Mapped["User | None"] = relationship(foreign_keys=[created_by_user_id])
    assigned_to_user: Mapped["User | None"] = relationship(foreign_keys=[assigned_to_user_id])
    notes: Mapped[list["SupportCaseNote"]] = relationship(
        back_populates="support_case", cascade="all, delete-orphan", order_by="SupportCaseNote.created_at.asc()"
    )
