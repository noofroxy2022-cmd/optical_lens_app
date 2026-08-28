"""
روتر العدسات
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app import crud, schemas

router = APIRouter(prefix="/lenses", tags=["العدسات"])


@router.post("/", response_model=schemas.LensResponse)
def create_lens(
    lens: schemas.LensCreate,
    db: Session = Depends(get_db)
):
    """إضافة عدسة جديدة"""
    # التحقق من وجود الشركة
    company = crud.get_company(db, lens.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="الشركة غير موجودة")

    return crud.create_lens(db, lens)


@router.get("/", response_model=List[schemas.LensResponse])
def list_lenses(
    skip: int = 0,
    limit: int = 100,
    filters: schemas.LensFilters = None,
    db: Session = Depends(get_db)
):
    """قائمة العدسات مع إمكانية التصفية"""
    return crud.get_lenses(db, skip=skip, limit=limit, filters=filters)


@router.get("/{lens_id}", response_model=schemas.LensResponse)
def get_lens(
    lens_id: int,
    db: Session = Depends(get_db)
):
    """جلب عدسة محددة"""
    lens = crud.get_lens(db, lens_id)
    if not lens:
        raise HTTPException(status_code=404, detail="العدسة غير موجودة")
    return lens


@router.delete("/{lens_id}")
def delete_lens(
    lens_id: int,
    db: Session = Depends(get_db)
):
    """حذف عدسة"""
    if crud.delete_lens(db, lens_id):
        return {"message": "تم الحذف بنجاح"}
    raise HTTPException(status_code=404, detail="العدسة غير موجودة")
