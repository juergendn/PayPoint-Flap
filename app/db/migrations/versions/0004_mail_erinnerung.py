"""Mail-Wiederholung und Erinnerung an die Wäscheabteilung

Revision ID: 0004
Revises: 0003
Erstellt: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mail",
        sa.Column("naechster_versuch", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "zuweisung", sa.Column("erinnert_am", sa.DateTime(timezone=True), nullable=True)
    )
    # Der Maildienst fragt alle 15 s nach offenen Mails.
    op.create_index(
        "ix_mail_offen", "mail", ["id"], postgresql_where=sa.text("status = 'offen'")
    )
    op.execute(
        "INSERT INTO einstellung (schluessel, wert) VALUES ('tuer.max_offen_min', '10')"
        " ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    op.drop_index("ix_mail_offen", table_name="mail")
    op.drop_column("zuweisung", "erinnert_am")
    op.drop_column("mail", "naechster_versuch")
