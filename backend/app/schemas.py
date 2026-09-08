"""
مخططات Pydantic النهائية
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
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
    extracted_price: Optional[float] = None
    extracted_features: Optional[List[str]] = None
    # commercial identity (parser-populated in Phase 4)
    extracted_design: Optional[str] = None
    extracted_color_variant: Optional[str] = None
    extracted_market_scope: Optional[str] = None
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
    extracted_price: Optional[float] = None
    extracted_features: Optional[List[str]] = None
    # commercial identity + coating human correction / review (mirrors CatalogExtraction)
    extracted_design: Optional[str] = None
    extracted_color_variant: Optional[str] = None
    extracted_market_scope: Optional[str] = None
    extracted_coating: Optional[str] = None
    coating_id: Optional[int] = None
    coating_extraction_status: Optional[CoatingExtractionStatus] = None
    coating_confidence: Optional[float] = None
    coating_review_notes: Optional[str] = None
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


# ===== Prescription =====
class EyePrescription(BaseModel):
    sph: float = Field(..., ge=-30.0, le=30.0)
    cyl: Optional[float] = Field(0.0, ge=-10.0, le=10.0)
    axis: Optional[int] = Field(0, ge=0, le=180)
    add: Optional[float] = Field(0.0, ge=0.0, le=5.0)

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
    source_pricing_id: int
    source_catalog_id: Optional[int] = None

class MatchResponse(BaseModel):
    prescription: PrescriptionResponse
    results: List[LensMatchResult]
    total_matches: int
    stock_count: int
    rx_count: int
    transposition_applied: bool
    index_recommendation: str
    aspherical_recommendation: str


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
