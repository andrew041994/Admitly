from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import MessageChannel, MessageDeliveryStatus, MessageTemplateType
from app.models.mixins import TimestampMixin
from app.models.sa_enum import db_enum

if TYPE_CHECKING:
    from app.models.user import User


class MessageDeliveryLog(TimestampMixin, Base):
    __tablename__ = "message_delivery_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    template_type: Mapped[MessageTemplateType] = mapped_column(
        db_enum(MessageTemplateType, name="message_template_type"),
        nullable=False,
        index=True,
    )
    channel: Mapped[MessageChannel] = mapped_column(
        db_enum(MessageChannel, name="message_channel"), nullable=False, index=True
    )
    status: Mapped[MessageDeliveryStatus] = mapped_column(
        db_enum(MessageDeliveryStatus, name="message_delivery_status"),
        nullable=False,
        index=True,
    )
    recipient_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    recipient_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    related_entity_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    related_entity_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    provider_reference_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    provider_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    is_manual_resend: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    resend_of_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("message_delivery_logs.id"), nullable=True, index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )

    recipient_user: Mapped["User | None"] = relationship(
        foreign_keys=[recipient_user_id]
    )
    actor_user: Mapped["User | None"] = relationship(foreign_keys=[actor_user_id])
    resend_of: Mapped["MessageDeliveryLog | None"] = relationship(
        remote_side=[id], uselist=False
    )
