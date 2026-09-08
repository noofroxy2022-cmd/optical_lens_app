"""g3 total sph+cyl clause

Revision ID: d4b8e7a19c02
Revises: c7a1f4e0b932
Create Date: 2026-09-09 00:00:00.000000

G3 Stock Range slice 1 ("Total Sph+Cyl (a b) [Max] Cyl (n)"): a diagonal
constraint  total_power_min <= SPH+CYL <= total_power_max  AND  abs(CYL) <= n
that the independent sph_min/sph_max/cyl_min/cyl_max box cannot represent.

Adds three nullable Float columns to ``power_ranges`` and the three mirroring
``extracted_*`` columns to ``catalog_extractions``.  All nullable => no
backfill; NULL means "not a G3 clause".  No index and no CHECK constraint in
this slice.  SQLite-safe via batch_alter_table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4b8e7a19c02"
down_revision: Union[str, Sequence[str], None] = "c7a1f4e0b932"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_PR_COLS = ("total_power_min", "total_power_max", "max_cyl_abs")
_EXT_COLS = (
    "extracted_total_power_min",
    "extracted_total_power_max",
    "extracted_max_cyl_abs",
)


def upgrade() -> None:
    with op.batch_alter_table("power_ranges", schema=None) as batch_op:
        for name in _PR_COLS:
            batch_op.add_column(sa.Column(name, sa.Float(), nullable=True))
    with op.batch_alter_table("catalog_extractions", schema=None) as batch_op:
        for name in _EXT_COLS:
            batch_op.add_column(sa.Column(name, sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("catalog_extractions", schema=None) as batch_op:
        for name in reversed(_EXT_COLS):
            batch_op.drop_column(name)
    with op.batch_alter_table("power_ranges", schema=None) as batch_op:
        for name in reversed(_PR_COLS):
            batch_op.drop_column(name)
