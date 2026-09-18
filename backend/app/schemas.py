"""
مخططات Pydantic النهائية
"""
from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from decimal import Decimal
from enum import Enum


class LensAvailability(str, Enum):
    STOCK = "stock"
    RX = "rx"
    BOTH = "both"

class LensCategory(str, Enum):
    SINGLE_VISION = "single_vision"
    BIFOCAL = "bifocal"
    PROGRESSIVE = "progressive"
    OFFICE = "office"
    DIGITAL = "digital"

class MaterialType(str, Enum):
    CR39 = "CR39"
    POLYCARBONATE = "polycarbonate"
    TRIVEX = "trivex"
    HIGH_INDEX_156 = "high_index_1.56"
    HIGH_INDEX_160 = "high_index_1.60"
    HIGH_INDEX_161 = "high_index_1.61"
    HIGH_INDEX_167 = "high_index_1.67"
    HIGH_INDEX_174 = "high_index_1.74"
    # Mineral glass - added for SCOPE's printed "White Glass"/"Photo Glass"
    # rows (migration c9d8e7f6a5b4). Never a placeholder for any plastic
    # material; only ever set when the catalog explicitly prints glass.
    GLASS = "glass"

class DesignType(str, Enum):
    # Optical geometry / type ONLY.
    SPHERICAL = "spherical"
    ASPHERICAL = "aspherical"
    DOUBLE_ASPHERICAL = "double_aspherical"
    FREE_FORM = "free_form"  # LEGACY - commercial "Free Form" belongs in design_variant


class CatalogStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class CoatingExtractionStatus(str, Enum):
    RESOLVED = "resolved"
    EXPLICIT_NONE = "explicit_none"
    NOT_FOUND = "not_found"


class PricingAvailability(str, Enum):
    STOCK = "stock"
    RX = "rx"


# ===== Company =====
class CompanyBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    name_ar: Optional[str] = None
    country: Optional[str] = None
    website: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None

class CompanyCreate(CompanyBase):
    pass

class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    name_ar: Optional[str] = None
    country: Optional[str] = None
    website: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None

