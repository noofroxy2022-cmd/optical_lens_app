"""
CRUD النهائي - يدعم Preview & Confirm + Transposition
"""
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import List, Optional
from app import models, schemas


# ===== Company =====
def create_company(db: Session, company: schemas.CompanyCreate) -> models.Company:
    db_company = models.Company(**company.model_dump())
    db.add(db_company)
    db.commit()
    db.refresh(db_company)
    return db_company

def get_company(db: Session, company_id: int) -> Optional[models.Company]:
    return db.query(models.Company).filter(
        models.Company.id == company_id,
        models.Company.is_deleted == False
    ).first()

def get_companies(db: Session, skip=0, limit=100, include_inactive=False) -> List[models.Company]:
    query = db.query(models.Company).filter(models.Company.is_deleted == False)
    if not include_inactive:
        query = query.filter(models.Company.is_active == True)
    return query.offset(skip).limit(limit).all()

def update_company(db: Session, company_id: int, update: schemas.CompanyUpdate) -> Optional[models.Company]:
    company = get_company(db, company_id)
    if not company:
        return None
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    db.commit()
    db.refresh(company)
    return company

def toggle_company_active(db: Session, company_id: int) -> Optional[models.Company]:
    company = get_company(db, company_id)
    if not company:
        return None
    company.is_active = not company.is_active
    db.commit()
    db.refresh(company)
    return company

def delete_company(db: Session, company_id: int, soft=True) -> bool:
    company = get_company(db, company_id)
    if not company:
        return False
    if soft:
        company.is_deleted = True
        company.is_active = False
    else:
        db.delete(company)
    db.commit()
    return True


# ===== Catalog =====
def create_catalog(db: Session, company_id: int, filename: str, file_path: str, file_size=None):
    catalog = models.Catalog(
        company_id=company_id, filename=filename,
        file_path=file_path, file_size=file_size,
        processing_status="pending"
    )
    db.add(catalog)
    db.commit()
    db.refresh(catalog)
    return catalog

def get_catalog(db: Session, catalog_id: int) -> Optional[models.Catalog]:
    return db.query(models.Catalog).filter(models.Catalog.id == catalog_id).first()

def get_catalogs_by_company(db: Session, company_id: int) -> List[models.Catalog]:
    return db.query(models.Catalog).filter(models.Catalog.company_id == company_id).all()


# ===== Catalog Extraction (Preview & Confirm) =====
def create_extraction(db: Session, extraction: schemas.CatalogExtractionCreate) -> models.CatalogExtraction:
    data = extraction.model_dump()
    db_ext = models.CatalogExtraction(**data)
    db.add(db_ext)
    db.commit()
    db.refresh(db_ext)
    return db_ext

def get_extractions_by_catalog(db: Session, catalog_id: int, status=None) -> List[models.CatalogExtraction]:
    query = db.query(models.CatalogExtraction).filter(models.CatalogExtraction.catalog_id == catalog_id)
    if status:
        query = query.filter(models.CatalogExtraction.status == status)
    return query.all()

def get_extraction(db: Session, extraction_id: int) -> Optional[models.CatalogExtraction]:
    return db.query(models.CatalogExtraction).filter(models.CatalogExtraction.id == extraction_id).first()

def update_extraction(db: Session, extraction_id: int, update: schemas.CatalogExtractionUpdate) -> Optional[models.CatalogExtraction]:
    ext = get_extraction(db, extraction_id)
    if not ext:
        return None
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(ext, field, value)
    db.commit()
    db.refresh(ext)
    return ext

def confirm_extraction(db: Session, extraction_id: int, reviewed_by: str = "system") -> Optional[models.CatalogExtraction]:
    ext = get_extraction(db, extraction_id)
    if not ext:
        return None
    ext.status = "confirmed"
    ext.reviewed_by = reviewed_by
    ext.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(ext)
    return ext

def reject_extraction(db: Session, extraction_id: int, notes: str = "") -> Optional[models.CatalogExtraction]:
    ext = get_extraction(db, extraction_id)
    if not ext:
        return None
    ext.status = "rejected"
    ext.review_notes = notes
    ext.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(ext)
    return ext


def apply_family_review_override(
    db: Session, extraction_id: int, family: str, reviewed_by: str = "reviewer"
) -> Optional[models.CatalogExtraction]:
    """Record a human-reviewed product family for one extraction.

    The value is written into the existing modified_data overlay that Phase 2
    bulk confirmation reads (`modified_data["name"]`), together with provenance
    marking it as human review rather than parser inference. Generic - `family`
    is caller-supplied; nothing catalog- or manufacturer-specific is hardcoded,
    and the parser's own source-derived result is left untouched.
    """
    ext = get_extraction(db, extraction_id)
    if not ext:
        return None
    fam = (family or "").strip()
    if not fam:
        return ext
    md = dict(ext.modified_data or {})
    md["name"] = fam
    md["family_source"] = "human_review"
    md["family_reviewed_by"] = reviewed_by
    md["family_reviewed_at"] = datetime.utcnow().isoformat()
    ext.modified_data = md
    note = f"product family set to {fam!r} by {reviewed_by} (human review)"
    ext.review_notes = "; ".join(x for x in (ext.review_notes, note) if x)
    db.commit()
    db.refresh(ext)
    return ext


# ===== Lens Model =====
def create_lens_model(db: Session, model: schemas.LensModelCreate) -> models.LensModel:
    data = model.model_dump()
    db_model = models.LensModel(**data)
    db.add(db_model)
    db.commit()
    db.refresh(db_model)
    return db_model

def get_lens_model(db: Session, model_id: int) -> Optional[models.LensModel]:
    return db.query(models.LensModel).options(
        joinedload(models.LensModel.company),
        joinedload(models.LensModel.variants),
        joinedload(models.LensModel.power_ranges)
    ).filter(
        models.LensModel.id == model_id,
        models.LensModel.is_deleted == False
    ).first()

def get_lens_models(db: Session, skip=0, limit=100, company_id=None, category=None, include_inactive=False):
    query = db.query(models.LensModel).filter(models.LensModel.is_deleted == False)
    if not include_inactive:
        query = query.filter(models.LensModel.is_active == True)
    if company_id:
        query = query.filter(models.LensModel.company_id == company_id)
    if category:
        query = query.filter(models.LensModel.category == category)
    return query.offset(skip).limit(limit).all()

def update_lens_model(db: Session, model_id: int, update: schemas.LensModelUpdate) -> Optional[models.LensModel]:
    model = get_lens_model(db, model_id)
    if not model:
        return None
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(model, field, value)
    db.commit()
    db.refresh(model)
    return model

