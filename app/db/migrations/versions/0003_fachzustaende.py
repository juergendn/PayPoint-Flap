"""Fachzustände befuellung/entnahme (Tür offen bis Türkontakt „zu“)

Revision ID: 0003
Revises: 0002
Erstellt: 2026-10-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_fach_zustand", "fach", type_="check")
    op.create_check_constraint(
        "ck_fach_zustand",
        "fach",
        "zustand IN ('frei', 'befuellung', 'belegt', 'entnahme', 'gestoert')",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE fach SET zustand = CASE zustand WHEN 'befuellung' THEN 'belegt'"
        " WHEN 'entnahme' THEN 'frei' ELSE zustand END"
    )
    op.drop_constraint("ck_fach_zustand", "fach", type_="check")
    op.create_check_constraint(
        "ck_fach_zustand", "fach", "zustand IN ('frei', 'belegt', 'gestoert')"
    )
