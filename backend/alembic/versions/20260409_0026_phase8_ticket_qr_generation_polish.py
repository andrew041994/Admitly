"""Phase 8 ticket QR token generation and display code polish

Revision ID: 20260409_0026
Revises: 20260409_0025
Create Date: 2026-04-09 13:00:00

"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260409_0026"
down_revision: Union[str, None] = "20260409_0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_tickets_table = sa.table(
    "tickets",
    sa.column("id", sa.Integer),
    sa.column("qr_payload", sa.Text),
    sa.column("qr_token", sa.String),
    sa.column("display_code", sa.String),
    sa.column("qr_generated_at", sa.DateTime(timezone=True)),
)


def _make_display_code(qr_token: str) -> str:
    normalized = "".join(ch for ch in qr_token.upper() if ch.isalnum())
    return f"TKT-{normalized[:10] or secrets.token_hex(5).upper()}"


def upgrade() -> None:
    op.add_column("tickets", sa.Column("display_code", sa.String(length=32), nullable=True))
    op.add_column("tickets", sa.Column("qr_token", sa.String(length=128), nullable=True))
    op.add_column("tickets", sa.Column("qr_generated_at", sa.DateTime(timezone=True), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.select(_tickets_table.c.id, _tickets_table.c.qr_payload, _tickets_table.c.qr_token)).all()
    seen_tokens: set[str] = set()
    seen_display_codes: set[str] = set()

    for row in rows:
        existing = (row.qr_token or "").strip()
        token = existing or (row.qr_payload or "").strip()
        if not token or token in seen_tokens:
            token = secrets.token_urlsafe(24)
            while token in seen_tokens:
                token = secrets.token_urlsafe(24)

        display_code = _make_display_code(token)
        if display_code in seen_display_codes:
            display_code = f"{display_code}-{secrets.token_hex(2).upper()}"
            while display_code in seen_display_codes:
                display_code = f"{_make_display_code(token)}-{secrets.token_hex(2).upper()}"

        seen_tokens.add(token)
        seen_display_codes.add(display_code)

        bind.execute(
            _tickets_table.update()
            .where(_tickets_table.c.id == row.id)
            .values(
                qr_token=token,
                display_code=display_code,
                qr_generated_at=datetime.now(timezone.utc),
            )
        )

    op.create_index(op.f("ix_tickets_display_code"), "tickets", ["display_code"], unique=True)
    op.create_index(op.f("ix_tickets_qr_token"), "tickets", ["qr_token"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_tickets_qr_token"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_display_code"), table_name="tickets")
    op.drop_column("tickets", "qr_generated_at")
    op.drop_column("tickets", "qr_token")
    op.drop_column("tickets", "display_code")