def toggle_lens_model_active(db: Session, model_id: int) -> Optional[models.LensModel]:
    model = get_lens_model(db, model_id)
    if not model:
        return None
    model.is_active = not model.is_active
    db.commit()
    db.refresh(model)
    return model

def delete_lens_model(db: Session, model_id: int) -> bool:
    model = get_lens_model(db, model_id)
    if not model:
        return False
    db.delete(model)
    db.commit()
    return True


# ===== Lens Variant =====
def create_lens_variant(db: Session, variant: schemas.LensVariantCreate) -> models.LensVariant:
    data = variant.model_dump()
    db_variant = models.LensVariant(**data)
    db.add(db_variant)
    db.commit()
    db.refresh(db_variant)
    return db_variant

def get_lens_variant(db: Session, variant_id: int) -> Optional[models.LensVariant]:
    return db.query(models.LensVariant).options(
        joinedload(models.LensVariant.lens_model),
        joinedload(models.LensVariant.power_ranges)
    ).filter(models.LensVariant.id == variant_id).first()

def get_variants_by_model(db: Session, model_id: int) -> List[models.LensVariant]:
    return db.query(models.LensVariant).filter(
        models.LensVariant.lens_model_id == model_id,
        models.LensVariant.is_active == True
    ).all()

def update_lens_variant(db: Session, variant_id: int, **kwargs) -> Optional[models.LensVariant]:
    variant = get_lens_variant(db, variant_id)
    if not variant:
        return None
    for key, value in kwargs.items():
        setattr(variant, key, value)
    db.commit()
    db.refresh(variant)
    return variant

def delete_lens_variant(db: Session, variant_id: int) -> bool:
    variant = get_lens_variant(db, variant_id)
    if not variant:
        return False
    db.delete(variant)
    db.commit()
    return True


# ===== Power Range =====
def create_power_range(db: Session, power_range: schemas.PowerRangeCreate) -> models.PowerRange:
    data = power_range.model_dump()
    db_range = models.PowerRange(**data)
    db.add(db_range)
    db.commit()
    db.refresh(db_range)
    return db_range

def get_power_ranges_by_model(db: Session, model_id: int) -> List[models.PowerRange]:
    return db.query(models.PowerRange).filter(models.PowerRange.lens_model_id == model_id).all()

def get_power_ranges_by_variant(db: Session, variant_id: int) -> List[models.PowerRange]:
    return db.query(models.PowerRange).filter(models.PowerRange.variant_id == variant_id).all()

def delete_power_range(db: Session, range_id: int) -> bool:
    pr = db.query(models.PowerRange).filter(models.PowerRange.id == range_id).first()
    if not pr:
        return False
    db.delete(pr)
    db.commit()
    return True


# ===== Prescription =====
def create_prescription(db: Session, prescription: schemas.PrescriptionCreate,
                       image_path=None, ocr_confidence=None) -> models.Prescription:
    data = prescription.model_dump()
    od = data.pop("od")
    os = data.pop("os")

    # تطبيق Transposition
    from app.lens_matcher import TranspositionEngine
    trans = TranspositionEngine()

    od_trans = trans.transpose(od["sph"], od.get("cyl", 0.0), od.get("axis", 0))
    os_trans = trans.transpose(os["sph"], os.get("cyl", 0.0), os.get("axis", 0))

    transposition_applied = (od.get("cyl", 0) > 0) or (os.get("cyl", 0) > 0)

    db_prescription = models.Prescription(
        **data,
        od_sph_original=od["sph"],
        od_cyl_original=od.get("cyl", 0.0),
        od_axis_original=od.get("axis", 0),
        od_sph=od_trans[0],
        od_cyl=od_trans[1],
        od_axis=od_trans[2],
        od_add=od.get("add", 0.0),
        os_sph_original=os["sph"],
        os_cyl_original=os.get("cyl", 0.0),
        os_axis_original=os.get("axis", 0),
        os_sph=os_trans[0],
        os_cyl=os_trans[1],
        os_axis=os_trans[2],
        os_add=os.get("add", 0.0),
        transposition_applied=transposition_applied,
        image_path=image_path,
        ocr_confidence=ocr_confidence
    )
    db.add(db_prescription)
    db.commit()
    db.refresh(db_prescription)
    return db_prescription

def get_prescription(db: Session, prescription_id: int) -> Optional[models.Prescription]:
    return db.query(models.Prescription).filter(models.Prescription.id == prescription_id).first()

def get_prescriptions(db: Session, skip=0, limit=100) -> List[models.Prescription]:
    return db.query(models.Prescription).order_by(models.Prescription.created_at.desc()).offset(skip).limit(limit).all()

def delete_prescription(db: Session, prescription_id: int) -> bool:
    prescription = get_prescription(db, prescription_id)
    if prescription:
        db.delete(prescription)
        db.commit()
        return True
    return False


# ===== Coating =====
def get_coating(db: Session, coating_id: int) -> Optional[models.Coating]:
    return db.query(models.Coating).filter(models.Coating.id == coating_id).first()

def get_coating_by_code(db: Session, code: str) -> Optional[models.Coating]:
    return db.query(models.Coating).filter(models.Coating.code == code).first()

def list_coatings(db: Session, include_inactive: bool = False) -> List[models.Coating]:
    query = db.query(models.Coating)
    if not include_inactive:
        query = query.filter(models.Coating.is_active == True)
    return query.order_by(models.Coating.code).all()

def get_or_create_coating(
    db: Session, code: str, name: Optional[str] = None, name_ar: Optional[str] = None
) -> models.Coating:
    existing = get_coating_by_code(db, code)
    if existing:
        return existing
    coating = models.Coating(code=code, name=name or code, name_ar=name_ar)
    db.add(coating)
    db.commit()
    db.refresh(coating)
    return coating


# ===== Variant Pricing (append-only commercial history) =====
# Reads --------------------------------------------------------------------------
def _current_pricing_query(db: Session, variant_id: int):
    return db.query(models.VariantPricing).filter(
        models.VariantPricing.variant_id == variant_id,
        models.VariantPricing.effective_to.is_(None),
    )

def get_current_pricing_for_variant(db: Session, variant_id: int) -> List[models.VariantPricing]:
    """All rows that are currently in effect for a variant."""
    return _current_pricing_query(db, variant_id).all()

