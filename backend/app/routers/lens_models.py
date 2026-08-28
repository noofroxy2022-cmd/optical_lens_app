"""
روتر نماذج العدسات ومتغيراتها ونطاقات القوة
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app import crud, schemas

router = APIRouter(prefix="/lens-models", tags=["نماذج العدسات"])


@router.post("/", response_model=schemas.LensModelResponse)
def create_lens_model(model: schemas.LensModelCreate, db: Session = Depends(get_db)):
    """إضافة نموذج عدسة جديد"""
    company = crud.get_company(db, model.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="الشركة غير موجودة")
    return crud.create_lens_model(db, model)


@router.get("/", response_model=List[schemas.LensModelResponse])
def list_lens_models(
    skip: int = 0,
    limit: int = 100,
    company_id: Optional[int] = None,
    category: Optional[str] = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db)
):
    """قائمة نماذج العدسات"""
    return crud.get_lens_models(db, skip=skip, limit=limit, 
                                company_id=company_id, category=category,
                                include_inactive=include_inactive)


@router.get("/{model_id}", response_model=schemas.LensModelResponse)
def get_lens_model(model_id: int, db: Session = Depends(get_db)):
    """جلب نموذج محدد"""
    model = crud.get_lens_model(db, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="النموذج غير موجود")
    return model


@router.put("/{model_id}", response_model=schemas.LensModelResponse)
def update_lens_model(model_id: int, update: schemas.LensModelUpdate, db: Session = Depends(get_db)):
    """تحديث نموذج"""
    model = crud.update_lens_model(db, model_id, update)
    if not model:
        raise HTTPException(status_code=404, detail="النموذج غير موجود")
    return model


@router.post("/{model_id}/toggle-active", response_model=schemas.LensModelResponse)
def toggle_lens_model_active(model_id: int, db: Session = Depends(get_db)):
    """تفعيل/تعطيل نموذج"""
    model = crud.toggle_lens_model_active(db, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="النموذج غير موجود")
    return model


@router.delete("/{model_id}")
def delete_lens_model(model_id: int, db: Session = Depends(get_db)):
    """حذف نموذج"""
    if crud.delete_lens_model(db, model_id):
        return {"message": "تم الحذف بنجاح"}
    raise HTTPException(status_code=404, detail="النموذج غير موجود")


# ===== Variants =====
@router.post("/{model_id}/variants", response_model=schemas.LensVariantResponse)
def create_variant(model_id: int, variant: schemas.LensVariantCreate, db: Session = Depends(get_db)):
    """إضافة متغير لنموذج"""
    model = crud.get_lens_model(db, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="النموذج غير موجود")

    variant_data = variant.model_dump()
    variant_data["lens_model_id"] = model_id
    return crud.create_lens_variant(db, schemas.LensVariantCreate(**variant_data))


@router.get("/{model_id}/variants", response_model=List[schemas.LensVariantResponse])
def list_variants(model_id: int, db: Session = Depends(get_db)):
    """قائمة متغيرات النموذج"""
    return crud.get_variants_by_model(db, model_id)


# ===== Power Ranges =====
@router.post("/{model_id}/power-ranges", response_model=schemas.PowerRangeResponse)
def create_power_range(model_id: int, power_range: schemas.PowerRangeCreate, db: Session = Depends(get_db)):
    """إضافة نطاق قوة"""
    model = crud.get_lens_model(db, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="النموذج غير موجود")

    range_data = power_range.model_dump()
    range_data["lens_model_id"] = model_id
    return crud.create_power_range(db, schemas.PowerRangeCreate(**range_data))


@router.get("/{model_id}/power-ranges", response_model=List[schemas.PowerRangeResponse])
def list_power_ranges(model_id: int, db: Session = Depends(get_db)):
    """قائمة نطاقات القوة"""
    return crud.get_power_ranges_by_model(db, model_id)
