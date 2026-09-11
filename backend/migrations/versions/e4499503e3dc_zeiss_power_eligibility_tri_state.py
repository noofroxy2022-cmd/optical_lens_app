"""zeiss power eligibility tri-state

Revision ID: e4499503e3dc
Revises: 602b2e1ba151
Create Date: 2026-09-11 06:00:00.000000

ZEISS Phase 3: distinguishes, for an RX pricing row with NO explicit
PowerRange, between:

  * UNRESTRICTED - the source catalog genuinely states no power restriction
    (the frozen matcher's long-standing "RX made-to-order = any power" rule);
    this is the DEFAULT and preserves every existing (HOYA) row's behaviour
    exactly as it is today.
  * UNRESOLVED   - the source catalog's real power applicability (an explicit
    numeric bound, a sign-dependent CYL cap, an ADD exclusion, a graphical/
    zoned map, or an external/deferred reference) is NOT yet modeled, so
    eligibility must be reported UNKNOWN rather than silently true. This is
    what the ZEISS index-grid strategy now sets on every row it produces,
    since those rows carry a real catalog price with no captured power limit
    at all.

Adds:
  * ``variant_pricing.power_eligibility``            (NOT NULL, default UNRESTRICTED)
  * ``catalog_extractions.extracted_power_eligibility`` (nullable review counterpart)

No existing column, index, or row is altered; this is a pure additive widening.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e4499503e3dc'
down_revision: Union[str, Sequence[str], None] = '602b2e1ba151'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


POWER_ELIGIBILITY = postgresql.ENUM(
    "UNRESTRICTED", "UNRESOLVED", name="powereligibilitystatus", create_type=False,
)


def _is_pg(bind) -> bool:
    return bind.dialect.name == "postgresql"


# variant_pricing carries an expression-based unique index
# (uq_variant_pricing_current) that SQLAlchemy's SQLite reflection cannot see
# (same issue as uq_variant_identity in the previous migration) - a batch
# table-recreate silently drops it unless it is explicitly re-created after.
_UQ_CURRENT_COLS = [
    "variant_id",
    "coalesce(coating_id, -1)",
    "availability",
    "coalesce(power_scope, '')",
    "coalesce(market_scope, '')",
]


def _drop_index_if_exists(bind, name, table) -> None:
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


def _create_uq_current(bind) -> None:
    op.create_index(
        "uq_variant_pricing_current", "variant_pricing",
        [sa.text(c) for c in _UQ_CURRENT_COLS],
        unique=True,
        postgresql_where=sa.text("effective_to IS NULL"),
        sqlite_where=sa.text("effective_to IS NULL"),
    )


def upgrade() -> None:
    bind = op.get_bind()
    if _is_pg(bind):
        POWER_ELIGIBILITY.create(bind, checkfirst=True)

    with op.batch_alter_table("catalog_extractions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("extracted_power_eligibility", sa.String(length=20), nullable=True))

    _drop_index_if_exists(bind, "uq_variant_pricing_current", "variant_pricing")
    with op.batch_alter_table("variant_pricing", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "power_eligibility", POWER_ELIGIBILITY, nullable=False,
                server_default=sa.text("'UNRESTRICTED'"),
            )
        )
        batch_op.create_check_constraint(
            "ck_variant_pricing_power_eligibility",
            "power_eligibility IN ('UNRESTRICTED', 'UNRESOLVED')",
        )
    _create_uq_current(bind)


def downgrade() -> None:
    bind = op.get_bind()

    _drop_index_if_exists(bind, "uq_variant_pricing_current", "variant_pricing")
    with op.batch_alter_table("variant_pricing", schema=None) as batch_op:
        batch_op.drop_constraint("ck_variant_pricing_power_eligibility", type_="check")
        batch_op.drop_column("power_eligibility")
    _create_uq_current(bind)

    with op.batch_alter_table("catalog_extractions", schema=None) as batch_op:
        batch_op.drop_column("extracted_power_eligibility")

    if _is_pg(bind):
        POWER_ELIGIBILITY.drop(bind, checkfirst=True)
