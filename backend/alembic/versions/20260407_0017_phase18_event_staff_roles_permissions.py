"""Phase 18 organizer staff roles and scoped permissions

Revision ID: 20260407_0017
Revises: 20260407_0016
Create Date: 2026-04-07 00:17:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260407_0017"
down_revision = "20260407_0016"
branch_labels = None
depends_on = None


OLD_ENUM_NAME = "event_staff_role_old"
NEW_ENUM_NAME = "event_staff_role"


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute(f"ALTER TYPE {NEW_ENUM_NAME} RENAME TO {OLD_ENUM_NAME}")
        op.execute(
            f"CREATE TYPE {NEW_ENUM_NAME} AS ENUM ('owner', 'manager', 'checkin', 'support')"
        )

        op.execute(
            f"""
            ALTER TABLE event_staff
            ALTER COLUMN role DROP DEFAULT
            """
        )

        op.execute(
            f"""
            ALTER TABLE event_staff
            ALTER COLUMN role TYPE {NEW_ENUM_NAME}
            USING (
                CASE
                    WHEN role::text = 'scanner' THEN 'checkin'
                    ELSE role::text
                END
            )::{NEW_ENUM_NAME}
            """
        )

        op.execute(
            f"""
            ALTER TABLE event_staff
            ALTER COLUMN role SET DEFAULT 'checkin'
            """
        )

        op.execute(f"DROP TYPE {OLD_ENUM_NAME}")
    else:
        op.execute("UPDATE event_staff SET role = 'checkin' WHERE role = 'scanner'")

    op.alter_column(
        "event_staff",
        "role",
        existing_type=sa.String(length=20),
        server_default="checkin",
        existing_nullable=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute(f"ALTER TYPE {NEW_ENUM_NAME} RENAME TO {OLD_ENUM_NAME}")
        op.execute(
            f"CREATE TYPE {NEW_ENUM_NAME} AS ENUM ('owner', 'manager', 'scanner')"
        )

        op.execute(
            f"""
            ALTER TABLE event_staff
            ALTER COLUMN role DROP DEFAULT
            """
        )

        op.execute(
            f"""
            ALTER TABLE event_staff
            ALTER COLUMN role TYPE {NEW_ENUM_NAME}
            USING (
                CASE
                    WHEN role::text = 'checkin' THEN 'scanner'
                    WHEN role::text = 'support' THEN 'manager'
                    ELSE role::text
                END
            )::{NEW_ENUM_NAME}
            """
        )

        op.execute(
            f"""
            ALTER TABLE event_staff
            ALTER COLUMN role SET DEFAULT 'scanner'
            """
        )

        op.execute(f"DROP TYPE {OLD_ENUM_NAME}")
    else:
        op.execute("UPDATE event_staff SET role = 'manager' WHERE role = 'support'")
        op.execute("UPDATE event_staff SET role = 'scanner' WHERE role = 'checkin'")

    op.alter_column(
        "event_staff",
        "role",
        existing_type=sa.String(length=20),
        server_default="scanner",
        existing_nullable=False,
    )