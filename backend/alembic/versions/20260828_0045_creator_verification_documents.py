"""Add temporary private creator verification document tracking.

Revision ID: 20260828_0045
Revises: 20260812_0044
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260828_0045"
down_revision: str | None = "20260812_0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "creator_verification_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("storage_object_key", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("review_outcome", sa.String(length=32), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleanup_required_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleanup_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_cleanup_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('uploading', 'pending', 'reviewed', 'deleted', 'cleanup_required')",
            name="ck_creator_verification_documents_status",
        ),
        sa.CheckConstraint(
            "review_outcome IS NULL OR review_outcome IN "
            "('verified', 'rejected', 'expired', 'upload_failed')",
            name="ck_creator_verification_documents_review_outcome",
        ),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_object_key"),
    )
    op.create_index(
        op.f("ix_creator_verification_documents_reviewed_by_user_id"),
        "creator_verification_documents",
        ["reviewed_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_creator_verification_documents_status"),
        "creator_verification_documents",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_creator_verification_documents_user_id"),
        "creator_verification_documents",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "uq_creator_verification_documents_active_user",
        "creator_verification_documents",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('uploading', 'pending', 'cleanup_required')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_creator_verification_documents_active_user",
        table_name="creator_verification_documents",
        postgresql_where=sa.text("status IN ('uploading', 'pending', 'cleanup_required')"),
    )
    op.drop_index(
        op.f("ix_creator_verification_documents_user_id"),
        table_name="creator_verification_documents",
    )
    op.drop_index(
        op.f("ix_creator_verification_documents_status"),
        table_name="creator_verification_documents",
    )
    op.drop_index(
        op.f("ix_creator_verification_documents_reviewed_by_user_id"),
        table_name="creator_verification_documents",
    )
    op.drop_table("creator_verification_documents")
