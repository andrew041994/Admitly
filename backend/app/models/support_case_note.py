from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.support_case import SupportCase
    from app.models.user import User


class SupportCaseNote(TimestampMixin, Base):
    __tablename__ = "support_case_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    support_case_id: Mapped[int] = mapped_column(ForeignKey("support_cases.id"), nullable=False, index=True)
    author_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_system_note: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    support_case: Mapped["SupportCase"] = relationship(back_populates="notes")
    author_user: Mapped["User"] = relationship(foreign_keys=[author_user_id])
