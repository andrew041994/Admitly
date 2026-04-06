from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.event_staff import EventStaff
    from app.models.organizer_profile import OrganizerProfile
    from app.models.ticket_hold import TicketHold


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    organizer_profile: Mapped["OrganizerProfile | None"] = relationship(
        back_populates="user", uselist=False
    )
    event_staff_assignments: Mapped[list["EventStaff"]] = relationship(
        back_populates="user", foreign_keys="EventStaff.user_id"
    )
    invited_staff_records: Mapped[list["EventStaff"]] = relationship(
        back_populates="invited_by_user", foreign_keys="EventStaff.invited_by_user_id"
    )

    ticket_holds: Mapped[list["TicketHold"]] = relationship()
