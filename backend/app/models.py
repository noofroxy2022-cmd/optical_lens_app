"""
قاعدة بيانات نهائية للعدسات البصرية

الخصائص:
- Transposition (CYL ±)
- Stock vs RX vs BOTH
- Aspherical flag
- Power Range Matrix
- Preview/Confirm workflow
- Dynamic company management
"""
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Text,
    Enum, JSON, Index, CheckConstraint, Table, text, Numeric
)
from sqlalchemy.orm import relationship, validates
from datetime import datetime
from enum import Enum as PyEnum
from app.database import Base


# ===== Enums =====
class LensAvailability(str, PyEnum):
    STOCK = "stock"
    RX = "rx"
    BOTH = "both"

class LensCategory(str, PyEnum):
    SINGLE_VISION = "single_vision"
    BIFOCAL = "bifocal"
    PROGRESSIVE = "progressive"
    OFFICE = "office"
    DIGITAL = "digital"

class MaterialType(str, PyEnum):
    CR39 = "CR39"
    POLYCARBONATE = "polycarbonate"
    TRIVEX = "trivex"
    HIGH_INDEX_156 = "high_index_1.56"
    HIGH_INDEX_160 = "high_index_1.60"
    HIGH_INDEX_161 = "high_index_1.61"
    HIGH_INDEX_167 = "high_index_1.67"
    HIGH_INDEX_174 = "high_index_1.74"

class DesignType(str, PyEnum):
    # Optical geometry / type ONLY. Not a commercial/marketing label.
    SPHERICAL = "spherical"
    ASPHERICAL = "aspherical"
    DOUBLE_ASPHERICAL = "double_aspherical"
    # LEGACY: kept for backward compatibility. Commercial "Free Form" now belongs
    # in LensVariant.design_variant, not here. Do not write new commercial data to
    # this value; do not remove the value yet.
    FREE_FORM = "free_form"


class CatalogStatus(str, PyEnum):
    """Editorial lifecycle of a catalog (separate from parser processing_status)."""
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class CoatingExtractionStatus(str, PyEnum):
    """How a coating value was resolved during extraction.

    RESOLVED       -> a concrete coating was identified (extracted_coating / coating_id set)
    EXPLICIT_NONE  -> the source explicitly states there is no coating
    NOT_FOUND      -> no coating information was present at all (distinct from EXPLICIT_NONE)
    """
    RESOLVED = "resolved"
    EXPLICIT_NONE = "explicit_none"
    NOT_FOUND = "not_found"


class PricingAvailability(str, PyEnum):
    """Commercial availability at the pricing level. STOCK / RX only - never BOTH."""
    STOCK = "stock"
    RX = "rx"


class PowerEligibilityStatus(str, PyEnum):
    """Whether an RX row with NO explicit PowerRange may be treated as
    prescription-UNRESTRICTED (the frozen matcher's long-standing "RX
    made-to-order, no range printed -> any power" rule).

        UNRESTRICTED -> the source catalog states (or a STOCK/ranged RX row
                        proves) there genuinely is no power restriction; the
                        existing no-range-means-eligible behaviour applies.
        UNRESOLVED   -> the source catalog's power applicability is NOT yet
                        modeled (an explicit numeric bound, a sign-dependent
                        CYL cap, an ADD exclusion, a graphical/zoned map, or an
                        external/deferred reference such as "see VISUSTORE"
                        all count) - eligibility must be reported UNKNOWN, never
                        auto-eligible, until that rule is actually represented.

    Ignored whenever the row HAS explicit PowerRange rows - those are checked
    normally regardless of this flag. Defaults to UNRESTRICTED so every
    existing (HOYA) row is completely unaffected."""
    UNRESTRICTED = "unrestricted"
    UNRESOLVED = "unresolved"


# Sentinel the parser writes to CatalogExtraction.extracted_name when the source
# PDF carries no relation that uniquely determines the product family. It must
# never reach a real LensModel name - a human review overlay (modified_data["name"]
# with family_source == "human_review") replaces it before bulk confirmation.
# Keep in sync with PDFHybridParser.UNRESOLVED_FAMILY.
UNRESOLVED_FAMILY_NAME = "__UNRESOLVED_FAMILY__"


