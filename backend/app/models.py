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
    Enum, JSON, Index, CheckConstraint, Table
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
    SPHERICAL = "spherical"
    ASPHERICAL = "aspherical"
    DOUBLE_ASPHERICAL = "double_aspherical"
    FREE_FORM = "free_form"


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

    processing_status = Column(String(20), default="pending")
    processing_errors = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="catalogs")
    extractions = relationship("CatalogExtraction", back_populates="catalog", cascade="all, delete-orphan")


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

    extracted_price = Column(Float, nullable=True)
    extracted_features = Column(JSON, nullable=True)

    # حالة التأكيد
    status = Column(String(20), default="pending")  # pending, confirmed, rejected, modified
    reviewed_by = Column(String(100), nullable=True)
    review_notes = Column(Text, nullable=True)

    # بيانات معدلة (إذا تم التعديل)
    modified_data = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)

    catalog = relationship("Catalog", back_populates="extractions")


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
    availability = Column(Enum(LensAvailability), nullable=False, default=LensAvailability.STOCK)

    # التصميم
    design_type = Column(Enum(DesignType), default=DesignType.SPHERICAL)
    is_aspherical = Column(Boolean, default=False)  # للبحث السريع

    price = Column(Float, nullable=False)
    currency = Column(String(10), default="USD")
    diameter = Column(Integer, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lens_model = relationship("LensModel", back_populates="variants")
    power_ranges = relationship("PowerRange", back_populates="variant", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_variant_model_material', 'lens_model_id', 'material'),
        Index('idx_variant_model_index', 'lens_model_id', 'index_value'),
        Index('idx_variant_aspherical', 'is_aspherical'),
    )


# ===== نطاقات القوة =====
class PowerRange(Base):
    __tablename__ = "power_ranges"

    id = Column(Integer, primary_key=True, index=True)
    lens_model_id = Column(Integer, ForeignKey("lens_models.id"), nullable=False)
    variant_id = Column(Integer, ForeignKey("lens_variants.id"), nullable=True)

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

    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    lens_model = relationship("LensModel", back_populates="power_ranges")
    variant = relationship("LensVariant", back_populates="power_ranges")

    __table_args__ = (
        Index('idx_power_sph', 'sph_min', 'sph_max'),
        Index('idx_power_cyl', 'cyl_min', 'cyl_max'),
        Index('idx_power_add', 'add_min', 'add_max'),
        Index('idx_power_variant', 'variant_id', 'sph_min', 'sph_max'),
    )

    @validates('sph_min', 'sph_max')
    def validate_sph(self, key, value):
        if value < -30.0 or value > 30.0:
            raise ValueError(f"SPH must be between -30 and +30")
        return round(value, 2)

    @validates('cyl_min', 'cyl_max')
    def validate_cyl(self, key, value):
        if value < -10.0 or value > 0.0:
            raise ValueError(f"CYL must be between -10 and 0")
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
