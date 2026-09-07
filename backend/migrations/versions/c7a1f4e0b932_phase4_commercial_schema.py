"""phase4 commercial schema

Revision ID: c7a1f4e0b932
Revises: 0cdade4da8ba
Create Date: 2026-09-07 06:30:00.000000

Brings the baseline schema up to the current (Phase 4) commercial model:

  * new PostgreSQL enum types: catalogstatus, coatingextractionstatus, pricingavailability
  * new table  ``coatings``
  * ``catalogs``            -> status / confirmed_at / confirmed_by (+ partial-unique
                              one-confirmed-catalog-per-company)
  * ``catalog_extractions`` -> extracted_design / extracted_color_variant /
                              extracted_market_scope / extracted_coating / coating_id (FK)
                              / coating_extraction_status / coating_confidence /
                              coating_review_notes
  * ``lens_variants``       -> design_variant / color_variant; design_type & is_aspherical
                              become NOT NULL (defensive backfill first);
                              uq_variant_identity expression-unique index
  * new table  ``variant_pricing`` (append-only, NUMERIC(12,2), RESTRICT FKs,
                              CHECK constraints, uq_variant_pricing_current
                              partial/expression-unique index)
  * ``power_ranges``        -> pricing_id (FK -> variant_pricing, ON DELETE RESTRICT,
                              NOT NULL) + idx_power_pricing

MIGRATION ASSUMPTION (confirmed): this project has NO production database and NO
production legacy data yet.  Existing databases are development/test only and
effectively empty.  This migration therefore does NOT invent or backfill
``variant_pricing`` from legacy ``power_ranges`` rows.  If any ``power_ranges``
row exists it aborts with a clear error (see the guard in ``upgrade``).

Baseline fields are preserved: ``lens_variants.price`` / ``.currency`` /
``.availability`` and the ``designtype.FREE_FORM`` enum label are left untouched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c7a1f4e0b932"
down_revision: Union[str, Sequence[str], None] = "0cdade4da8ba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --------------------------------------------------------------------------- #
# New PostgreSQL enum types.  ``create_type=False`` -> Alembic will NOT emit a
# CREATE TYPE while adding the columns; we create/drop them explicitly, exactly
# once, with checkfirst so re-runs are safe.  On SQLite these degrade to VARCHAR.
# --------------------------------------------------------------------------- #
CATALOG_STATUS = postgresql.ENUM(
    "DRAFT", "CONFIRMED", "REJECTED", "SUPERSEDED",
    name="catalogstatus", create_type=False,
)
COATING_STATUS = postgresql.ENUM(
    "RESOLVED", "EXPLICIT_NONE", "NOT_FOUND",
    name="coatingextractionstatus", create_type=False,
)
PRICING_AVAIL = postgresql.ENUM(
    "STOCK", "RX",
    name="pricingavailability", create_type=False,
)
_NEW_ENUMS = (CATALOG_STATUS, COATING_STATUS, PRICING_AVAIL)

# baseline ``design_type`` column type (VARCHAR(17) on SQLite; enum on PG).  The
# ``designtype`` PG type itself is NEVER created/altered/dropped here.
DESIGN_TYPE_EXISTING = sa.String(length=17)


def _is_pg(bind) -> bool:
    return bind.dialect.name == "postgresql"


def _create_new_enum_types(bind) -> None:
    if _is_pg(bind):
        for enum in _NEW_ENUMS:
            enum.create(bind, checkfirst=True)


def _drop_new_enum_types(bind) -> None:
    if _is_pg(bind):
        for enum in reversed(_NEW_ENUMS):
            enum.drop(bind, checkfirst=True)


def _ensure_index(bind, name, table, columns, *, unique=False, **kw) -> None:
    """Create ``name`` only if a SQLite batch table-recreate has not already
    preserved it (defends against silent index loss during batch operations)."""
    existing = {ix["name"] for ix in sa.inspect(bind).get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns, unique=unique, **kw)


def _drop_index_if_exists(bind, name, table) -> None:
    existing = {ix["name"] for ix in sa.inspect(bind).get_indexes(table)}
    if name in existing:
        op.drop_index(name, table_name=table)


# --------------------------------------------------------------------------- #
def upgrade() -> None:
    bind = op.get_bind()

    # ---- 0. empty-baseline guard -------------------------------------------- #
    legacy_power_ranges = bind.execute(
        sa.text("SELECT COUNT(*) FROM power_ranges")
    ).scalar() or 0
    if legacy_power_ranges:
        raise RuntimeError(
            "Revision c7a1f4e0b932 assumes a PRE-PRODUCTION baseline with NO "
            "legacy power_ranges data. Found %d existing power_ranges row(s) "
            "which cannot be linked to a variant_pricing record. Aborting: this "
            "migration will not invent/backfill VariantPricing and will not "
            "delete rows. Clear the legacy power_ranges data manually before "
            "running this upgrade." % legacy_power_ranges
        )

    # ---- 1. enum types (before any column/table that uses them) ------------ #
    _create_new_enum_types(bind)

    # ---- 2. coatings ----------------------------------------------------------
    op.create_table(
        "coatings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("name_ar", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_coatings_id"), "coatings", ["id"], unique=False)
    op.create_index(op.f("ix_coatings_code"), "coatings", ["code"], unique=True)

    # ---- 3. catalog lifecycle ---------------------------------------------- #
    op.add_column(
        "catalogs",
        sa.Column(
            "status", CATALOG_STATUS, nullable=False,
            server_default=sa.text("'DRAFT'"),
        ),
    )  # existing catalogs become DRAFT via this server default
    op.add_column("catalogs", sa.Column("confirmed_at", sa.DateTime(), nullable=True))
    op.add_column("catalogs", sa.Column("confirmed_by", sa.String(length=100), nullable=True))
    _ensure_index(bind, "ix_catalogs_id", "catalogs", ["id"])
    _ensure_index(bind, "ix_catalogs_status", "catalogs", ["status"])

    # ---- 4. catalog_extractions commercial + coating fields --------------- #
    with op.batch_alter_table("catalog_extractions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("extracted_design", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("extracted_color_variant", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("extracted_market_scope", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("extracted_coating", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("coating_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("coating_extraction_status", COATING_STATUS, nullable=True))
        batch_op.add_column(sa.Column("coating_confidence", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("coating_review_notes", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_catalog_extractions_coating_id", "coatings", ["coating_id"], ["id"],
        )
    _ensure_index(bind, "ix_catalog_extractions_id", "catalog_extractions", ["id"])

    # ---- 5. lens_variants: commercial cols + NOT NULL optical identity ---- #
    lens_variants = sa.table(
        "lens_variants",
        sa.column("design_type", sa.String()),
        sa.column("is_aspherical", sa.Boolean()),
    )
    # defensive backfill BEFORE tightening nullability (empty in every current
    # environment; kept for safety). SQLAlchemy Core renders the boolean literal
    # per-dialect (false / 0).
    op.execute(
        lens_variants.update()
        .where(lens_variants.c.design_type.is_(None))
        .values(design_type="SPHERICAL")
    )
    op.execute(
        lens_variants.update()
        .where(lens_variants.c.is_aspherical.is_(None))
        .values(is_aspherical=False)
    )
    with op.batch_alter_table("lens_variants", schema=None) as batch_op:
        batch_op.add_column(sa.Column("design_variant", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("color_variant", sa.String(length=50), nullable=True))
        batch_op.alter_column(
            "design_type", existing_type=DESIGN_TYPE_EXISTING,
            existing_nullable=True, nullable=False,
        )
        batch_op.alter_column(
            "is_aspherical", existing_type=sa.Boolean(),
            existing_nullable=True, nullable=False,
        )
    for ix_name, ix_cols in (
        ("ix_lens_variants_id", ["id"]),
        ("idx_variant_model_material", ["lens_model_id", "material"]),
        ("idx_variant_model_index", ["lens_model_id", "index_value"]),
        ("idx_variant_aspherical", ["is_aspherical"]),
    ):
        _ensure_index(bind, ix_name, "lens_variants", ix_cols)

    # ---- 6. variant_pricing (append-only commercial history) ------------- #
    op.create_table(
        "variant_pricing",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("variant_id", sa.Integer(), nullable=False),
        sa.Column("coating_id", sa.Integer(), nullable=True),
        sa.Column("availability", PRICING_AVAIL, nullable=False),
        sa.Column("price_pair", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "currency", sa.String(length=10), nullable=False,
            server_default=sa.text("'EGP'"),
        ),
        sa.Column("source_catalog_id", sa.Integer(), nullable=False),
        sa.Column("source_extraction_id", sa.Integer(), nullable=True),
        sa.Column("effective_from", sa.DateTime(), nullable=False),
        sa.Column("effective_to", sa.DateTime(), nullable=True),
        sa.Column("power_scope", sa.String(length=50), nullable=True),
        sa.Column("market_scope", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["variant_id"], ["lens_variants.id"],
            name="fk_variant_pricing_variant_id", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["coating_id"], ["coatings.id"], name="fk_variant_pricing_coating_id",
        ),
        sa.ForeignKeyConstraint(
            ["source_catalog_id"], ["catalogs.id"],
            name="fk_variant_pricing_source_catalog_id",
        ),
        sa.ForeignKeyConstraint(
            ["source_extraction_id"], ["catalog_extractions.id"],
            name="fk_variant_pricing_source_extraction_id",
        ),
        sa.CheckConstraint(
            "availability IN ('STOCK', 'RX')",
            name="ck_variant_pricing_availability",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_from < effective_to",
            name="ck_variant_pricing_effective_interval",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_variant_pricing_id"), "variant_pricing", ["id"], unique=False)
    op.create_index(op.f("ix_variant_pricing_variant_id"), "variant_pricing", ["variant_id"], unique=False)
    op.create_index(op.f("ix_variant_pricing_coating_id"), "variant_pricing", ["coating_id"], unique=False)
    op.create_index(
        "idx_variant_pricing_lookup", "variant_pricing",
        ["variant_id", "coating_id", "effective_to"], unique=False,
    )

    # ---- 7. power_ranges.pricing_id (RESTRICT FK, NOT NULL) -------------- #
    with op.batch_alter_table("power_ranges", schema=None) as batch_op:
        batch_op.add_column(sa.Column("pricing_id", sa.Integer(), nullable=False))
        batch_op.create_foreign_key(
            "fk_power_ranges_pricing_id", "variant_pricing",
            ["pricing_id"], ["id"], ondelete="RESTRICT",
        )
    for ix_name, ix_cols in (
        ("ix_power_ranges_id", ["id"]),
        ("idx_power_sph", ["sph_min", "sph_max"]),
        ("idx_power_cyl", ["cyl_min", "cyl_max"]),
        ("idx_power_add", ["add_min", "add_max"]),
        ("idx_power_variant", ["variant_id", "sph_min", "sph_max"]),
    ):
        _ensure_index(bind, ix_name, "power_ranges", ix_cols)
    _ensure_index(bind, "idx_power_pricing", "power_ranges", ["pricing_id"])

    # ---- 8/9. hand-authored partial / expression unique indexes --------- #
    op.create_index(
        "uq_one_confirmed_catalog_per_company", "catalogs", ["company_id"],
        unique=True,
        postgresql_where=sa.text("status = 'CONFIRMED'"),
        sqlite_where=sa.text("status = 'CONFIRMED'"),
    )
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
    op.create_index(
        "uq_variant_pricing_current", "variant_pricing",
        [
            sa.text("variant_id"),
            sa.text("coalesce(coating_id, -1)"),
            sa.text("availability"),
            sa.text("coalesce(power_scope, '')"),
            sa.text("coalesce(market_scope, '')"),
        ],
        unique=True,
        postgresql_where=sa.text("effective_to IS NULL"),
        sqlite_where=sa.text("effective_to IS NULL"),
    )


# --------------------------------------------------------------------------- #
def downgrade() -> None:
    bind = op.get_bind()

    # ---- reverse 8/9: hand-authored indexes ---------------------------- #
    _drop_index_if_exists(bind, "uq_variant_pricing_current", "variant_pricing")
    _drop_index_if_exists(bind, "uq_variant_identity", "lens_variants")
    _drop_index_if_exists(bind, "uq_one_confirmed_catalog_per_company", "catalogs")

    # ---- reverse 7: power_ranges.pricing_id (must go before variant_pricing) #
    _drop_index_if_exists(bind, "idx_power_pricing", "power_ranges")
    with op.batch_alter_table("power_ranges", schema=None) as batch_op:
        batch_op.drop_constraint("fk_power_ranges_pricing_id", type_="foreignkey")
        batch_op.drop_column("pricing_id")

    # ---- reverse 6: variant_pricing --------------------------------------- #
    op.drop_index("idx_variant_pricing_lookup", table_name="variant_pricing")
    op.drop_index(op.f("ix_variant_pricing_coating_id"), table_name="variant_pricing")
    op.drop_index(op.f("ix_variant_pricing_variant_id"), table_name="variant_pricing")
    op.drop_index(op.f("ix_variant_pricing_id"), table_name="variant_pricing")
    op.drop_table("variant_pricing")

    # ---- reverse 5: lens_variants (restore nullable, drop commercial cols) #
    with op.batch_alter_table("lens_variants", schema=None) as batch_op:
        batch_op.alter_column(
            "is_aspherical", existing_type=sa.Boolean(),
            existing_nullable=False, nullable=True,
        )
        batch_op.alter_column(
            "design_type", existing_type=DESIGN_TYPE_EXISTING,
            existing_nullable=False, nullable=True,
        )
        batch_op.drop_column("color_variant")
        batch_op.drop_column("design_variant")

    # ---- reverse 4: catalog_extractions --------------------------------- #
    with op.batch_alter_table("catalog_extractions", schema=None) as batch_op:
        batch_op.drop_constraint("fk_catalog_extractions_coating_id", type_="foreignkey")
        batch_op.drop_column("coating_review_notes")
        batch_op.drop_column("coating_confidence")
        batch_op.drop_column("coating_extraction_status")
        batch_op.drop_column("coating_id")
        batch_op.drop_column("extracted_coating")
        batch_op.drop_column("extracted_market_scope")
        batch_op.drop_column("extracted_color_variant")
        batch_op.drop_column("extracted_design")

    # ---- reverse 3: catalogs ------------------------------------------- #
    _drop_index_if_exists(bind, "ix_catalogs_status", "catalogs")
    op.drop_column("catalogs", "confirmed_by")
    op.drop_column("catalogs", "confirmed_at")
    op.drop_column("catalogs", "status")

    # ---- reverse 2: coatings ------------------------------------------- #
    op.drop_index(op.f("ix_coatings_code"), table_name="coatings")
    op.drop_index(op.f("ix_coatings_id"), table_name="coatings")
    op.drop_table("coatings")

    # ---- reverse 1: enum types (only after every dependent column/table gone) #
    _drop_new_enum_types(bind)