def get_current_pricing(
    db: Session,
    variant_id: int,
    availability,
    coating_id: Optional[int] = None,
    power_scope: Optional[str] = None,
    market_scope: Optional[str] = None,
) -> Optional[models.VariantPricing]:
    """The single current row for a precise commercial identity (NULL-aware)."""
    query = _current_pricing_query(db, variant_id).filter(
        models.VariantPricing.availability == availability
    )
    query = query.filter(
        models.VariantPricing.coating_id == coating_id
        if coating_id is not None
        else models.VariantPricing.coating_id.is_(None)
    )
    query = query.filter(
        models.VariantPricing.power_scope == power_scope
        if power_scope is not None
        else models.VariantPricing.power_scope.is_(None)
    )
    query = query.filter(
        models.VariantPricing.market_scope == market_scope
        if market_scope is not None
        else models.VariantPricing.market_scope.is_(None)
    )
    return query.first()

def get_pricing_history(
    db: Session,
    variant_id: int,
    coating_id: Optional[int] = None,
    availability=None,
) -> List[models.VariantPricing]:
    """Full append-only history for a variant, oldest first."""
    query = db.query(models.VariantPricing).filter(
        models.VariantPricing.variant_id == variant_id
    )
    if coating_id is not None:
        query = query.filter(models.VariantPricing.coating_id == coating_id)
    if availability is not None:
        query = query.filter(models.VariantPricing.availability == availability)
    return query.order_by(
        models.VariantPricing.effective_from.asc(), models.VariantPricing.id.asc()
    ).all()

# Writes (lifecycle only - no manual update/delete) -----------------------------
def create_variant_pricing_internal(
    db: Session, data: schemas.VariantPricingCreate
) -> models.VariantPricing:
    """The ONLY way to add a price. Appends a new current row."""
    payload = data.model_dump()
    if payload.get("effective_from") is None:
        payload["effective_from"] = datetime.utcnow()
    payload["availability"] = models.PricingAvailability(data.availability.value)
    pricing = models.VariantPricing(**payload)
    db.add(pricing)
    db.commit()
    db.refresh(pricing)
    return pricing

def close_current_pricing(
    db: Session, pricing_id: int, effective_to: Optional[datetime] = None
) -> Optional[models.VariantPricing]:
    """Close a single current row by stamping effective_to. No-op if already closed."""
    pricing = db.query(models.VariantPricing).filter(
        models.VariantPricing.id == pricing_id
    ).first()
    if not pricing or pricing.effective_to is not None:
        return pricing
    pricing.effective_to = effective_to or datetime.utcnow()
    db.commit()
    db.refresh(pricing)
    return pricing

def supersede_pricing(
    db: Session,
    old_pricing_id: int,
    new_data: schemas.VariantPricingCreate,
    at: Optional[datetime] = None,
) -> models.VariantPricing:
    """Close the old current row and append its replacement at the same instant."""
    at = at or datetime.utcnow()
    old = db.query(models.VariantPricing).filter(
        models.VariantPricing.id == old_pricing_id
    ).first()
    if old is not None and old.effective_to is None:
        old.effective_to = at
        db.flush()
    payload = new_data.model_dump()
    payload["effective_from"] = at
    payload["availability"] = models.PricingAvailability(new_data.availability.value)
    replacement = models.VariantPricing(**payload)
    db.add(replacement)
    db.commit()
    db.refresh(replacement)
    return replacement

def close_company_current_pricing(
    db: Session, company_id: int, effective_to: Optional[datetime] = None
) -> int:
    """Close every current price for a company (used when a catalog is replaced).

    Returns the number of rows closed.
    """
    stamp = effective_to or datetime.utcnow()
    rows = _company_current_pricing_rows(db, company_id)
    for row in rows:
        row.effective_to = stamp
    db.commit()
    return len(rows)


def _company_current_pricing_rows(db: Session, company_id: int) -> List[models.VariantPricing]:
    return (
        db.query(models.VariantPricing)
        .join(models.LensVariant, models.VariantPricing.variant_id == models.LensVariant.id)
        .join(models.LensModel, models.LensVariant.lens_model_id == models.LensModel.id)
        .filter(
            models.LensModel.company_id == company_id,
            models.VariantPricing.effective_to.is_(None),
        )
        .all()
    )


# ===== Catalog processing status (parser/processing state, NOT the lifecycle) =====
def update_catalog_status(db: Session, catalog_id: int, status: str, errors: Optional[str] = None):
    catalog = get_catalog(db, catalog_id)
    if not catalog:
        return None
    catalog.processing_status = status
    if errors is not None:
        catalog.processing_errors = errors
    db.commit()
    db.refresh(catalog)
    return catalog


