from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class WebhookDelivery(TimestampMixin, Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        UniqueConstraint("endpoint_id", "event_id", "attempt_number", name="uq_webhook_delivery_attempt"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint_id: Mapped[int] = mapped_column(ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), index=True, nullable=False)
    event_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(24), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    next_retry_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="automatic_initial")
    redelivery_of_delivery_id: Mapped[int | None] = mapped_column(ForeignKey("webhook_deliveries.id", ondelete="SET NULL"), nullable=True)