# ===== الطبقات (Coatings) =====
class Coating(Base):
    """Catalog of coating options referenced by commercial pricing."""
    __tablename__ = "coatings"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), nullable=False, unique=True, index=True)
    name = Column(String(100), nullable=False)
    name_ar = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ===== الشركات =====
class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    name_ar = Column(String(100), nullable=True)
    logo_url = Column(String(500), nullable=True)
    country = Column(String(50), nullable=True)
    website = Column(String(200), nullable=True)
    contact_email = Column(String(100), nullable=True)
    contact_phone = Column(String(50), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_deleted = Column(Boolean, default=False, nullable=False)

    description = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lens_models = relationship("LensModel", back_populates="company", cascade="all, delete-orphan")
    catalogs = relationship("Catalog", back_populates="company", cascade="all, delete-orphan")


# ===== الكتالوجات =====
class Catalog(Base):
    __tablename__ = "catalogs"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)

    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=True)
    page_count = Column(Integer, nullable=True)

    # Parser / processing state - preserved separately from the editorial lifecycle.
    processing_status = Column(String(20), default="pending")
    processing_errors = Column(Text, nullable=True)

    # Editorial lifecycle: draft -> confirmed / rejected / superseded.
    status = Column(
        Enum(CatalogStatus), nullable=False,
        default=CatalogStatus.DRAFT, server_default=CatalogStatus.DRAFT.name, index=True
    )
    confirmed_at = Column(DateTime, nullable=True)
    confirmed_by = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="catalogs")
    extractions = relationship("CatalogExtraction", back_populates="catalog", cascade="all, delete-orphan")
    pricing_records = relationship("VariantPricing", back_populates="source_catalog")

    __table_args__ = (
        # Exactly one CONFIRMED catalog per company. PostgreSQL-compatible partial
        # unique index; mirrored for SQLite. Enum is persisted by NAME, hence 'CONFIRMED'.
        Index(
            "uq_one_confirmed_catalog_per_company", "company_id", unique=True,
            postgresql_where=text("status = 'CONFIRMED'"),
            sqlite_where=text("status = 'CONFIRMED'"),
        ),
    )


# ===== البيانات المستخرجة (Preview & Confirm) =====
class CatalogExtraction(Base):
    """البيانات المستخرجة من PDF بانتظار التأكيد"""
    __tablename__ = "catalog_extractions"

    id = Column(Integer, primary_key=True, index=True)
    catalog_id = Column(Integer, ForeignKey("catalogs.id"), nullable=False)

    # البيانات المستخرجة
    extracted_name = Column(String(200), nullable=False)
    extracted_category = Column(String(50), nullable=True)
    extracted_material = Column(String(50), nullable=True)
    extracted_index = Column(Float, nullable=True)
    extracted_availability = Column(String(20), nullable=True)

    # نطاقات القوة
    sph_min = Column(Float, nullable=True)
    sph_max = Column(Float, nullable=True)
    cyl_min = Column(Float, nullable=True)
    cyl_max = Column(Float, nullable=True)
    add_min = Column(Float, nullable=True)
    add_max = Column(Float, nullable=True)
    # G3 "Total Sph+Cyl" clause carried from the parser to bulk-confirm.
    extracted_total_power_min = Column(Float, nullable=True)
    extracted_total_power_max = Column(Float, nullable=True)
    extracted_max_cyl_abs = Column(Float, nullable=True)

    extracted_price = Column(Float, nullable=True)
    extracted_features = Column(JSON, nullable=True)

    # ----- Commercial identity extracted by the parser (Phase 4) -----
    # design_variant / color_variant / market_scope populated by the parser when
    # confidently read from catalog structure; consumed by confirm_catalog_commercial.
    # design geometry stays in a separate concept - these never hold optical geometry.
    extracted_design = Column(String(50), nullable=True)          # commercial design line
    extracted_color_variant = Column(String(50), nullable=True)   # commercial colour / technology line
    extracted_market_scope = Column(String(50), nullable=True)    # generic catalog market key
    # ----- Phase 2 (ZEISS): two more independent commercial axes -----
    # extracted_design_tier: a commercial TIER within a shared design family
    #   (e.g. family "ClearMind" -> tier "Individual 3" / "Superb"), populated
    #   ONLY when the source document itself proves a shared-family/tier split.
    # extracted_treatment_band: the raw treatment/technology band label as printed
    #   (e.g. "Clear" / "BlueGuard" / "PhotoFusion X" / "Tinted"); distinct from
    #   design_variant (a design LINE) and from color_variant (an actual colour) -
    #   a neutral catalog-structure name, never a claim that the band is a
    #   coating or a material (ZEISS itself describes "BlueGuard" as a
    #   substrate/material technology, not a treatment).
    extracted_design_tier = Column(String(50), nullable=True)
    extracted_treatment_band = Column(String(50), nullable=True)
    # ----- Phase 3 (ZEISS): power-eligibility provenance for RX rows with no
    # explicit PowerRange - see PowerEligibilityStatus. Nullable here (the
    # authoritative value lives on VariantPricing.power_eligibility once
    # confirmed); "unresolved" whenever the parser strategy that produced this
    # row does not yet model the source catalog's real power limits.
    extracted_power_eligibility = Column(String(20), nullable=True)

    # ----- Coating extraction semantics -----
    # extracted_coating: raw/normalised coating text as found in the source (if any).
    # coating_id: resolved Coating row when coating_extraction_status == RESOLVED.
    # coating_extraction_status: RESOLVED vs EXPLICIT_NONE vs NOT_FOUND - the last two
    #   are deliberately distinct (source said "no coating" vs source said nothing).
    extracted_coating = Column(String(100), nullable=True)
    coating_id = Column(Integer, ForeignKey("coatings.id"), nullable=True)
    coating_extraction_status = Column(Enum(CoatingExtractionStatus), nullable=True)
    coating_confidence = Column(Float, nullable=True)
    coating_review_notes = Column(Text, nullable=True)

    # حالة التأكيد
    status = Column(String(20), default="pending")  # pending, confirmed, rejected, modified
    reviewed_by = Column(String(100), nullable=True)
    review_notes = Column(Text, nullable=True)

    # بيانات معدلة (إذا تم التعديل)
    modified_data = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)

    catalog = relationship("Catalog", back_populates="extractions")
    coating = relationship("Coating")


