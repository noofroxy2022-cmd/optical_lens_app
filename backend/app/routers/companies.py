"""
روتر الشركات V2 - إدارة ديناميكية كاملة
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app import crud, schemas
import os
import shutil
from datetime import datetime

router = APIRouter(prefix="/companies", tags=["الشركات"])

UPLOAD_DIR = "uploads/companies"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/", response_model=schemas.CompanyResponse)
def create_company(company: schemas.CompanyCreate, db: Session = Depends(get_db)):
    """إضافة شركة جديدة"""
    return crud.create_company(db, company)


@router.get("/", response_model=List[schemas.CompanyResponse])
def list_companies(
    skip: int = 0,
    limit: int = 100,
    include_inactive: bool = False,
    db: Session = Depends(get_db)
):
    """قائمة الشركات - مع إمكانية إظهار غير النشطة"""
    companies = crud.get_companies(db, skip=skip, limit=limit, include_inactive=include_inactive)

    # إضافة عدادات
    result = []
    for company in companies:
        data = schemas.CompanyResponse.model_validate(company)
        data.lens_models_count = len([m for m in company.lens_models if not m.is_deleted])
        data.catalogs_count = len(company.catalogs)
        result.append(data)

    return result


@router.get("/{company_id}", response_model=schemas.CompanyResponse)
def get_company(company_id: int, db: Session = Depends(get_db)):
    """جلب شركة محددة"""
    company = crud.get_company(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="الشركة غير موجودة")
    return company


@router.put("/{company_id}", response_model=schemas.CompanyResponse)
def update_company(company_id: int, update: schemas.CompanyUpdate, db: Session = Depends(get_db)):
    """تحديث بيانات شركة"""
    company = crud.update_company(db, company_id, update)
    if not company:
        raise HTTPException(status_code=404, detail="الشركة غير موجودة")
    return company


@router.post("/{company_id}/toggle-active", response_model=schemas.CompanyResponse)
def toggle_company_active(company_id: int, db: Session = Depends(get_db)):
    """تفعيل/تعطيل شركة"""
    company = crud.toggle_company_active(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="الشركة غير موجودة")
    status = "مفعلة" if company.is_active else "معطلة"
    return company


@router.delete("/{company_id}")
def delete_company(
    company_id: int,
    hard_delete: bool = False,
    db: Session = Depends(get_db)
):
    """حذف شركة (soft أو hard)"""
    if crud.delete_company(db, company_id, soft_delete=not hard_delete):
        mode = "نهائي" if hard_delete else "soft"
        return {"message": f"تم الحذف ({mode}) بنجاح"}
    raise HTTPException(status_code=404, detail="الشركة غير موجودة")


@router.post("/{company_id}/upload-logo")
async def upload_logo(
    company_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """رفع شعار الشركة"""
    company = crud.get_company(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="الشركة غير موجودة")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = file.filename.split(".")[-1]
    file_path = f"{UPLOAD_DIR}/{company_id}_{timestamp}.{ext}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    company.logo_url = file_path
    db.commit()

    return {"logo_url": file_path}