class CompanyResponse(CompanyBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    logo_url: Optional[str] = None
    is_active: bool
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    lens_models_count: int = 0
    catalogs_count: int = 0


# ===== Coating =====
class CoatingBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    name_ar: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True

class CoatingCreate(CoatingBase):
    pass

class CoatingResponse(CoatingBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


# ===== Catalog =====
class CatalogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    filename: str
    file_path: str
    file_size: Optional[int]
    page_count: Optional[int]
    processing_status: str
    processing_errors: Optional[str]
    status: str
    confirmed_at: Optional[datetime] = None
    confirmed_by: Optional[str] = None
    created_at: datetime


# ===== Catalog Extraction (Preview & Confirm) =====
class CatalogExtractionBase(BaseModel):
    extracted_name: str
    extracted_category: Optional[str] = None
    extracted_material: Optional[str] = None
    extracted_index: Optional[float] = None
    extracted_availability: Optional[str] = None
    sph_min: Optional[float] = None
    sph_max: Optional[float] = None
    cyl_min: Optional[float] = None
    cyl_max: Optional[float] = None
    add_min: Optional[float] = None
    add_max: Optional[float] = None
    # G3 "Total Sph+Cyl" clause (nullable; only set for G3 stock ranges)
    extracted_total_power_min: Optional[float] = None
    extracted_total_power_max: Optional[float] = None
    extracted_max_cyl_abs: Optional[float] = None
    # Optical applicability sub-branch (Phase 4K) - which sub-option of a
    # multi-range single-priced offer this row's range belongs to ("POL" /
    # "AdaptiveSun" / ...). NULL for every ordinary (non-split) row.
    extracted_applicability_key: Optional[str] = None
    extracted_price: Optional[float] = None
    extracted_features: Optional[List[str]] = None
    # commercial identity (parser-populated in Phase 4)
    extracted_design: Optional[str] = None
    extracted_color_variant: Optional[str] = None
    extracted_market_scope: Optional[str] = None
    # Phase 2 (ZEISS): two more independent commercial axes
    extracted_design_tier: Optional[str] = None
    extracted_treatment_band: Optional[str] = None
    extracted_coating: Optional[str] = None
    coating_id: Optional[int] = None
    coating_extraction_status: Optional[CoatingExtractionStatus] = None
    coating_confidence: Optional[float] = None

class CatalogExtractionCreate(CatalogExtractionBase):
    catalog_id: int

class CatalogExtractionUpdate(BaseModel):
    extracted_name: Optional[str] = None
    extracted_category: Optional[str] = None
    extracted_material: Optional[str] = None
    extracted_index: Optional[float] = None
    extracted_availability: Optional[str] = None
    sph_min: Optional[float] = None
    sph_max: Optional[float] = None
    cyl_min: Optional[float] = None
    cyl_max: Optional[float] = None
    add_min: Optional[float] = None
    add_max: Optional[float] = None
    extracted_total_power_min: Optional[float] = None
    extracted_total_power_max: Optional[float] = None
    extracted_max_cyl_abs: Optional[float] = None
    extracted_applicability_key: Optional[str] = None
    extracted_price: Optional[float] = None
    extracted_features: Optional[List[str]] = None
    # commercial identity + coating human correction / review (mirrors CatalogExtraction)
    extracted_design: Optional[str] = None
    extracted_color_variant: Optional[str] = None
    extracted_market_scope: Optional[str] = None
    extracted_design_tier: Optional[str] = None
    extracted_treatment_band: Optional[str] = None
    extracted_coating: Optional[str] = None
    coating_id: Optional[int] = None
    coating_extraction_status: Optional[CoatingExtractionStatus] = None
    coating_confidence: Optional[float] = None
    coating_review_notes: Optional[str] = None
    # Power-eligibility provenance for a reviewer to mark explicitly (see
    # PowerEligibilityStatus) - was previously settable only by the parser
    # itself. A reviewer may only ever move a row TOWARD "unresolved" (the
    # safe, no-power-claim state); the frozen matcher's "unrestricted" default
    # for a no-range RX row is untouched for every row the reviewer leaves alone.
    extracted_power_eligibility: Optional[str] = None
    status: Optional[str] = None
    review_notes: Optional[str] = None
    modified_data: Optional[Dict[str, Any]] = None

class CatalogExtractionResponse(CatalogExtractionBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    catalog_id: int
    status: str
    reviewed_by: Optional[str]
    review_notes: Optional[str]
    coating_review_notes: Optional[str] = None
    modified_data: Optional[Dict[str, Any]]
    created_at: datetime
    reviewed_at: Optional[datetime]


# ===== Power Range =====
class PowerRangeBase(BaseModel):
    sph_min: float = Field(..., ge=-30.0, le=30.0)
    sph_max: float = Field(..., ge=-30.0, le=30.0)
    # Signed CYL: minus-cyl range [-c, 0] or plus-cyl range [0, +c] - the
    # catalog's source notation is preserved, never transposed.
    cyl_min: float = Field(-10.0, ge=-10.0, le=10.0)
    cyl_max: float = Field(0.0, ge=-10.0, le=10.0)
    add_min: Optional[float] = Field(None, ge=0.0, le=5.0)
    add_max: Optional[float] = Field(None, ge=0.0, le=5.0)
    axis_min: Optional[int] = Field(0, ge=0, le=180)
    axis_max: Optional[int] = Field(180, ge=0, le=180)
    max_cyl_for_high_sph: Optional[float] = None
    sph_threshold: Optional[float] = None
    # G3 "Total Sph+Cyl" clause: SPH+CYL in [total_power_min, total_power_max]
    # AND abs(CYL) <= max_cyl_abs. NULL for non-G3 ranges.
    total_power_min: Optional[float] = Field(None, ge=-40.0, le=40.0)
    total_power_max: Optional[float] = Field(None, ge=-40.0, le=40.0)
    max_cyl_abs: Optional[float] = Field(None, ge=0.0, le=10.0)
    # Optical applicability sub-branch (Phase 4K) - see PairFulfillment.applicability_key.
    applicability_key: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None

class PowerRangeCreate(PowerRangeBase):
    lens_model_id: int
    variant_id: Optional[int] = None
    # Required at the DB level (a PowerRange cannot exist without pricing). Kept
    # Optional here so legacy callers fail loudly rather than silently; commercial
    # callers must supply it.
    pricing_id: Optional[int] = None

class PowerRangeResponse(PowerRangeBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    lens_model_id: int
    variant_id: Optional[int]
    pricing_id: Optional[int] = None
    created_at: datetime


# ===== Lens Variant =====
class LensVariantBase(BaseModel):
    material: MaterialType
    index_value: float = Field(..., ge=1.0, le=2.0)
    # DEPRECATED / NON-AUTHORITATIVE: commercial availability lives on VariantPricing.
    availability: LensAvailability = LensAvailability.STOCK
    design_type: DesignType = DesignType.SPHERICAL  # optical geometry ONLY
    is_aspherical: bool = False
    design_variant: Optional[str] = Field(None, max_length=50)  # commercial design line
    color_variant: Optional[str] = Field(None, max_length=50)   # commercial colour line
    design_tier: Optional[str] = Field(None, max_length=50)     # tier within design_variant's family
    treatment_band: Optional[str] = Field(None, max_length=50)       # treatment_band/technology band evidence
    price: float = Field(..., ge=0)
    currency: str = "USD"
    diameter: Optional[int] = Field(None, ge=50, le=80)
    is_active: bool = True

class LensVariantCreate(LensVariantBase):
    lens_model_id: int

class LensVariantResponse(LensVariantBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    lens_model_id: int
    created_at: datetime
    updated_at: datetime
    power_ranges: List[PowerRangeResponse] = []


# ===== Lens Model =====
class LensModelBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    name_ar: Optional[str] = None
    lens_code: Optional[str] = None
    category: LensCategory = LensCategory.SINGLE_VISION
    description: Optional[str] = None
    features: Optional[List[str]] = None
    is_active: bool = True

class LensModelCreate(LensModelBase):
    company_id: int

class LensModelUpdate(BaseModel):
    name: Optional[str] = None
    name_ar: Optional[str] = None
    lens_code: Optional[str] = None
    category: Optional[LensCategory] = None
    description: Optional[str] = None
    features: Optional[List[str]] = None
    is_active: Optional[bool] = None

class LensModelResponse(LensModelBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    created_at: datetime
    updated_at: datetime
    company: Optional[CompanyResponse] = None
    variants: List[LensVariantResponse] = []
    power_ranges: List[PowerRangeResponse] = []
    variants_count: int = 0


# ===== Variant Pricing (commercial, append-only) =====
class VariantPricingCreate(BaseModel):
    """Internal creation payload. There is no public update/delete counterpart."""
    variant_id: int
    coating_id: Optional[int] = None
    availability: PricingAvailability
    # Exact fixed-point money. Phase 2 converts extracted float/text -> Decimal at
    # this commercial-write boundary.
    price_pair: Decimal = Field(..., ge=0, max_digits=12, decimal_places=2)
    currency: str = "EGP"
    source_catalog_id: int
    source_extraction_id: Optional[int] = None
    effective_from: Optional[datetime] = None
    power_scope: Optional[str] = Field(None, max_length=50)
    market_scope: Optional[str] = Field(None, max_length=50)
    # Generic, manufacturer-agnostic catalog-proven caveat: base price/
    # manufacturing eligibility are unaffected, but the FINAL price may need
    # separate manual/lab confirmation (e.g. PIXEL's "Hi Power" surcharge,
    # whose applicability trigger the catalog never states numerically).
    # NULL (the default) means no caveat. See PairFulfillment.price_confirmation_note.
    price_confirmation_note: Optional[str] = Field(None, max_length=255)

class VariantPricingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    variant_id: int
    coating_id: Optional[int]
    availability: PricingAvailability
    price_pair: Decimal
    currency: str
    source_catalog_id: int
    source_extraction_id: Optional[int]
    effective_from: datetime
    effective_to: Optional[datetime]
    power_scope: Optional[str]
    market_scope: Optional[str]
    created_at: datetime
    updated_at: datetime


# ===== Catalog option lists (read-only, for search-form filters) =====
class CoatingOption(BaseModel):
    """Distinct coating catalog entry, for populating a targeted-search Select.
    Carries the canonical `code` (what LensFilters.coating actually matches on)
    alongside display-only `name`/`name_ar`."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    name_ar: Optional[str] = None

class LensModelOption(BaseModel):
    """Distinct product/model catalog entry, for populating the Product Select
    without requiring the full LensModelResponse (variants/power_ranges)."""
    id: int
    name: str

class FilterOptionsResponse(BaseModel):
    """Distinct valid values for every targeted-search dimension, given whichever
    OTHER filters are currently selected (see GET /lens-models/filter-options).
    Every list already reflects strict AND against the caller's other filters;
    the frontend must not additionally narrow or relax them client-side."""
    lens_models: List[LensModelOption] = []
    index_value: List[float] = []
    category: List[str] = []
    design_variant: List[str] = []
    coating: List[CoatingOption] = []
    color_variant: List[str] = []
    treatment_band: List[str] = []


# ===== Prescription =====
class EyePrescription(BaseModel):
    sph: float = Field(..., ge=-30.0, le=30.0)
    cyl: Optional[float] = Field(0.0, ge=-10.0, le=10.0)
    axis: Optional[int] = Field(None, ge=0, le=180)
    add: Optional[float] = Field(None, ge=0.0, le=5.0)

    @model_validator(mode="after")
    def require_explicit_axis(self):
        if self.cyl and self.axis is None:
            raise ValueError("أدخل AXIS لهذه العين عند وجود CYL غير صفر")
        # Missing axis is harmless only for zero cylinder. Explicit 0/180
        # remain valid under the existing transposition convention.
        self.cyl = self.cyl or 0.0
        if self.axis is None:
            self.axis = 0
        return self

class PrescriptionBase(BaseModel):
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    od: EyePrescription
    os: EyePrescription
    pd: Optional[float] = Field(None, ge=40.0, le=80.0)
    notes: Optional[str] = None

class PrescriptionCreate(PrescriptionBase):
    pass

class PrescriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    customer_name: Optional[str]
    customer_phone: Optional[str]
    od_sph_original: float
    od_cyl_original: float
    od_axis_original: int
    od_sph: float
    od_cyl: float
    od_axis: int
    od_add: Optional[float]
    os_sph_original: float
    os_cyl_original: float
    os_axis_original: int
    os_sph: float
    os_cyl: float
    os_axis: int
    os_add: Optional[float]
    transposition_applied: bool
    pd: Optional[float]
    image_path: Optional[str]
    ocr_confidence: Optional[float]
    notes: Optional[str]
    created_at: datetime


# ===== Filters =====
class LensFilters(BaseModel):
    category: Optional[LensCategory] = None
    material: Optional[MaterialType] = None
    index_value: Optional[float] = None
    min_index: Optional[float] = None
    max_index: Optional[float] = None
    # commercial filters -> resolved against the CURRENT VariantPricing row,
    # never against legacy LensVariant.price / .availability
    availability: Optional[LensAvailability] = None      # STOCK / RX (BOTH = no filter)
    max_price: Optional[float] = None                    # compared to VariantPricing.price_pair
    coating: Optional[str] = None                        # coating code on the pricing row
    market_scope: Optional[str] = None                   # generic catalog market key (e.g. egypt / out_of_egypt)
    # optical filters (unchanged)
    design_type: Optional[DesignType] = None
    prefer_aspherical: Optional[bool] = None
    features: Optional[List[str]] = None
    company_id: Optional[int] = None
    is_active: Optional[bool] = True
    # V1.0.1 targeted-search dimensions - existing canonical DB fields only, no
    # migration. Applied as strict AND on top of match_lenses eligibility by the
    # product_search layer (the optical matcher itself ignores fields it does not
    # already read, so its logic is unchanged).
    lens_model_id: Optional[int] = None                  # LensModel.id  (Product / Model)
    design_variant: Optional[str] = None                 # LensVariant.design_variant (commercial design line)
    color_variant: Optional[str] = None                  # LensVariant.color_variant (actual colour only)
    # Phase 2 (ZEISS) targeted-search dimensions - same strict-AND rule as above.
    design_tier: Optional[str] = None                    # LensVariant.design_tier (tier within a design family)
    treatment_band: Optional[str] = None                      # LensVariant.treatment_band (treatment_band/technology band evidence)
    # Phase 4K-final: which optical sub-option to evaluate when ONE priced
    # commercial offer covers more than one (PowerRange.applicability_key) -
    # e.g. ZEISS's single-priced "Polarized / AdaptiveSun" offer, whose POL
    # and AdaptiveSun ranges differ. Unlike treatment_band (an IDENTITY
    # filter on LensVariant), this does NOT change which commercial options
    # are considered - it restricts WHICH PowerRange(s) are evaluated for
    # eligibility within them. None (default): every applicable sub-option
    # may prove eligibility, exactly as before this field existed - a row
    # that was never split (the overwhelming majority: HOYA, and any
    # non-split ZEISS row) is completely unaffected regardless of this value.
    applicability_key: Optional[str] = None


# ===== PDF import policy =====
class ExtractRequest(BaseModel):
    """Optional per-catalog import policy for POST /pdf-import/extract.

    The parser engine stays generic and manufacturer-agnostic; catalog-specific
    reading rules arrive here as caller-supplied policy (the foundation for
    future ZEISS / Essilor / Rodenstock catalogs without re-coding).

    dual_price_semantics: the ONLY accepted non-null value is
    'left_wholesale_right_retail' - the caller asserts that a two-value Price
    cell is '<wholesale> <retail>'. Any other non-null value is rejected 422,
    never a silent fallback. Absent/None -> unlabelled multi-value price cells
    stay UNRESOLVED (needs_review); wholesale is never persisted or exposed.
    """
    dual_price_semantics: Optional[str] = None
    use_vision: bool = False
    save_to_preview: bool = True


# ===== Bulk-confirm result =====
class BulkConfirmParkedItem(BaseModel):
    extraction_id: int
    reason: str

class BulkConfirmResult(BaseModel):
    success: bool = True
    catalog_id: int
    status: str
    confirmed: int
    skipped_unresolved: int
    true_duplicates_collapsed: int
    conflicts: int
    parked: List[BulkConfirmParkedItem] = []
    closed_previous_current: int = 0
    superseded_catalogs: List[int] = []


# ===== Match =====
class MatchRequest(BaseModel):
    prescription_id: int
    filters: Optional[LensFilters] = None
    prefer_stock: bool = True
    prefer_aspherical: bool = True

class LensMatchResult(BaseModel):
    lens_model: LensModelResponse
    variant: LensVariantResponse
    match_score: float = Field(..., ge=0, le=100)
    reason: str
    # matched PowerRange for a STOCK candidate (belongs to `source_pricing_id`);
    # None for RX made-to-order without an explicit range
    power_range: Optional[PowerRangeResponse] = None
    is_recommended: bool = True
    index_recommended: bool = False
    aspherical_recommended: bool = False
    stock_available: bool = True
    # ----- authoritative commercial data (from the CURRENT VariantPricing) -----
    availability: str = "rx"                     # "stock" / "rx"
    price_pair: Decimal
    currency: str = "EGP"
    coating_id: Optional[int] = None
    coating_code: Optional[str] = None
    coating_name: Optional[str] = None
    market_scope: Optional[str] = None
    power_scope: Optional[str] = None
    design_variant: Optional[str] = None
    color_variant: Optional[str] = None
    design_tier: Optional[str] = None
    treatment_band: Optional[str] = None
    source_pricing_id: int
    source_catalog_id: Optional[int] = None

# UNUSED as of Phase 3B: POST /prescriptions/{id}/match no longer returns this
# shape - it delegates to product_search.search() (ProductSearchResponse) so
# there is exactly one prescription-eligibility decision path. Kept only in
# case an external caller still deserialises it; not produced anywhere.
class MatchResponse(BaseModel):
    prescription: PrescriptionResponse
    results: List[LensMatchResult]
    total_matches: int
    stock_count: int
    rx_count: int
    transposition_applied: bool
    index_recommendation: str
    aspherical_recommendation: str


# ===== V1.0.1 product search (availability-first, targeted filters, alternatives) =====
class ProductSearchRequest(BaseModel):
    # New primary controls; every selected capability is required on the same offer.
    # None preserves scalar callers; [] means no additional restriction.
    customer_needs: Optional[List[Literal["blue_light", "photo_gray", "photo_brown", "impact_resistant"]]] = None
    customer_need: Optional[str] = None
    """Two modes:
      - "automatic"  -> every lens optically valid for the prescription
      - "targeted"   -> automatic result, then `filters` applied as strict AND;
                        never silently relaxed. Alternatives (if any) are
                        returned in a SEPARATE list, never mixed into the exact
                        result and never labelled as exact.
    """
    mode: str = "automatic"                       # "automatic" | "targeted"
    filters: Optional[LensFilters] = None
    prefer_stock: bool = True
    prefer_aspherical: bool = True
    include_alternatives: bool = True             # only computed when targeted + zero exact
    # V1.2 core-workflow: what the customer is actually being fitted for.
    # None preserves every prior caller's exact existing behaviour untouched
    # (no category restriction, original stored Rx used as-is - the deprecated
    # /match alias and any other caller that never sends this field are
    # unaffected). "distance"|"reading"|"bifocal"|"progressive" when set.
    use_mode: Optional[str] = None
    # V1.2 core-workflow: canonical, manufacturer-agnostic technology need.
    # "none"/None = no technology requirement. See app.technology_evidence
    # for the full evidence-backed capability registry.
    technology_intent: Optional[str] = None


class AvailabilityAnswer(BaseModel):
    # code: "stock_egypt" | "stock_out_of_egypt" | "stock_market_unknown" |
    #       "rx_only" | "split" | "power_eligibility_unknown" | "none"
    # "stock_market_unknown" (Phase 3C): a proven STOCK price/eligibility whose
    # catalog market_scope is NULL/unspecified - never claims Egypt, never
    # claims Out Of Egypt.
    code: str
    title: str
    detail: Optional[str] = None


# ===== V1.0.2 per-eye availability + pair fulfillment =====
class EyeAvailability(BaseModel):
    """Whether ONE eye is covered by any valid OR PowerRange of the SAME
    commercial option, evaluated independently per pricing route. Reuses the
    frozen optical eligibility - no new/duplicated range logic.

    Phase 3: eligibility is tri-state per route. `stock_egypt`/`stock_outside`/
    `rx` are True ONLY when a route is PROVEN eligible (an explicit PowerRange
    matches, or the row is genuinely unrestricted). The matching
    `*_unknown` flag is True when that route's real power applicability is not
    yet modeled (see PowerEligibilityStatus) - NEVER folded into the proven
    bool, and NEVER silently treated as ineligible either.

    Phase 3C: `stock_market_unknown` is a FOURTH, distinct route - a STOCK row
    whose catalog market_scope is genuinely unspecified (NULL). It is never
    folded into `stock_outside` (that would falsely claim a proven non-Egypt
    market) and never folded into `stock_egypt` either. Its own
    `stock_market_unknown_unknown` flag carries the same optical-eligibility-
    unresolved meaning as the other routes' `*_unknown` flags."""
    stock_egypt: bool = False
    stock_outside: bool = False
    stock_market_unknown: bool = False
    rx: bool = False
    stock_egypt_unknown: bool = False
    stock_outside_unknown: bool = False
    stock_market_unknown_unknown: bool = False
    rx_unknown: bool = False
    best: str = "none"          # stock_egypt | stock_outside | stock_market_unknown | rx | unknown | none


class TechnologyAddonInfo(BaseModel):
    """Seller-facing breakdown for a Type-B (base + catalog-proven add-on)
    technology fulfillment. See PairFulfillment.technology_addon below."""
    label: str              # catalog-printed add-on name(s), e.g. "Blue HMC+"
    base_price: Decimal     # the base row's own proven pair price
    addon_price: Decimal    # printed amount if unresolved; pair surcharge if proven
    unit_status: Literal["UNIT_PAIR_PROVEN", "UNIT_PER_LENS_PROVEN", "UNIT_UNRESOLVED"] = "UNIT_UNRESOLVED"


class PairFulfillment(BaseModel):
    """The best VERIFIED way to fulfill BOTH eyes as one pair from the SAME
    commercial option.

    `price_pair` is set ONLY when provenance is proven:
      * provenance="single_route"  -> ONE VariantPricing row's OR PowerRange(s)
        cover BOTH eyes; `source_pricing_ids` holds that single id.
      * provenance="unproven_mixed" -> both eyes are covered at the tier, but by
        SEPARATE VariantPricing rows of the same identity whose belonging to one
        catalog pricing offer cannot be proven from persistence
        (source_extraction_id differs). `price_pair` is null, `needs_review` is
        true; `source_pricing_ids` lists every covering row for transparency.
      * provenance="none" -> split / unavailable / eligibility_unknown.
    Never divided, summed, mixed (STOCK+RX) or estimated.

    status="eligibility_unknown" (Phase 3): no tier has BOTH eyes PROVEN
    eligible, and at least one eye's optical eligibility is itself unresolved
    (not proven ineligible - simply unproven, e.g. a catalog price whose real
    power limits are not yet modeled). The pair is NEVER reported as a proven
    STOCK/RX route in this case; `price_pair` stays null and `needs_review` is
    true, exactly like `unproven_mixed`."""
    status: str  # stock_egypt|stock_outside|stock_market_unknown|rx|split|unavailable|eligibility_unknown
    price_pair: Optional[Decimal] = None
    currency: Optional[str] = None
    source_pricing_ids: List[int] = []
    provenance: str = "none"                     # single_route | unproven_mixed | none
    needs_review: bool = False
    reason: str
    # Which PowerRange.applicability_key actually proved this pair (e.g. "POL"
    # vs "AdaptiveSun" under one ZEISS "Polarized / AdaptiveSun" offer). None
    # for every ordinary (undifferentiated) proven pair - ~all HOYA rows and
    # any non-split catalog row - and whenever provenance != "single_route".
    applicability_key: Optional[str] = None
    # Generic, manufacturer-agnostic catalog-proven caveat carried verbatim
    # from the proving VariantPricing row(s) (see
    # VariantPricing.price_confirmation_note) - e.g. PIXEL's "Hi Power"
    # surcharge, whose applicability the catalog leaves to manual/lab review.
    # Deliberately independent of `needs_review`: this pair IS proven and
    # `price_pair` IS the correct base price either way - this field only
    # says the FINAL price may still be adjusted after confirmation. None
    # (the default) means no caveat.
    price_confirmation_note: Optional[str] = None
    # V1.2 technology-fulfillment completeness: set ONLY when this pair's
    # price/status were adjusted to include a catalog-proven optional add-on
    # needed to satisfy the requested technology_intent (Type B fulfillment -
    # see app.technology_evidence.addon_completion). None means either no
    # technology_intent was requested, or the base row already included the
    # requested technology on its own (Type A - the ordinary, unmodified
    # case). With unresolved add-on units, price_pair is None and the base
    # price remains in technology_addon. A confirmation note always prevents
    # an unconditional final quotation, even if a numeric total is available.
    technology_addon: Optional[TechnologyAddonInfo] = None


class PerEyeProductResult(BaseModel):
    """One commercial option (strict identity) with independent OD / OS
    availability and the unified pair fulfillment."""
    company_id: int
    company_name: Optional[str] = None
    lens_model_id: int
    model_name: str
    category: Optional[str] = None
    variant_id: int
    index_value: float
    material: Optional[str] = None
    design_variant: Optional[str] = None
    color_variant: Optional[str] = None
    design_tier: Optional[str] = None
    treatment_band: Optional[str] = None
    coating_id: Optional[int] = None
    coating_code: Optional[str] = None
    coating_name: Optional[str] = None
    currency: str = "EGP"
    match_score: float = Field(..., ge=0, le=100)
    reason: str
    seller_recommendation_reason: Optional[str] = None
    manufacturing_location: Optional[Literal["egypt"]] = None
    # P0: the row's OWN catalog price, shown ONLY as informational detail for
    # a stock_egypt_range_unverified entry (ProductSearchResponse.
    # stock_egypt_unverified) - deliberately separate from
    # pair_fulfillment.price_pair, which stays None/provenance="none" for
    # these rows since their prescription compatibility is never proven.
    # None for every ordinary (proven) result.
    catalog_price_pair: Optional[Decimal] = None
    od: EyeAvailability
    os: EyeAvailability
    pair_fulfillment: PairFulfillment


class LensSearchGroup(BaseModel):
    # key: "stock_egypt" | "stock_out_of_egypt" | "stock_market_unknown" | "rx" |
    #      "split" | "eligibility_unknown"
    key: str
    label: str
    availability: str                            # "stock" | "rx" | "mixed" | "unknown"
    market: Optional[str] = None                 # "egypt" | "out_of_egypt" | "unknown" | None
    catalog_note: str = "حسب الكتالوج"           # STOCK label accuracy - not real-time inventory
    count: int
    results: List[PerEyeProductResult]


class AlternativeResult(BaseModel):
    result: LensMatchResult
    # which requested filters this alternative does NOT satisfy (why it is only
    # an alternative, not an exact match)
    relaxed_filters: List[str] = []
    # commercially useful proximity, existing dimensions only
    proximity_reason: str
    proximity_score: int = 0


class DerivedSearchRx(BaseModel):
    """The SEARCH-ONLY power actually evaluated for this request when it
    differs from the stored prescription (currently: the derived Reading
    Rx = Distance SPH + ADD per eye, CYL/AXIS unchanged). Never persisted -
    the stored prescription (see `prescription` above) is never mutated.
    Shown so the seller can verify what the application calculated, per the
    V1.2 core-workflow requirement that nobody manually computes a Reading Rx."""
    od_sph: float
    od_cyl: float
    od_axis: int
    os_sph: float
    os_cyl: float
    os_axis: int


class ProductSearchResponse(BaseModel):
    customer_needs: Optional[List[str]] = None
    customer_need: Optional[str] = None
    seller_alternatives: List[PerEyeProductResult] = []
    prescription: PrescriptionResponse
    mode: str
    # V1.2 core-workflow: echoes the request's use_mode/technology_intent so
    # the frontend can render the right labels without re-deriving them.
    use_mode: Optional[str] = None
    technology_intent: Optional[str] = None
    derived_search_rx: Optional[DerivedSearchRx] = None
    transposition_applied: bool
    index_recommendation: str
    aspherical_recommendation: str
    availability_answer: AvailabilityAnswer
    # exact result (automatic = all valid; targeted = valid AND all filters)
    exact_total: int
    best_match: Optional[PerEyeProductResult] = None
    groups: List[LensSearchGroup] = []
    # P0: Stock rows whose market IS proven Egypt but that print NO catalog
    # PowerRange at all (e.g. SEIKO/BBGR today - generic, not hardcoded to
    # any manufacturer). Entirely separate from exact_total/groups/
    # best_match - never a prescription match, never actionable, never a
    # confirmed price for this Rx. Each entry's own catalog price is still
    # shown via PerEyeProductResult.catalog_price_pair for transparency.
    stock_egypt_unverified: List[PerEyeProductResult] = []
    stock_egypt_count: int = 0                   # full-pair STOCK Egypt
    stock_out_of_egypt_count: int = 0            # full-pair STOCK Out Of Egypt
    stock_market_unknown_count: int = 0          # full-pair STOCK, catalog market unspecified
    rx_count: int = 0                            # full-pair RX
    split_count: int = 0                         # split / no unified route
    eligibility_unknown_count: int = 0            # power applicability unresolved
    # populated ONLY for targeted mode when exact_total == 0
    alternatives: List[AlternativeResult] = []
    alternatives_note: Optional[str] = None
    # V1.0.2 fix - the SAME requested commercial option(s) that satisfy every
    # IDENTITY filter but fail the requested availability / market / max_price
    # gate. Availability intelligence ONLY - never counted as exact, never
    # relaxes the requested filters.
    availability_intelligence: List[PerEyeProductResult] = []
    availability_intelligence_note: Optional[str] = None


# ===== OCR =====
class OCRResponse(BaseModel):
    success: bool
    prescription: Optional[PrescriptionBase] = None
    confidence: float = Field(0.0, ge=0, le=100)
    raw_text: Optional[str] = None
    message: Optional[str] = None


# ===== PDF Import =====
class PDFImportRequest(BaseModel):
    company_id: int
    catalog_id: Optional[int] = None
    override_existing: bool = False

class PDFImportResponse(BaseModel):
    success: bool
    extracted_models: int
    extracted_variants: int
    extracted_ranges: int
    errors: List[str]
    message: str


# ===== Bulk Upload =====
class BulkPowerRange(BaseModel):
    lens_model_name: str
    variant_material: MaterialType
    variant_index: float
    availability: LensAvailability
    design_type: DesignType = DesignType.SPHERICAL
    is_aspherical: bool = False
    sph_min: float
    sph_max: float
    cyl_min: float = -10.0
    cyl_max: float = 0.0
    add_min: Optional[float] = None
    add_max: Optional[float] = None
    price: float

class BulkUploadRequest(BaseModel):
    company_id: int
    ranges: List[BulkPowerRange]
