"""variant pricing price confirmation note

Revision ID: b3f7c9d21a44
Revises: a1b2c3d4e5f6
Create Date: 2026-09-13 23:55:00.000000

PIXEL "Hi Power" domain correction: a generic, manufacturer-agnostic
catalog-proven caveat for a VariantPricing row whose printed base price is
commercially usable and whose manufacturing eligibility is NOT affected by
it, but whose FINAL price may need a separate manual/lab confirmation (e.g.
an add-on surcharge whose applicability trigger the catalog never states
numerically). PIXEL's "Hi Power" (+1000, no stated SPH/CYL/Total-Power/index
threshold) is the first case this represents; any manufacturer's row may
carry one in the future.

Deliberately SEPARATE from `power_eligibility` (manufacturing-eligibility
provenance) and from `PairFulfillment.needs_review` (proven-pair
PROVENANCE completeness) - this is about a proven, priced, eligible row
whose LAST-MILE price completeness is still pending human judgement.

Adds:
  * ``variant_pricing.price_confirmation_note`` (nullable, NULL by default -
    a pure additive widening; no existing row's meaning changes).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3f7c9d21a44"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("variant_pricing", schema=None) as batch_op:
        batch_op.add_column(sa.Column("price_confirmation_note", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("variant_pricing", schema=None) as batch_op:
        batch_op.drop_column("price_confirmation_note")
