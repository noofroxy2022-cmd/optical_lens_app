"""zeiss design tier treatment axes

Revision ID: 602b2e1ba151
Revises: d4b8e7a19c02
Create Date: 2026-09-11 04:13:23.903104

ZEISS Phase 2: two new independent commercial identity axes, proven necessary
by the ZEISS Single Vision RX index-column price grid (a design TIER within a
shared design family - e.g. "ClearMind" -> "Individual 3" / "Superb" - and a
neutral commercial TREATMENT BAND - e.g. "Clear" / "BlueGuard" / "PhotoFusion X"
/ "Tinted" / "Polarized / AdaptiveSun" / "AdaptiveSun Polarized" - that is
catalog evidence, not yet claimed to be a coating or a material. Named
`treatment_band`, not `treatment`, precisely because ZEISS's own literature
describes "BlueGuard" as a substrate/material technology rather than a
treatment - see Phase 3 item 6).

Both axes are nullable and additive:
  * ``lens_variants.design_tier``       - commercial tier within design_variant's
                                           family, ONLY when the source document
                                           itself proves a shared-family split
                                           (never invented).
  * ``lens_variants.treatment_band``    - raw treatment/technology band label as
                                           extracted; kept distinct from
                                           design_variant (a design LINE) and
                                           color_variant (an actual COLOUR).
  * ``catalog_extractions.extracted_design_tier`` / ``.extracted_treatment_band``
    - the parser-populated preview/review counterparts, mirroring how
      extracted_design / extracted_color_variant already work.

``uq_variant_identity`` is rebuilt to add both new axes (coalesced/normalised
exactly like design_variant / color_variant already are) so that two rows
differing ONLY by tier or by treatment band are never merged as one identity.
Every existing row has NULL for both new columns, so COALESCE(...,'') is the
same constant on both sides of the old and the new index for all of them -
this is a pure widening of the identity, not a behaviour change for any
existing (HOYA) data.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '602b2e1ba151'
down_revision: Union[str, Sequence[str], None] = 'd4b8e7a19c02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_index_if_exists(bind, name, table) -> None:
    # SQLAlchemy's reflection does not reliably report expression-based unique
    # indexes (uq_variant_identity is `lower(trim(coalesce(...)))` on every
    # dialect) so existence is checked directly against sqlite_master here
    # instead of trusting sa.inspect(...).get_indexes(); PostgreSQL falls back
    # to a plain drop-if-exists.
    if bind.dialect.name == "sqlite":
        row = bind.execute(
            sa.text("SELECT 1 FROM sqlite_master WHERE type='index' AND name=:n"),
            {"n": name},
        ).first()
        if row is None:
            return
        op.drop_index(name, table_name=table)
    else:
        op.execute(sa.text(f"DROP INDEX IF EXISTS {name}"))


def upgrade() -> None:
    bind = op.get_bind()

    # ---- catalog_extractions: parser/review counterparts ------------------
    with op.batch_alter_table("catalog_extractions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("extracted_design_tier", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("extracted_treatment_band", sa.String(length=50), nullable=True))

    # ---- lens_variants: new canonical axes + widened identity ------------
    with op.batch_alter_table("lens_variants", schema=None) as batch_op:
        batch_op.add_column(sa.Column("design_tier", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("treatment_band", sa.String(length=50), nullable=True))

    _drop_index_if_exists(bind, "uq_variant_identity", "lens_variants")
    op.create_index(
        "uq_variant_identity", "lens_variants",
        [
            sa.text("lens_model_id"),
            sa.text("material"),
            sa.text("index_value"),
            sa.text("design_type"),
            sa.text("is_aspherical"),
            sa.text("lower(trim(coalesce(design_variant, '')))"),
            sa.text("lower(trim(coalesce(color_variant, '')))"),
            sa.text("lower(trim(coalesce(design_tier, '')))"),
            sa.text("lower(trim(coalesce(treatment_band, '')))"),
        ],
        unique=True,
    )


def downgrade() -> None:
    bind = op.get_bind()

    _drop_index_if_exists(bind, "uq_variant_identity", "lens_variants")
    op.create_index(
        "uq_variant_identity", "lens_variants",
        [
            sa.text("lens_model_id"),
            sa.text("material"),
            sa.text("index_value"),
            sa.text("design_type"),
            sa.text("is_aspherical"),
            sa.text("lower(trim(coalesce(design_variant, '')))"),
            sa.text("lower(trim(coalesce(color_variant, '')))"),
        ],
        unique=True,
    )

    with op.batch_alter_table("lens_variants", schema=None) as batch_op:
        batch_op.drop_column("treatment_band")
        batch_op.drop_column("design_tier")

    with op.batch_alter_table("catalog_extractions", schema=None) as batch_op:
        batch_op.drop_column("extracted_treatment_band")
        batch_op.drop_column("extracted_design_tier")