# ===== نماذج العدسات =====
class LensModel(Base):
    __tablename__ = "lens_models"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)

    name = Column(String(200), nullable=False, index=True)
    name_ar = Column(String(200), nullable=True)
    lens_code = Column(String(50), nullable=True, index=True)

    category = Column(Enum(LensCategory), nullable=False, default=LensCategory.SINGLE_VISION)

    description = Column(Text, nullable=True)
    features = Column(JSON, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_deleted = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("Company", back_populates="lens_models")
    variants = relationship("LensVariant", back_populates="lens_model", cascade="all, delete-orphan")
    power_ranges = relationship("PowerRange", back_populates="lens_model", cascade="all, delete-orphan")


# ===== متغيرات العدسة =====
class LensVariant(Base):
    __tablename__ = "lens_variants"

    id = Column(Integer, primary_key=True, index=True)
    lens_model_id = Column(Integer, ForeignKey("lens_models.id"), nullable=False)

    material = Column(Enum(MaterialType), nullable=False)
    index_value = Column(Float, nullable=False)
    # DEPRECATED / NON-AUTHORITATIVE as of Phase 1. Authoritative commercial
    # availability lives on VariantPricing.availability. Retained temporarily
    # because the matcher and legacy PDF import still read/write it. New
    # commercial CRUD must never use this column.
    availability = Column(Enum(LensAvailability), nullable=False, default=LensAvailability.STOCK)

    # التصميم
    # design_type = optical geometry / type ONLY (see DesignType).
    # NOT NULL: this is an optical identity dimension of uq_variant_identity; a NULL
    # here would let two otherwise-identical variants bypass the unique constraint
    # on PostgreSQL (NULLs compare distinct). Safe existing default preserved.
    design_type = Column(
        Enum(DesignType), nullable=False, default=DesignType.SPHERICAL
    )
    # NOT NULL for the same reason. Safe existing default preserved.
    is_aspherical = Column(Boolean, nullable=False, default=False)  # للبحث السريع
    # design_variant = commercial / manufacturing design line, e.g.
    #   "Free Form", "High Definition", "Core", "Advance", "Premium", "D Type", "KT Type".
    #   This is the authoritative destination for commercial "Free Form".
    design_variant = Column(String(50), nullable=True)
    # color_variant = commercial colour / tint line, e.g. "Clear", "Transmatic/G/B".
    # ACTUAL COLOUR ONLY - never a treatment_band/technology bucket; when a catalog
    # states a treatment_band/technology but no colour, color_variant stays NULL
    # (never guessed) and the treatment_band is recorded on `treatment_band` below.
    color_variant = Column(String(50), nullable=True)
    # ----- Phase 2 (ZEISS): two more independent commercial axes -----
    # design_tier = a commercial TIER within design_variant's family (e.g.
    #   family "ClearMind" -> tier "Individual 3" / "Superb"). Populated ONLY
    #   when catalog structure proves a shared-family/tier split; never
    #   invented for a family with no sibling tier.
    design_tier = Column(String(50), nullable=True)
    # treatment_band = raw treatment_band/technology band evidence (e.g. "Clear",
    #   "BlueGuard", "PhotoFusion X", "Tinted", "Polarized / AdaptiveSun").
    #   Kept distinct from design_variant and color_variant; NOT reclassified
    #   as a coating or a material by this field alone.
    treatment_band = Column(String(50), nullable=True)

    price = Column(Float, nullable=False)
    currency = Column(String(10), default="USD")
    diameter = Column(Integer, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lens_model = relationship("LensModel", back_populates="variants")
    power_ranges = relationship("PowerRange", back_populates="variant", cascade="all, delete-orphan")
    # NO delete / delete-orphan cascade: historical and current commercial pricing
    # must NEVER be destroyed because a variant is deleted. The VariantPricing ->
    # LensVariant FK is ON DELETE RESTRICT and passive_deletes=True lets the
    # database refuse the parent delete instead of SQLAlchemy touching (or NULLing
    # the NOT NULL) child rows. A variant with pricing history cannot be hard-deleted.
    pricing_records = relationship(
        "VariantPricing", back_populates="variant", passive_deletes=True
    )

    __table_args__ = (
        Index('idx_variant_model_material', 'lens_model_id', 'material'),
        Index('idx_variant_model_index', 'lens_model_id', 'index_value'),
        Index('idx_variant_aspherical', 'is_aspherical'),
        # Minimum safe variant identity. Preserves every optical distinction already
        # representable on this table (model + material + index + geometry +
        # aspherical flag) and adds the two commercial axes. Nullable commercial
        # axes are made deterministic with COALESCE; identity comparison is
        # case/whitespace-insensitive via lower(trim(...)) while the stored value
        # keeps its display casing.
        Index(
            "uq_variant_identity",
            text("lens_model_id"),
            text("material"),
            text("index_value"),
            text("design_type"),
            text("is_aspherical"),
            text("lower(trim(coalesce(design_variant, '')))"),
            text("lower(trim(coalesce(color_variant, '')))"),
            text("lower(trim(coalesce(design_tier, '')))"),
            text("lower(trim(coalesce(treatment_band, '')))"),
            unique=True,
        ),
    )


# ===== التسعير التجاري (append-only) =====
class VariantPricing(Base):
    """Commercial catalog pricing for a variant (+ optional coating).

    Append-only history. A row with effective_to IS NULL is the *current* price
    for its (variant, coating, availability, power_scope, market_scope) tuple.
    Superseding a price closes the old row (sets effective_to) and inserts a new
    one. There is deliberately no public manual update/delete path.
    """
    __tablename__ = "variant_pricing"

    id = Column(Integer, primary_key=True, index=True)
    # ON DELETE RESTRICT: a LensVariant that still has pricing history cannot be
    # hard-deleted. variant_id stays required.
    variant_id = Column(
        Integer, ForeignKey("lens_variants.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    coating_id = Column(Integer, ForeignKey("coatings.id"), nullable=True, index=True)

    # STOCK / RX only - never BOTH (enum has no BOTH; CHECK enforces it at the DB).
    availability = Column(Enum(PricingAvailability), nullable=False)

    # Power-eligibility provenance for an RX row with NO explicit PowerRange
    # (see PowerEligibilityStatus). Irrelevant whenever this row DOES have
    # PowerRange rows - those are always checked normally. Defaults to
    # UNRESTRICTED so every pre-Phase-3 (HOYA) row keeps its existing "RX
    # made-to-order = any power" behaviour unchanged.
    power_eligibility = Column(
        Enum(PowerEligibilityStatus), nullable=False,
        default=PowerEligibilityStatus.UNRESTRICTED,
        server_default=PowerEligibilityStatus.UNRESTRICTED.name,
    )

    # Catalog price for exactly ONE pair (both lenses). Exact fixed-point money -
    # PostgreSQL NUMERIC(12,2); SQLite round-trips 2dp Decimals exactly via the
    # scale-aware result processor. Never Float (binary rounding drift on sums,
    # markups, currency formatting, and "did the price change?" comparisons).
    price_pair = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), nullable=False, default="EGP", server_default="EGP")

    source_catalog_id = Column(Integer, ForeignKey("catalogs.id"), nullable=False)
    source_extraction_id = Column(Integer, ForeignKey("catalog_extractions.id"), nullable=True)

    effective_from = Column(DateTime, nullable=False, default=datetime.utcnow)
    effective_to = Column(DateTime, nullable=True)

    # Optional narrowing scopes (nullable). Part of the "current price" identity.
    power_scope = Column(String(50), nullable=True)
    market_scope = Column(String(50), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    variant = relationship("LensVariant", back_populates="pricing_records")
    coating = relationship("Coating")
    source_catalog = relationship("Catalog", back_populates="pricing_records")
    source_extraction = relationship("CatalogExtraction")
    # NO delete cascade. The PowerRange -> VariantPricing FK is ON DELETE RESTRICT;
    # a pricing row that still has power ranges cannot be hard-deleted, and its
    # ranges are never silently cascaded away.
    power_ranges = relationship(
        "PowerRange", back_populates="pricing", passive_deletes=True
    )

    __table_args__ = (
        # No BOTH at the pricing level (enum is persisted by NAME).
        CheckConstraint(
            "availability IN ('STOCK', 'RX')", name="ck_variant_pricing_availability"
        ),
        CheckConstraint(
            "power_eligibility IN ('UNRESTRICTED', 'UNRESOLVED')",
            name="ck_variant_pricing_power_eligibility",
        ),
        # Zero-length / inverted effective intervals are invalid.
        CheckConstraint(
            "effective_to IS NULL OR effective_from < effective_to",
            name="ck_variant_pricing_effective_interval",
        ),
        # At most one CURRENT price per commercial identity. COALESCE gives the
        # nullable axes deterministic values so NULLs collide as expected.
        Index(
            "uq_variant_pricing_current",
            text("variant_id"),
            text("coalesce(coating_id, -1)"),
            text("availability"),
            text("coalesce(power_scope, '')"),
            text("coalesce(market_scope, '')"),
            unique=True,
            postgresql_where=text("effective_to IS NULL"),
            sqlite_where=text("effective_to IS NULL"),
        ),
        Index("idx_variant_pricing_lookup", "variant_id", "coating_id", "effective_to"),
    )


# ===== نطاقات القوة =====
class PowerRange(Base):
    __tablename__ = "power_ranges"

    id = Column(Integer, primary_key=True, index=True)
    lens_model_id = Column(Integer, ForeignKey("lens_models.id"), nullable=False)
    variant_id = Column(Integer, ForeignKey("lens_variants.id"), nullable=True)
    # A PowerRange cannot exist without a commercial price. A VariantPricing row
    # may legitimately have zero PowerRanges (typical for RX). ON DELETE RESTRICT:
    # commercial pricing that still has ranges cannot be hard-deleted.
    pricing_id = Column(
        Integer, ForeignKey("variant_pricing.id", ondelete="RESTRICT"), nullable=False
    )

    sph_min = Column(Float, nullable=False)
    sph_max = Column(Float, nullable=False)
    cyl_min = Column(Float, nullable=False, default=-10.0)
    cyl_max = Column(Float, nullable=False, default=0.0)
    add_min = Column(Float, nullable=True)
    add_max = Column(Float, nullable=True)
    axis_min = Column(Integer, nullable=True, default=0)
    axis_max = Column(Integer, nullable=True, default=180)

    # قيود خاصة
    max_cyl_for_high_sph = Column(Float, nullable=True)
    sph_threshold = Column(Float, nullable=True)

    # ----- G3 "Total Sph+Cyl" clause (HOYA) -----
    # When set, the AUTHORITATIVE constraint is: total_power_min <= SPH+CYL <=
    # total_power_max (evaluated in the normalized MINUS-cyl convention) AND
    # abs(CYL) <= max_cyl_abs. The sph_*/cyl_* columns above then hold only a
    # false-negative-safe COARSE prefilter box. NULL on every non-G3 row.
    total_power_min = Column(Float, nullable=True)
    total_power_max = Column(Float, nullable=True)
    max_cyl_abs = Column(Float, nullable=True)

    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    lens_model = relationship("LensModel", back_populates="power_ranges")
    variant = relationship("LensVariant", back_populates="power_ranges")
    pricing = relationship("VariantPricing", back_populates="power_ranges")

    __table_args__ = (
        Index('idx_power_sph', 'sph_min', 'sph_max'),
        Index('idx_power_cyl', 'cyl_min', 'cyl_max'),
        Index('idx_power_add', 'add_min', 'add_max'),
        Index('idx_power_variant', 'variant_id', 'sph_min', 'sph_max'),
        Index('idx_power_pricing', 'pricing_id'),
    )

    @validates('sph_min', 'sph_max')
    def validate_sph(self, key, value):
        if value < -30.0 or value > 30.0:
            raise ValueError(f"SPH must be between -30 and +30")
        return round(value, 2)

    @validates('cyl_min', 'cyl_max')
    def validate_cyl(self, key, value):
        # Signed: a catalog range keeps its source notation - "Cyl (-3.00)" ->
        # [-3, 0] (minus-cyl blank), "Cyl (+3.00)" -> [0, +3] (plus-cyl blank).
        # (Deferred hardening: a cyl_min <= cyl_max cross-field invariant is not
        # enforced here.)
        if value < -10.0 or value > 10.0:
            raise ValueError(f"CYL must be between -10 and +10")
        return round(value, 2)

    @validates('total_power_min', 'total_power_max')
    def validate_total_power(self, key, value):
        if value is None:
            return value
        if value < -40.0 or value > 40.0:
            raise ValueError("total power (SPH+CYL) must be between -40 and +40")
        return round(value, 2)

    @validates('max_cyl_abs')
    def validate_max_cyl_abs(self, key, value):
        if value is None:
            return value
        if value < 0.0 or value > 10.0:
            raise ValueError("max_cyl_abs must be between 0 and +10")
        return round(value, 2)


# ===== الوصفات =====
class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(Integer, primary_key=True, index=True)

    customer_name = Column(String(100), nullable=True)
    customer_phone = Column(String(20), nullable=True)

    # العين اليمنى (OD) - الأصلية
    od_sph_original = Column(Float, nullable=False)
    od_cyl_original = Column(Float, nullable=True, default=0.0)
    od_axis_original = Column(Integer, nullable=True, default=0)
    od_add = Column(Float, nullable=True, default=0.0)

    # العين اليمنى - بعد Transposition
    od_sph = Column(Float, nullable=False)
    od_cyl = Column(Float, nullable=True, default=0.0)
    od_axis = Column(Integer, nullable=True, default=0)

    # العين اليسرى (OS) - الأصلية
    os_sph_original = Column(Float, nullable=False)
    os_cyl_original = Column(Float, nullable=True, default=0.0)
    os_axis_original = Column(Integer, nullable=True, default=0)
    os_add = Column(Float, nullable=True, default=0.0)

    # العين اليسرى - بعد Transposition
    os_sph = Column(Float, nullable=False)
    os_cyl = Column(Float, nullable=True, default=0.0)
    os_axis = Column(Integer, nullable=True, default=0)

    # هل تم Transposition؟
    transposition_applied = Column(Boolean, default=False)

    pd = Column(Float, nullable=True)
    image_path = Column(String(500), nullable=True)
    ocr_confidence = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ===== نتائج المطابقة =====
class MatchResult(Base):
    __tablename__ = "match_results"

    id = Column(Integer, primary_key=True, index=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"), nullable=False)
    variant_id = Column(Integer, ForeignKey("lens_variants.id"), nullable=False)

    match_score = Column(Float, nullable=False)
    match_reason = Column(Text, nullable=True)
    is_selected = Column(Boolean, default=False)

    # تفاصيل التوصية
    index_recommended = Column(Boolean, default=False)
    aspherical_recommended = Column(Boolean, default=False)
    stock_available = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
