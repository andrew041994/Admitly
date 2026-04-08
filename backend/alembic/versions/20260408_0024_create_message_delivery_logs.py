"""create message delivery logs table"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "20260408_0024"
down_revision = "20260408_0023"
branch_labels = None
depends_on = None


message_template_type = sa.Enum(
    "order_confirmation",
    "ticket_issued",
    "transfer_invite",
    "transfer_accepted",
    "refund_processed",
    "reminder",
    "event_day_update",
    "organizer_broadcast",
    name="message_template_type",
    create_type=False,
)

message_channel = sa.Enum(
    "email",
    "push",
    name="message_channel",
    create_type=False,
)

message_delivery_status = sa.Enum(
    "sent",
    "failed",
    "skipped",
    name="message_delivery_status",
    create_type=False,
)


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'message_template_type') THEN
                    CREATE TYPE message_template_type AS ENUM (
                        'order_confirmation',
                        'ticket_issued',
                        'transfer_invite',
                        'transfer_accepted',
                        'refund_processed',
                        'reminder',
                        'event_day_update',
                        'organizer_broadcast'
                    );
                END IF;

                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'message_channel') THEN
                    CREATE TYPE message_channel AS ENUM ('email', 'push');
                END IF;

                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'message_delivery_status') THEN
                    CREATE TYPE message_delivery_status AS ENUM ('sent', 'failed', 'skipped');
                END IF;
            END$$;
            """
        )
    )

    op.create_table(
        "message_delivery_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_type", message_template_type, nullable=False),
        sa.Column("channel", message_channel, nullable=False),
        sa.Column("status", message_delivery_status, nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=True),
        sa.Column("recipient_email", sa.String(length=255), nullable=True),
        sa.Column("related_entity_type", sa.String(length=32), nullable=True),
        sa.Column("related_entity_id", sa.Integer(), nullable=True),
        sa.Column("provider_reference_id", sa.String(length=255), nullable=True),
        sa.Column("provider_status", sa.String(length=64), nullable=True),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("is_manual_resend", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("resend_of_message_id", sa.Integer(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_message_delivery_logs_actor_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"],
            ["users.id"],
            name=op.f("fk_message_delivery_logs_recipient_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["resend_of_message_id"],
            ["message_delivery_logs.id"],
            name=op.f("fk_message_delivery_logs_resend_of_message_id_message_delivery_logs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message_delivery_logs")),
    )

    op.create_index(op.f("ix_message_delivery_logs_actor_user_id"), "message_delivery_logs", ["actor_user_id"], unique=False)
    op.create_index(op.f("ix_message_delivery_logs_channel"), "message_delivery_logs", ["channel"], unique=False)
    op.create_index(op.f("ix_message_delivery_logs_idempotency_key"), "message_delivery_logs", ["idempotency_key"], unique=False)
    op.create_index(op.f("ix_message_delivery_logs_recipient_user_id"), "message_delivery_logs", ["recipient_user_id"], unique=False)
    op.create_index(op.f("ix_message_delivery_logs_related_entity_id"), "message_delivery_logs", ["related_entity_id"], unique=False)
    op.create_index(op.f("ix_message_delivery_logs_related_entity_type"), "message_delivery_logs", ["related_entity_type"], unique=False)
    op.create_index(op.f("ix_message_delivery_logs_resend_of_message_id"), "message_delivery_logs", ["resend_of_message_id"], unique=False)
    op.create_index(op.f("ix_message_delivery_logs_status"), "message_delivery_logs", ["status"], unique=False)
    op.create_index(op.f("ix_message_delivery_logs_template_type"), "message_delivery_logs", ["template_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_message_delivery_logs_template_type"), table_name="message_delivery_logs")
    op.drop_index(op.f("ix_message_delivery_logs_status"), table_name="message_delivery_logs")
    op.drop_index(op.f("ix_message_delivery_logs_resend_of_message_id"), table_name="message_delivery_logs")
    op.drop_index(op.f("ix_message_delivery_logs_related_entity_type"), table_name="message_delivery_logs")
    op.drop_index(op.f("ix_message_delivery_logs_related_entity_id"), table_name="message_delivery_logs")
    op.drop_index(op.f("ix_message_delivery_logs_recipient_user_id"), table_name="message_delivery_logs")
    op.drop_index(op.f("ix_message_delivery_logs_idempotency_key"), table_name="message_delivery_logs")
    op.drop_index(op.f("ix_message_delivery_logs_channel"), table_name="message_delivery_logs")
    op.drop_index(op.f("ix_message_delivery_logs_actor_user_id"), table_name="message_delivery_logs")
    op.drop_table("message_delivery_logs")

    bind = op.get_bind()
    message_delivery_status.drop(bind, checkfirst=True)
    message_channel.drop(bind, checkfirst=True)
    message_template_type.drop(bind, checkfirst=True)