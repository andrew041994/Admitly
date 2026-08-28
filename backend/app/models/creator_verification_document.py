from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class CreatorVerificationDocument(TimestampMixin, Base):
    """Internal tracking for temporary, private creator-verification material."""

    __tablename__ = "creator_verification_documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('uploading', 'pending', 'reviewed', 'deleted', 'cleanup_required')",
            name="ck_creator_verification_documents_status",
        ),
        CheckConstraint(
            "review_outcome IS NULL OR review_outcome IN "
            "('verified', 'rejected', 'expired', 'upload_failed')",
            name="ck_creator_verification_documents_review_outcome",
        ),
        Index(
            "uq_creator_verification_documents_active_user",
            "user_id",
            unique=True,
            postgresql_where=text("status IN ('uploading', 'pending', 'cleanup_required')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    storage_object_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploading", index=True)
    review_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cleanup_required_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cleanup_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_cleanup_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
