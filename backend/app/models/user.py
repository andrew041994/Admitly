from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.event_staff import EventStaff
    from app.models.event_reminder_log import EventReminderLog
    from app.models.organizer_profile import OrganizerProfile
    from app.models.password_reset_token import PasswordResetToken
    from app.models.push_token import PushToken
    from app.models.ticket import Ticket
    from app.models.ticket_hold import TicketHold
    from app.models.ticket_transfer_invite import TicketTransferInvite
    from app.models.verification_token import EmailVerificationToken


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auth_provider: Mapped[str] = mapped_column(String(32), default="local", nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organizer_profile: Mapped["OrganizerProfile | None"] = relationship(
        back_populates="user", uselist=False
    )
    event_staff_assignments: Mapped[list["EventStaff"]] = relationship(
        back_populates="user", foreign_keys="EventStaff.user_id"
    )
    invited_staff_records: Mapped[list["EventStaff"]] = relationship(
        back_populates="invited_by_user", foreign_keys="EventStaff.invited_by_user_id"
    )

    ticket_holds: Mapped[list["TicketHold"]] = relationship(back_populates="user")
    event_reminder_logs: Mapped[list["EventReminderLog"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    push_tokens: Mapped[list["PushToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="user", foreign_keys="Ticket.user_id")
    purchased_tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="purchaser", foreign_keys="Ticket.purchaser_user_id"
    )
    owned_tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="owner", foreign_keys="Ticket.owner_user_id"
    )
    checked_in_tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="checked_in_by", foreign_keys="Ticket.checked_in_by_user_id"
    )
    voided_tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="voided_by", foreign_keys="Ticket.voided_by_user_id"
    )
    sent_transfer_invites: Mapped[list["TicketTransferInvite"]] = relationship(
        back_populates="sender", foreign_keys="TicketTransferInvite.sender_user_id"
    )
    received_transfer_invites: Mapped[list["TicketTransferInvite"]] = relationship(
        back_populates="recipient", foreign_keys="TicketTransferInvite.recipient_user_id"
    )
    accepted_transfer_invites: Mapped[list["TicketTransferInvite"]] = relationship(
        back_populates="accepted_by", foreign_keys="TicketTransferInvite.accepted_by_user_id"
    )
    revoked_transfer_invites: Mapped[list["TicketTransferInvite"]] = relationship(
        back_populates="revoked_by", foreign_keys="TicketTransferInvite.revoked_by_user_id"
    )
    email_verification_tokens: Mapped[list["EmailVerificationToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    password_reset_tokens: Mapped[list["PasswordResetToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