# ===== Phase 2: commercial import / confirmation ================================
class CommercialValidationError(Exception):
    """Raised when a catalog cannot be commercially confirmed. Carries every
    reason found (the whole catalog is blocked, never partially applied)."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(str(e) for e in self.errors))


def _fmt_scope_num(value) -> str:
    return f"{float(value):+.2f}"


def build_power_scope(
    sph_min=None, sph_max=None, cyl_min=None, cyl_max=None, add_min=None, add_max=None,
    total_power_min=None, total_power_max=None, max_cyl_abs=None,
) -> Optional[str]:
    """Canonical, deterministic power-scope key (single source of truth).

    - Built only from normalised numeric range bounds, never from raw strings.
    - Order-independent (min/max swapped) and precision-independent
      (-6, -6.0, -6.00 all collapse to the same token).
    - Returns None when no real range is represented (e.g. RX with no
      manufacturing limits).
    """
    def real(a, b):
        vals = [v for v in (a, b) if v is not None]
        return bool(vals) and any(float(v) != 0.0 for v in vals)

    parts = []
    if real(sph_min, sph_max):
        lo, hi = sorted((float(sph_min or 0.0), float(sph_max or 0.0)))
        parts.append(f"sph:{_fmt_scope_num(lo)}/{_fmt_scope_num(hi)}")
    if real(cyl_min, cyl_max):
        lo, hi = sorted((float(cyl_min or 0.0), float(cyl_max or 0.0)))
        parts.append(f"cyl:{_fmt_scope_num(lo)}/{_fmt_scope_num(hi)}")
    if real(add_min, add_max):
        lo, hi = sorted((float(add_min or 0.0), float(add_max or 0.0)))
        parts.append(f"add:{_fmt_scope_num(lo)}/{_fmt_scope_num(hi)}")
    # G3 "Total Sph+Cyl" clause - keeps distinct G3 clauses from colliding in
    # commercial identity even when their coarse sph/cyl boxes coincide.
    if total_power_min is not None or total_power_max is not None:
        lo, hi = sorted((float(total_power_min or 0.0), float(total_power_max or 0.0)))
        parts.append(f"total:{_fmt_scope_num(lo)}/{_fmt_scope_num(hi)}")
    if max_cyl_abs is not None:
        parts.append(f"maxcyl:{_fmt_scope_num(float(max_cyl_abs))}")
    return "|".join(parts) if parts else None


def to_price_decimal(value) -> Decimal:
    """Safe conversion of an extracted price (float/str/Decimal) to a 2dp Decimal
    at the commercial-write boundary. Never rounds a real value and never does
    commercial arithmetic - it only pads scale (19.9 -> 19.90) and rejects
    anything not representable as an exact catalog price."""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("missing price")
    try:
        d = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"invalid price {value!r}")
    if not d.is_finite() or d <= 0:
        raise ValueError(f"non-positive price {value!r}")
    if d.as_tuple().exponent < -2:
        raise ValueError(f"price {value!r} has more than 2 decimal places")
    d = d.quantize(Decimal("0.01"))
    if len(d.as_tuple().digits) > 12:
        raise ValueError(f"price {value!r} exceeds NUMERIC(12,2)")
    return d


def _coerce_enum(enum_cls, value, default=None):
    if value is None:
        return default
    if isinstance(value, enum_cls):
        return value
    s = str(value).strip()
    for member in enum_cls:
        if s == member.value or s.lower() in (member.value.lower(), member.name.lower()):
            return member
    return default


def _norm(text_value) -> str:
    return (text_value or "").strip().lower()


def _prepare_extraction_row(ext) -> dict:
    """Build the effective commercial view of one extraction and validate it.

    Returns {"row": <dict>} on success or {"errors": [...]} on failure. Human
    review lives in ext.modified_data (overlaying the parser's extracted_* fields);
    the commercial identity axes design_variant / color_variant / market_scope /
    design_type / is_aspherical come only from that review overlay.
    """
    tag = f"extraction {ext.id}"
    errors = []
    md = ext.modified_data or {}

    if ext.status != "confirmed":
        return {"errors": [f"{tag}: not review-approved (status={ext.status!r})"]}

    cs = ext.coating_extraction_status
    coating_ref = None
    if cs is None or cs == models.CoatingExtractionStatus.NOT_FOUND:
        errors.append(f"{tag}: coating unresolved (not_found)")
    elif cs == models.CoatingExtractionStatus.RESOLVED:
        if ext.coating_id is not None:
            coating_ref = ("id", int(ext.coating_id))
        elif ext.extracted_coating:
            coating_ref = ("code", str(ext.extracted_coating).strip())
        else:
            errors.append(f"{tag}: coating RESOLVED but no coating_id / extracted_coating")
    # EXPLICIT_NONE -> coating_ref stays None (valid)

    avail_raw = _norm(md.get("availability") or ext.extracted_availability)
    availability = None
    if avail_raw in ("stock", "rx"):
        availability = (
            models.PricingAvailability.STOCK if avail_raw == "stock"
            else models.PricingAvailability.RX
        )
    else:
        errors.append(f"{tag}: invalid commercial availability {avail_raw!r} (STOCK/RX only)")

    price = None
    try:
        price = to_price_decimal(md.get("price", ext.extracted_price))
    except ValueError as ve:
        errors.append(f"{tag}: {ve}")

    # A range exists ONLY when the source extraction carried a COMPLETE explicit
    # bound pair. A lone bound, or a value that is really a persisted default
    # (e.g. the parser's old cyl -10..0 fallback), is not catalog manufacturing
    # evidence and must never be turned into an RX range.
    def _pair(a, b):
        return (a, b) if (a is not None and b is not None) else (None, None)

    sph_min, sph_max = _pair(md.get("sph_min", ext.sph_min), md.get("sph_max", ext.sph_max))
    cyl_min, cyl_max = _pair(md.get("cyl_min", ext.cyl_min), md.get("cyl_max", ext.cyl_max))
    add_min, add_max = _pair(md.get("add_min", ext.add_min), md.get("add_max", ext.add_max))
    # G3 "Total Sph+Cyl" clause (nullable; human review overlay wins). These are
    # the AUTHORITATIVE G3 constraint; sph_*/cyl_* above are only a coarse box.
    total_power_min = md.get("total_power_min", ext.extracted_total_power_min)
    total_power_max = md.get("total_power_max", ext.extracted_total_power_max)
    max_cyl_abs = md.get("max_cyl_abs", ext.extracted_max_cyl_abs)
    power_scope = build_power_scope(
        sph_min, sph_max, cyl_min, cyl_max, add_min, add_max,
        total_power_min, total_power_max, max_cyl_abs,
    )
    has_range = power_scope is not None
    if availability == models.PricingAvailability.STOCK and not has_range:
        errors.append(f"{tag}: STOCK requires PowerRange data (no numeric sph/cyl/add range)")

    name = (md.get("name") or ext.extracted_name or "").strip()
    if not name:
        errors.append(f"{tag}: missing product name")
    elif name == models.UNRESOLVED_FAMILY_NAME:
        # parser could not derive the family from the PDF; a human review overlay
        # (modified_data["name"] with family_source == "human_review") must supply it
        errors.append(f"{tag}: unresolved product family - needs human review")
        name = ""

    material_enum = _coerce_enum(
        models.MaterialType, md.get("material") or ext.extracted_material or "CR39"
    )
    if material_enum is None:
        errors.append(f"{tag}: invalid material {md.get('material') or ext.extracted_material!r}")

    idx_raw = md.get("index", ext.extracted_index)
    idx = None
    if idx_raw is None:
        errors.append(f"{tag}: missing index")
    else:
        try:
            idx = round(float(idx_raw), 2)
        except (TypeError, ValueError):
            errors.append(f"{tag}: invalid index {idx_raw!r}")

    design_type_enum = _coerce_enum(
        models.DesignType, md.get("design_type"), models.DesignType.SPHERICAL
    )
    if design_type_enum is None:
        errors.append(f"{tag}: invalid design_type {md.get('design_type')!r}")
    is_asph = bool(md.get("is_aspherical", False))
    category_enum = _coerce_enum(
        models.LensCategory, md.get("category") or ext.extracted_category,
        models.LensCategory.SINGLE_VISION,
    )
    # human review overlay (modified_data) wins over the parser-extracted column
    design_variant = md.get("design_variant") or ext.extracted_design or None
    color_variant = md.get("color_variant") or ext.extracted_color_variant or None
    market_scope = md.get("market_scope") or ext.extracted_market_scope or None
    # Phase 2 (ZEISS): two more independent commercial axes, same overlay rule.
    design_tier = md.get("design_tier") or ext.extracted_design_tier or None
    treatment_band = md.get("treatment_band") or ext.extracted_treatment_band or None

    # Phase 3 (ZEISS): power-eligibility provenance for a row with no explicit
    # range. NOT human-overridable via modified_data - the only legitimate fix
    # for "unresolved" is a real PowerRange, never a manual flip to
    # "unrestricted". Missing on every pre-Phase-3 row -> "unrestricted"
    # (existing RX-made-to-order behaviour, completely unchanged).
    power_eligibility_raw = ext.extracted_power_eligibility or "unrestricted"
    power_eligibility_enum = _coerce_enum(models.PowerEligibilityStatus, power_eligibility_raw)
    if power_eligibility_enum is None:
        errors.append(f"{tag}: invalid power_eligibility {power_eligibility_raw!r}")

    if errors:
        return {"errors": errors}

    return {
        "row": {
            "ext": ext,
            "name": name,
            "category_enum": category_enum,
            "material_enum": material_enum,
            "idx": idx,
            "design_type_enum": design_type_enum,
            "is_asph": is_asph,
            "design_variant": design_variant,
            "color_variant": color_variant,
            "design_tier": design_tier,
            "treatment_band": treatment_band,
            "power_eligibility": power_eligibility_enum,
            "market_scope": market_scope,
            "coating_ref": coating_ref,
            "availability": availability,
            "price": price,
            "power_scope": power_scope,
            "has_range": has_range,
            "sph_min": sph_min, "sph_max": sph_max,
            "cyl_min": cyl_min, "cyl_max": cyl_max,
            "add_min": add_min, "add_max": add_max,
            "total_power_min": total_power_min,
            "total_power_max": total_power_max,
            "max_cyl_abs": max_cyl_abs,
            "identity": (
                name.strip().lower(), category_enum.value,
                material_enum.value, idx,
                design_type_enum.value, is_asph,
                _norm(design_variant), _norm(color_variant),
                _norm(design_tier), _norm(treatment_band),
                coating_ref or ("none",), availability.value,
                power_scope or "", _norm(market_scope),
            ),
        }
    }


def _resolve_or_create_variant(db: Session, model, row) -> models.LensVariant:
    dv_n = _norm(row["design_variant"])
    cv_n = _norm(row["color_variant"])
    dt_n = _norm(row["design_tier"])
    tr_n = _norm(row["treatment_band"])
    existing = (
        db.query(models.LensVariant)
        .filter(
            models.LensVariant.lens_model_id == model.id,
            models.LensVariant.material == row["material_enum"],
            models.LensVariant.index_value == row["idx"],
            models.LensVariant.design_type == row["design_type_enum"],
            models.LensVariant.is_aspherical == row["is_asph"],
            func.lower(func.trim(func.coalesce(models.LensVariant.design_variant, ""))) == dv_n,
            func.lower(func.trim(func.coalesce(models.LensVariant.color_variant, ""))) == cv_n,
            func.lower(func.trim(func.coalesce(models.LensVariant.design_tier, ""))) == dt_n,
            func.lower(func.trim(func.coalesce(models.LensVariant.treatment_band, ""))) == tr_n,
        )
        .first()
    )
    if existing is not None:
        return existing
    variant = models.LensVariant(
        lens_model_id=model.id,
        material=row["material_enum"],
        index_value=row["idx"],
        design_type=row["design_type_enum"],
        is_aspherical=row["is_asph"],
        design_variant=row["design_variant"],
        color_variant=row["color_variant"],
        design_tier=row["design_tier"],
        treatment_band=row["treatment_band"],
        # legacy / NON-AUTHORITATIVE mirror; commercial availability is on VariantPricing
        availability=(
            models.LensAvailability.RX
            if row["availability"] == models.PricingAvailability.RX
            else models.LensAvailability.STOCK
        ),
        price=0.0,          # legacy column; real money lives on VariantPricing.price_pair
        currency="EGP",
    )
    db.add(variant)
    db.flush()
    return variant


def confirm_catalog_commercial(
    db: Session, catalog_id: int, reviewed_by: str = "admin", _fault_hook=None
) -> dict:
    """The ONE commercial writer.

    Validates every extraction in the catalog first (whole catalog blocked on any
    failure), then performs a single atomic transaction: close all current company
    pricing, resolve/create model+variant+coating, append new VariantPricing (+
    PowerRange only for real ranges), mark this catalog CONFIRMED and the previous
    confirmed catalog SUPERSEDED. Any failure rolls the whole thing back.
    """
    catalog = get_catalog(db, catalog_id)
    if catalog is None:
        raise CommercialValidationError([f"catalog {catalog_id}: not found"])
    if catalog.status == models.CatalogStatus.CONFIRMED:
        raise CommercialValidationError([f"catalog {catalog_id}: already CONFIRMED"])

    company_id = catalog.company_id
    considered = [
        e for e in get_extractions_by_catalog(db, catalog_id) if e.status != "rejected"
    ]

    # ---------- PHASE A: prepare the SAFE subset; park the rest -------------
    # A minority of unresolved / conflicting rows must NOT zero out the whole
    # catalog. Rows that cannot be safely written are parked with an exact
    # reason for human review; everything clean is confirmed atomically.
    #   - _prepare error            -> skipped_unresolved
    #   - same identity + same price + same power_scope + currency
    #                               -> true duplicate, collapsed (one pricing)
    #   - same identity, DIFFERENT price -> price conflict: BOTH rows parked,
    #                                  never merged / averaged / auto-picked
    if not considered:
        raise CommercialValidationError(
            [f"catalog {catalog_id}: no confirmable extractions"]
        )

    keep: dict = {}          # identity -> row (the survivor to write)
    seen_meta: dict = {}     # identity -> (ext_id, price, currency, power_scope)
    conflicted: set = set()  # identities with an unresolved price conflict
    parked: List[dict] = []  # [{"extraction_id": int, "reason": str}]

    for ext in considered:
        result = _prepare_extraction_row(ext)
        if "errors" in result:
            parked.append({"extraction_id": ext.id, "reason": "; ".join(result["errors"])})
            continue
        row = result["row"]
        ident = row["identity"]
        meta = (ext.id, row.get("price"), "EGP", row.get("power_scope") or "")
        if ident in conflicted:
            parked.append({
                "extraction_id": ext.id,
                "reason": f"price conflict for this commercial identity "
                          f"(see extraction {seen_meta[ident][0]}) - needs human review",
            })
            continue
        if ident in keep:
            p_id, p_price, p_cur, p_scope = seen_meta[ident]
            exact = (
                abs((p_price or 0.0) - (row.get("price") or 0.0)) < 0.005
                and p_cur == meta[2] and p_scope == meta[3]
            )
            if exact:
                parked.append({
                    "extraction_id": ext.id,
                    "reason": f"exact duplicate of extraction {p_id} - collapsed to one pricing",
                })
            else:
                # genuine price conflict: park BOTH, keep neither
                parked.append({
                    "extraction_id": p_id,
                    "reason": f"price conflict for this commercial identity "
                              f"(with extraction {ext.id}) - needs human review",
                })
                parked.append({
                    "extraction_id": ext.id,
                    "reason": f"price conflict for this commercial identity "
                              f"(with extraction {p_id}) - needs human review",
                })
                del keep[ident]
                conflicted.add(ident)
            continue
        keep[ident] = row
        seen_meta[ident] = meta

    prepared: List[dict] = list(keep.values())
    if not prepared:
        raise CommercialValidationError(
            [f"catalog {catalog_id}: no confirmable rows"]
            + [f"extraction {p['extraction_id']}: {p['reason']}" for p in parked]
        )

    # ---------- PHASE B: one atomic write ----------
    try:
        now = datetime.utcnow()

        # 1. close ALL current pricing for this company
        current_rows = _company_current_pricing_rows(db, company_id)
        if current_rows:
            latest = max(
                (r.effective_from for r in current_rows if r.effective_from), default=now
            )
            if now <= latest:
                now = latest + timedelta(microseconds=1)
        for r in current_rows:
            r.effective_to = now
        db.flush()

        model_cache: dict = {}
        coating_cache: dict = {}
        written: List[models.VariantPricing] = []

        for row in prepared:
            # 2a. resolve / create LensModel. Identity is (company, normalized
            # name, category): the same family name in two lens categories
            # (e.g. "Pixel" Single Vision vs "Pixel" Progressive) is two
            # distinct products and must never collapse into one LensModel.
            category_enum = row["category_enum"]
            mkey = row["name"].strip().lower()
            ckey = (mkey, category_enum)
            model = model_cache.get(ckey)
            if model is None:
                model = (
                    db.query(models.LensModel)
                    .filter(
                        models.LensModel.company_id == company_id,
                        func.lower(func.trim(models.LensModel.name)) == mkey,
                        models.LensModel.category == category_enum,
                    )
                    .first()
                )
            if model is None:
                model = models.LensModel(
                    company_id=company_id, name=row["name"], category=category_enum
                )
                db.add(model)
                db.flush()
            model_cache[ckey] = model

            # 2b. resolve / create LensVariant (full commercial identity)
            variant = _resolve_or_create_variant(db, model, row)

            # 2c. resolve / create Coating
            coating_id = None
            if row["coating_ref"] is not None:
                kind, val = row["coating_ref"]
                if kind == "id":
                    coating_id = val
                else:
                    ckey = val.strip().lower()
                    coating = coating_cache.get(ckey)
                    if coating is None:
                        coating = (
                            db.query(models.Coating)
                            .filter(func.lower(models.Coating.code) == ckey)
                            .first()
                        )
                    if coating is None:
                        coating = models.Coating(code=val, name=val)
                        db.add(coating)
                        db.flush()
                    coating_cache[ckey] = coating
                    coating_id = coating.id

            # 3. new current VariantPricing (Decimal price, verbatim)
            pricing = models.VariantPricing(
                variant_id=variant.id,
                coating_id=coating_id,
                availability=row["availability"],
                power_eligibility=row["power_eligibility"],
                price_pair=row["price"],
                currency="EGP",
                source_catalog_id=catalog.id,
                source_extraction_id=row["ext"].id,
                effective_from=now,
                effective_to=None,
                power_scope=row["power_scope"],
                market_scope=row["market_scope"],
            )
            db.add(pricing)
            db.flush()

            # 4/5/6. PowerRange ONLY for real ranges (STOCK always, RX iff limits given)
            if row["has_range"]:
                db.add(
                    models.PowerRange(
                        lens_model_id=model.id,
                        variant_id=variant.id,
                        pricing_id=pricing.id,
                        sph_min=float(row["sph_min"]) if row["sph_min"] is not None else 0.0,
                        sph_max=float(row["sph_max"]) if row["sph_max"] is not None else 0.0,
                        cyl_min=float(row["cyl_min"]) if row["cyl_min"] is not None else -10.0,
                        cyl_max=float(row["cyl_max"]) if row["cyl_max"] is not None else 0.0,
                        add_min=row["add_min"],
                        add_max=row["add_max"],
                        total_power_min=row.get("total_power_min"),
                        total_power_max=row.get("total_power_max"),
                        max_cyl_abs=row.get("max_cyl_abs"),
                    )
                )
                db.flush()

            row["ext"].reviewed_by = reviewed_by
            row["ext"].reviewed_at = now
            written.append(pricing)

        # 8. previous CONFIRMED catalog(s) -> SUPERSEDED (before we claim CONFIRMED,
        #    so the "one confirmed catalog per company" index is never violated)
        superseded = (
            db.query(models.Catalog)
            .filter(
                models.Catalog.company_id == company_id,
                models.Catalog.status == models.CatalogStatus.CONFIRMED,
                models.Catalog.id != catalog.id,
            )
            .all()
        )
        for prev in superseded:
            prev.status = models.CatalogStatus.SUPERSEDED
        db.flush()

        # 7. mark this catalog CONFIRMED
        catalog.status = models.CatalogStatus.CONFIRMED
        catalog.confirmed_at = now
        catalog.confirmed_by = reviewed_by
        db.flush()

        # 8. park the unresolved / conflicting rows: back to needs_review with an
        #    exact reason. Never fabricated, never silently dropped.
        for pk in parked:
            pe = db.get(models.CatalogExtraction, pk["extraction_id"])
            if pe is not None and pe.status != "rejected":
                pe.status = "needs_review"
                pe.review_notes = (
                    ((pe.review_notes + " | ") if pe.review_notes else "") + pk["reason"]
                )
        db.flush()

        if _fault_hook is not None:
            _fault_hook(db)

        db.commit()
    except Exception:
        db.rollback()
        raise

    _n_conflict = sum(1 for p in parked if "price conflict" in p["reason"])
    _n_truedup = sum(1 for p in parked if "exact duplicate" in p["reason"])
    return {
        "catalog_id": catalog.id,
        "status": models.CatalogStatus.CONFIRMED.value,
        "priced_rows": len(written),
        "confirmed": len(written),
        "skipped_unresolved": len(parked) - _n_conflict - _n_truedup,
        "true_duplicates_collapsed": _n_truedup,
        "conflicts": _n_conflict,
        "parked": parked,
        "closed_previous_current": len(current_rows),
        "superseded_catalogs": [c.id for c in superseded],
    }


# ===== Phase 4H: attach graphical/G3 power-range evidence to EXISTING pricing ====
def attach_range_to_existing_pricing(db: Session, extraction_id: int) -> dict:
    """Attach one CONFIRMED extraction's power-range evidence (coarse box and/or
    G3 total_power_min/total_power_max/max_cyl_abs) to an ALREADY-CURRENT
    VariantPricing row, by exact commercial identity match.

    This is deliberately NOT confirm_catalog_commercial: that function is a
    whole-company pricing writer (it closes every current price for the
    company and appends new VariantPricing rows with a required price). A
    range-only extraction has no price and must never go through it - doing
    so would supersede/close the very pricing rows this function exists to
    leave untouched. This function only ever ADDS PowerRange row(s); it never
    creates, closes, or modifies a Company/LensModel/LensVariant/Coating/
    VariantPricing. If any part of the commercial identity does not already
    exist, it parks with an exact reason instead of fabricating one.

    Coating is deliberately NOT part of the identity match here (unlike
    confirm_catalog_commercial's price identity, which requires one). A
    graphical/G3 power-range chart states its limits per index/diameter/
    treatment_band and never varies them per coating (DuraVision Gold vs
    Platinum vs Chrome, etc. all share one optical range) - LensVariant
    itself carries no coating column; only VariantPricing does. So when the
    extraction carries no coating evidence at all (coating_extraction_status
    is unset - this is graphical range evidence, not a priced commercial
    row), the same proven range is attached to EVERY currently-current
    VariantPricing row under the matching LensVariant/availability/
    market_scope, one PowerRange copy per pricing_id (PowerRange.pricing_id
    is NOT NULL, so it cannot point at a variant "for all coatings" any
    other way). This does not create new commercial identities or duplicate
    search results - those coating rows already existed as separate priced
    products; this only makes each of them correctly power-eligible. If the
    extraction DOES carry resolved coating evidence, it is honored and the
    range is attached to that one coating's pricing only.

    Generic across manufacturers/catalogs: the identity axes are the same
    ones confirm_catalog_commercial/_resolve_or_create_variant use (material,
    index, design_type, is_aspherical, design_variant, color_variant,
    design_tier, treatment_band, availability, market_scope) - no brand/
    family branching here.

    Returns {"power_range_ids": [int, ...], "created": [int, ...],
    "reused": [int, ...]} on success, or {"error": str} on failure. Never
    raises for an expected identity-mismatch, so a caller can batch many
    extractions and collect per-row outcomes.
    """
    ext = get_extraction(db, extraction_id)
    if ext is None:
        return {"error": f"extraction {extraction_id}: not found"}
    if ext.status != "confirmed":
        return {"error": f"extraction {extraction_id}: not review-approved (status={ext.status!r})"}

    catalog = get_catalog(db, ext.catalog_id)
    if catalog is None:
        return {"error": f"extraction {extraction_id}: parent catalog not found"}
    company = get_company(db, catalog.company_id)
    if company is None:
        return {
            "error": f"extraction {extraction_id}: company {catalog.company_id} is "
                     f"inactive/deleted - graphical range NOT attached"
        }

    md = ext.modified_data or {}

    name = (md.get("name") or ext.extracted_name or "").strip()
    if not name or name == models.UNRESOLVED_FAMILY_NAME:
        return {"error": f"extraction {extraction_id}: unresolved/missing product family"}

    category_enum = _coerce_enum(
        models.LensCategory, md.get("category") or ext.extracted_category,
        models.LensCategory.SINGLE_VISION,
    )
    material_enum = _coerce_enum(
        models.MaterialType, md.get("material") or ext.extracted_material or "CR39"
    )
    idx_raw = md.get("index", ext.extracted_index)
    try:
        idx = round(float(idx_raw), 2)
    except (TypeError, ValueError):
        return {"error": f"extraction {extraction_id}: invalid/missing index {idx_raw!r}"}
    design_type_enum = _coerce_enum(models.DesignType, md.get("design_type"), models.DesignType.SPHERICAL)
    is_asph = bool(md.get("is_aspherical", False))
    design_variant = md.get("design_variant") or ext.extracted_design or None
    color_variant = md.get("color_variant") or ext.extracted_color_variant or None
    design_tier = md.get("design_tier") or ext.extracted_design_tier or None
    treatment_band = md.get("treatment_band") or ext.extracted_treatment_band or None
    market_scope = md.get("market_scope") or ext.extracted_market_scope or None

    avail_raw = _norm(md.get("availability") or ext.extracted_availability)
    if avail_raw not in ("stock", "rx"):
        return {"error": f"extraction {extraction_id}: invalid availability {avail_raw!r} (STOCK/RX only)"}
    availability = (
        models.PricingAvailability.STOCK if avail_raw == "stock" else models.PricingAvailability.RX
    )

    # Coating is deliberately NOT required here (see docstring): a graphical
    # range chart never varies by coating, only by treatment_band. Only when
    # the extraction DOES carry resolved coating evidence do we narrow to
    # that one coating's pricing.
    cs = ext.coating_extraction_status
    coating_id = None
    coating_constrained = False
    if cs == models.CoatingExtractionStatus.RESOLVED:
        coating_constrained = True
        if ext.coating_id is not None:
            coating_id = int(ext.coating_id)
        elif ext.extracted_coating:
            coating = (
                db.query(models.Coating)
                .filter(func.lower(models.Coating.code) == ext.extracted_coating.strip().lower())
                .first()
            )
            if coating is None:
                return {"error": f"extraction {extraction_id}: coating {ext.extracted_coating!r} does not exist"}
            coating_id = coating.id
        else:
            return {"error": f"extraction {extraction_id}: coating RESOLVED but no coating_id / extracted_coating"}
    elif cs == models.CoatingExtractionStatus.EXPLICIT_NONE:
        coating_constrained = True  # valid: uncoated identity only, coating_id stays None
    # cs is None / NOT_FOUND -> graphical evidence with no coating axis at all;
    # coating_constrained stays False -> attach across every current coating.

    sph_min, sph_max = md.get("sph_min", ext.sph_min), md.get("sph_max", ext.sph_max)
    cyl_min, cyl_max = md.get("cyl_min", ext.cyl_min), md.get("cyl_max", ext.cyl_max)
    add_min, add_max = md.get("add_min", ext.add_min), md.get("add_max", ext.add_max)
    total_power_min = md.get("total_power_min", ext.extracted_total_power_min)
    total_power_max = md.get("total_power_max", ext.extracted_total_power_max)
    max_cyl_abs = md.get("max_cyl_abs", ext.extracted_max_cyl_abs)
    has_range = any(
        v is not None for v in (sph_min, sph_max, total_power_min, total_power_max, max_cyl_abs)
    )
    if not has_range:
        return {"error": f"extraction {extraction_id}: no range data to attach"}

    model = (
        db.query(models.LensModel)
        .filter(
            models.LensModel.company_id == catalog.company_id,
            func.lower(func.trim(models.LensModel.name)) == name.lower(),
            models.LensModel.category == category_enum,
            models.LensModel.is_active == True,
            models.LensModel.is_deleted == False,
        )
        .first()
    )
    if model is None:
        return {
            "error": f"extraction {extraction_id}: no existing ACTIVE LensModel {name!r} "
                     f"for this company/category - graphical range NOT attached "
                     f"(this function never creates commercial identity, and never "
                     f"attaches to an inactive/deleted one)"
        }

    # design_variant / color_variant / design_tier are wildcarded when the
    # extraction leaves them None: a family-level graphical chart (no tier
    # column, e.g. ClearMind's chart shared by "Individual 3" and "Superb")
    # proves the range applies regardless of that axis, so it must attach to
    # every existing variant that matches on every axis the chart DOES speak
    # to - never invented as a specific tier, never narrowed to "no tier".
    # treatment_band is never wildcarded: the chart always states a specific
    # band for every row, and bands must stay commercially distinct.
    base_filters = [
        models.LensVariant.lens_model_id == model.id,
        models.LensVariant.index_value == idx,
        models.LensVariant.design_type == design_type_enum,
        models.LensVariant.is_aspherical == is_asph,
        func.lower(func.trim(func.coalesce(models.LensVariant.treatment_band, ""))) == _norm(treatment_band),
    ]
    if design_variant is not None:
        base_filters.append(
            func.lower(func.trim(func.coalesce(models.LensVariant.design_variant, ""))) == _norm(design_variant)
        )
    if color_variant is not None:
        base_filters.append(
            func.lower(func.trim(func.coalesce(models.LensVariant.color_variant, ""))) == _norm(color_variant)
        )
    if design_tier is not None:
        base_filters.append(
            func.lower(func.trim(func.coalesce(models.LensVariant.design_tier, ""))) == _norm(design_tier)
        )

    variants = db.query(models.LensVariant).filter(
        *base_filters, models.LensVariant.material == material_enum
    ).all()
    material_relaxed = False
    if not variants:
        # Fallback: material is dropped from the filter, index_value alone
        # already uniquely identifies the optical index within one LensModel
        # (ZEISS never sells two different materials at the same index under
        # one family) - a stored material that doesn't match the material a
        # graphical-chart index implies (e.g. a commercial extraction that
        # left every row at a generic default material instead of resolving
        # it per index) is a known, one-sided upstream data gap, not a real
        # commercial distinction, so it must never block an otherwise exact,
        # unique identity match. If this fallback ever matches MULTIPLE
        # distinct materials at the same index (a genuine ambiguity), it is
        # surfaced as an error below, never silently guessed.
        variants = db.query(models.LensVariant).filter(*base_filters).all()
        if variants:
            material_relaxed = True
            distinct_materials = {v.material for v in variants}
            if len(distinct_materials) > 1:
                return {
                    "error": f"extraction {extraction_id}: ambiguous - {len(distinct_materials)} "
                             f"different materials exist at this exact index/treatment_band "
                             f"identity ({sorted(m.value for m in distinct_materials)}) and none "
                             f"matches the expected {material_enum.value!r} - graphical range "
                             f"NOT attached (never guessed)"
                }
    if not variants:
        return {
            "error": f"extraction {extraction_id}: no existing LensVariant for this "
                     f"commercial identity - graphical range NOT attached"
        }

    pricing_rows: List[models.VariantPricing] = []
    for variant in variants:
        pricing_query = db.query(models.VariantPricing).filter(
            models.VariantPricing.variant_id == variant.id,
            models.VariantPricing.availability == availability,
            models.VariantPricing.effective_to.is_(None),
            models.VariantPricing.market_scope == market_scope
            if market_scope is not None
            else models.VariantPricing.market_scope.is_(None),
        )
        if coating_constrained:
            pricing_query = pricing_query.filter(
                models.VariantPricing.coating_id == coating_id
                if coating_id is not None
                else models.VariantPricing.coating_id.is_(None)
            )
        pricing_rows.extend(pricing_query.all())
    if not pricing_rows:
        return {
            "error": f"extraction {extraction_id}: no existing CURRENT VariantPricing for "
                     f"this identity - graphical range NOT attached (price truth is never "
                     f"created or altered by this function)"
        }

    norm_sph_min = float(sph_min) if sph_min is not None else 0.0
    norm_sph_max = float(sph_max) if sph_max is not None else 0.0
    norm_cyl_min = float(cyl_min) if cyl_min is not None else -10.0
    norm_cyl_max = float(cyl_max) if cyl_max is not None else 0.0

    created_ids: List[int] = []
    reused_ids: List[int] = []
    try:
        for pricing in pricing_rows:
            # idempotent: an identical range under the same pricing is a no-op,
            # not a duplicate PowerRange row (guards re-running on the same
            # extraction, or attaching the same evidence to the same coating
            # twice from two different rows).
            dup = (
                db.query(models.PowerRange)
                .filter(
                    models.PowerRange.pricing_id == pricing.id,
                    models.PowerRange.sph_min == norm_sph_min,
                    models.PowerRange.sph_max == norm_sph_max,
                    models.PowerRange.cyl_min == norm_cyl_min,
                    models.PowerRange.cyl_max == norm_cyl_max,
                    models.PowerRange.total_power_min == total_power_min,
                    models.PowerRange.total_power_max == total_power_max,
                    models.PowerRange.max_cyl_abs == max_cyl_abs,
                )
                .first()
            )
            if dup is not None:
                reused_ids.append(dup.id)
                continue
            pr = models.PowerRange(
                lens_model_id=model.id,
                variant_id=pricing.variant_id,
                pricing_id=pricing.id,
                sph_min=norm_sph_min, sph_max=norm_sph_max,
                cyl_min=norm_cyl_min, cyl_max=norm_cyl_max,
                add_min=add_min, add_max=add_max,
                total_power_min=total_power_min, total_power_max=total_power_max,
                max_cyl_abs=max_cyl_abs,
                notes=ext.review_notes,
            )
            db.add(pr)
            db.flush()
            created_ids.append(pr.id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "power_range_ids": created_ids + reused_ids, "created": created_ids,
        "reused": reused_ids, "material_relaxed": material_relaxed,
    }
