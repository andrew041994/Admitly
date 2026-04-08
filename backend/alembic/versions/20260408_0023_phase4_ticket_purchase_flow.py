"""phase4 ticket purchase flow"""

from alembic import op
import sqlalchemy as sa


revision = "20260408_0023"
down_revision = "20260407_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("reference_code", sa.String(length=32), nullable=True))
    op.execute("""
    UPDATE orders
    SET reference_code = 'ORD-' || lpad(id::text, 8, '0')
    WHERE reference_code IS NULL
    """)
    op.create_unique_constraint("uq_orders_reference_code", "orders", ["reference_code"])
    op.create_index(op.f("ix_orders_reference_code"), "orders", ["reference_code"], unique=False)
    op.alter_column("orders", "reference_code", nullable=False)

    op.execute("ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'awaiting_payment'")
    op.execute("ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'payment_submitted'")
    op.execute("ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'failed'")

    op.create_table(
        "payment_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("payment_method", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("verification_status", sa.String(length=64), nullable=False),
        sa.Column("provider_reference", sa.String(length=255), nullable=True),
        sa.Column("request_payload", sa.Text(), nullable=True),
        sa.Column("response_payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name=op.f("fk_payment_attempts_order_id_orders"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_attempts")),
    )
    op.create_index(op.f("ix_payment_attempts_order_id"), "payment_attempts", ["order_id"], unique=False)
    op.create_index(op.f("ix_payment_attempts_provider_reference"), "payment_attempts", ["provider_reference"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_payment_attempts_provider_reference"), table_name="payment_attempts")
    op.drop_index(op.f("ix_payment_attempts_order_id"), table_name="payment_attempts")
    op.drop_table("payment_attempts")

    op.drop_index(op.f("ix_orders_reference_code"), table_name="orders")
    op.drop_constraint("uq_orders_reference_code", "orders", type_="unique")
    op.drop_column("orders", "reference_code")
