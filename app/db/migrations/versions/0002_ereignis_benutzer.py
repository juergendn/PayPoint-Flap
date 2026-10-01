"""Ereignis: wer hat gehandelt (benutzer_id)

Revision ID: 0002
Revises: 0001
Erstellt: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ereignis", sa.Column("benutzer_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "ereignis_benutzer_id_fkey",
        "ereignis",
        "benutzer",
        ["benutzer_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ereignis_benutzer_id_fkey", "ereignis", type_="foreignkey")
    op.drop_column("ereignis", "benutzer_id")
