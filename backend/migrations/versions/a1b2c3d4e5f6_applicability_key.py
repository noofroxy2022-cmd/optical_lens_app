"""applicability_key for multi-optical-subtype single-price offers

Revision ID: a1b2c3d4e5f6
Revises: e4499503e3dc
Create Date: 2026-09-12 00:00:00.000000

Adds a nullable applicability_key to power_ranges and the mirroring
extracted_applicability_key to catalog_extractions. NULL on every existing
row (HOYA and the 28 already-attached ZEISS ranges) => no behavior change
for anything that doesn't set it. Lets ONE commercial priced offer (one
VariantPricing) legitimately own multiple PowerRanges that are optically
distinct sub-options (e.g. ZEISS's single-priced "Polarized / AdaptiveSun"
offer, where the catalog's own graphical chart proves POL and AdaptiveSun
have different power ranges) without duplicating the price or the SKU.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "e4499503e3dc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("power_ranges", schema=None) as batch_op:
        batch_op.add_column(sa.Column("applicability_key", sa.String(length=50), nullable=True))
    with op.batch_alter_table("catalog_extractions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("extracted_applicability_key", sa.String(length=50), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("catalog_extractions", schema=None) as batch_op:
        batch_op.drop_column("extracted_applicability_key")
    with op.batch_alter_table("power_ranges", schema=None) as batch_op:
        batch_op.drop_column("applicability_key")
