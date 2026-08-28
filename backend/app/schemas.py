"""
مخططات Pydantic النهائية
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
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
    SPHERICAL = "spherical"
    ASPHERICAL = "aspherical"
    DOUBLE_ASPHERICAL = "double_aspherical"
    FREE_FORM = "free_form"


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
    extracted_price: Optional[float] = None
    extracted_features: Optional[List[str]] = None

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
    extracted_price: Optional[float] = None
    extracted_features: Optional[List[str]] = None
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
    modified_data: Optional[Dict[str, Any]]
    created_at: datetime
    reviewed_at: Optional[datetime]


# ===== Power Range =====
class PowerRangeBase(BaseModel):
    sph_min: float = Field(..., ge=-30.0, le=30.0)
    sph_max: float = Field(..., ge=-30.0, le=30.0)
    cyl_min: float = Field(-10.0, ge=-10.0, le=0.0)
    cyl_max: float = Field(0.0, ge=-10.0, le=0.0)
    add_min: Optional[float] = Field(None, ge=0.0, le=5.0)
    add_max: Optional[float] = Field(None, ge=0.0, le=5.0)
    axis_min: Optional[int] = Field(0, ge=0, le=180)
    axis_max: Optional[int] = Field(180, ge=0, le=180)
    max_cyl_for_high_sph: Optional[float] = None
    sph_threshold: Optional[float] = None
    notes: Optional[str] = None

class PowerRangeCreate(PowerRangeBase):
    lens_model_id: int
    variant_id: Optional[int] = None

class PowerRangeResponse(PowerRangeBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    lens_model_id: int
    variant_id: Optional[int]
    created_at: datetime


# ===== Lens Variant =====
class LensVariantBase(BaseModel):
    material: MaterialType
    index_value: float = Field(..., ge=1.0, le=2.0)
    availability: LensAvailability = LensAvailability.STOCK
    design_type: DesignType = DesignType.SPHERICAL
    is_aspherical: bool = False
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
    availability: Optional[LensAvailability] = None
    design_type: Optional[DesignType] = None
    prefer_aspherical: Optional[bool] = None
    features: Optional[List[str]] = None
    max_price: Optional[float] = None
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
    power_range: Optional[PowerRangeResponse] = None
    is_recommended: bool = True
    index_recommended: bool = False
    aspherical_recommended: bool = False
    stock_available: bool = True

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
