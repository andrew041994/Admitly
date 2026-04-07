"""Phase 19 admin support cases and action audit

Revision ID: 20260407_0018
Revises: 20260407_0017
Create Date: 2026-04-07 00:18:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260407_0018"
down_revision = "20260407_0017"
branch_labels = None
depends_on = None


support_case_status = sa.Enum(
    "open",
    "investigating",
    "waiting_on_customer",
    "waiting_on_payment_provider",
    "resolved",
    "closed",
    name="support_case_status",
)

support_case_priority = sa.Enum("low", "normal", "high", "urgent", name="support_case_priority")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        support_case_status.create(bind, checkfirst=True)
        support_case_priority.create(bind, checkfirst=True)

    op.create_table(
        "support_cases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("status", support_case_status, nullable=False, server_default="open"),
        sa.Column("priority", support_case_priority, nullable=False, server_default="normal"),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="other"),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("assigned_to_user_id", sa.Integer(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], name=op.f("fk_support_cases_assigned_to_user_id_users")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_support_cases_created_by_user_id_users")),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name=op.f("fk_support_cases_order_id_orders")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_cases")),
    )
    op.create_index(op.f("ix_support_cases_order_id"), "support_cases", ["order_id"], unique=False)
    op.create_index(op.f("ix_support_cases_status"), "support_cases", ["status"], unique=False)
    op.create_index(op.f("ix_support_cases_created_by_user_id"), "support_cases", ["created_by_user_id"], unique=False)
    op.create_index(op.f("ix_support_cases_assigned_to_user_id"), "support_cases", ["assigned_to_user_id"], unique=False)

    op.create_table(
        "support_case_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("support_case_id", sa.Integer(), nullable=False),
        sa.Column("author_user_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_system_note", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], name=op.f("fk_support_case_notes_author_user_id_users")),
        sa.ForeignKeyConstraint(["support_case_id"], ["support_cases.id"], name=op.f("fk_support_case_notes_support_case_id_support_cases")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_case_notes")),
    )
    op.create_index(op.f("ix_support_case_notes_support_case_id"), "support_case_notes", ["support_case_id"], unique=False)
    op.create_index(op.f("ix_support_case_notes_author_user_id"), "support_case_notes", ["author_user_id"], unique=False)

    op.create_table(
        "admin_action_audits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name=op.f("fk_admin_action_audits_actor_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_action_audits")),
    )
    op.create_index(op.f("ix_admin_action_audits_actor_user_id"), "admin_action_audits", ["actor_user_id"], unique=False)
    op.create_index(op.f("ix_admin_action_audits_target_type"), "admin_action_audits", ["target_type"], unique=False)
    op.create_index(op.f("ix_admin_action_audits_target_id"), "admin_action_audits", ["target_id"], unique=False)
    op.create_index(op.f("ix_admin_action_audits_action_type"), "admin_action_audits", ["action_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_admin_action_audits_action_type"), table_name="admin_action_audits")
    op.drop_index(op.f("ix_admin_action_audits_target_id"), table_name="admin_action_audits")
    op.drop_index(op.f("ix_admin_action_audits_target_type"), table_name="admin_action_audits")
    op.drop_index(op.f("ix_admin_action_audits_actor_user_id"), table_name="admin_action_audits")
    op.drop_table("admin_action_audits")

    op.drop_index(op.f("ix_support_case_notes_author_user_id"), table_name="support_case_notes")
    op.drop_index(op.f("ix_support_case_notes_support_case_id"), table_name="support_case_notes")
    op.drop_table("support_case_notes")

    op.drop_index(op.f("ix_support_cases_assigned_to_user_id"), table_name="support_cases")
    op.drop_index(op.f("ix_support_cases_created_by_user_id"), table_name="support_cases")
    op.drop_index(op.f("ix_support_cases_status"), table_name="support_cases")
    op.drop_index(op.f("ix_support_cases_order_id"), table_name="support_cases")
    op.drop_table("support_cases")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        support_case_priority.drop(bind, checkfirst=True)
        support_case_status.drop(bind, checkfirst=True)
