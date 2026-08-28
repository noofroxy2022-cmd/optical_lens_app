"""
CRUD النهائي - يدعم Preview & Confirm + Transposition
"""
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_
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
