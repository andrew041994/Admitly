from sqlalchemy import Boolean, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import EventStaffRole
from app.models.mixins import TimestampMixin


class EventStaff(TimestampMixin, Base):
    __tablename__ = "event_staff"
    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_event_staff_event_id_user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[EventStaffRole] = mapped_column(
        Enum(EventStaffRole, name="event_staff_role"),
        nullable=False,
        default=EventStaffRole.CHECKIN,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    invited_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )

    event = relationship("Event", back_populates="staff")
    user = relationship("User", foreign_keys=[user_id], back_populates="event_staff_assignments")
    invited_by_user = relationship(
        "User", foreign_keys=[invited_by_user_id], back_populates="invited_staff_records"
    )
