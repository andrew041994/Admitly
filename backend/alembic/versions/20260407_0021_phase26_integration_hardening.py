"""phase26 integration hardening"""

from alembic import op
import sqlalchemy as sa


revision = "20260407_0021"
down_revision = "20260407_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("webhook_deliveries", sa.Column("delivery_kind", sa.String(length=32), nullable=False, server_default="automatic_initial"))
    op.add_column("webhook_deliveries", sa.Column("redelivery_of_delivery_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_webhook_deliveries_redelivery_of_delivery_id",
        "webhook_deliveries",
        "webhook_deliveries",
        ["redelivery_of_delivery_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column("webhook_deliveries", "delivery_kind", server_default=None)


def downgrade() -> None:
    op.drop_constraint("fk_webhook_deliveries_redelivery_of_delivery_id", "webhook_deliveries", type_="foreignkey")
    op.drop_column("webhook_deliveries", "redelivery_of_delivery_id")
    op.drop_column("webhook_deliveries", "delivery_kind")
