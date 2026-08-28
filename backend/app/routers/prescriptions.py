"""
روتر الوصفات الطبية النهائي - مع Transposition
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app import crud, schemas
from app.ocr_service import ocr_service
from app.lens_matcher import lens_matcher, TranspositionEngine, OpticsRecommender
import os
import shutil
from datetime import datetime

router = APIRouter(prefix="/prescriptions", tags=["الوصفات الطبية"])

UPLOAD_DIR = "uploads/prescriptions"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/", response_model=schemas.PrescriptionResponse)
def create_prescription(prescription: schemas.PrescriptionCreate, db: Session = Depends(get_db)):
    """إنشاء وصفة مع Transposition تلقائي"""
    return crud.create_prescription(db, prescription)


@router.post("/upload", response_model=schemas.OCRResponse)
async def upload_prescription_image(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """رفع صورة + OCR + Transposition"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = f"{UPLOAD_DIR}/{timestamp}_{file.filename}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    ocr_result = ocr_service.process_image(file_path)

    if ocr_result.success and ocr_result.prescription:
        db_prescription = crud.create_prescription(
            db, ocr_result.prescription,
            image_path=file_path,
            ocr_confidence=ocr_result.confidence
        )

        return schemas.OCRResponse(
            success=True,
            prescription=schemas.PrescriptionResponse.model_validate(db_prescription),
            confidence=ocr_result.confidence,
            raw_text=ocr_result.raw_text,
            message=f"تم الاستخراج + Transposition. CYL موجب: {db_prescription.transposition_applied}"
        )

    return ocr_result


@router.get("/", response_model=List[schemas.PrescriptionResponse])
def list_prescriptions(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """قائمة الوصفات"""
    return crud.get_prescriptions(db, skip=skip, limit=limit)


@router.get("/{prescription_id}", response_model=schemas.PrescriptionResponse)
def get_prescription(prescription_id: int, db: Session = Depends(get_db)):
    """جلب وصفة"""
    prescription = crud.get_prescription(db, prescription_id)
    if not prescription:
        raise HTTPException(status_code=404, detail="الوصفة غير موجودة")
    return prescription


@router.post("/{prescription_id}/match", response_model=schemas.MatchResponse)
def match_lenses(
    prescription_id: int,
    filters: Optional[schemas.LensFilters] = None,
    prefer_stock: bool = True,
    prefer_aspherical: bool = True,
    db: Session = Depends(get_db)
):
    """مطابقة الوصفة مع العدسات - مع جميع التوصيات"""
    prescription = crud.get_prescription(db, prescription_id)
    if not prescription:
        raise HTTPException(status_code=404, detail="الوصفة غير موجودة")

    results, stock_count, rx_count, index_rec, aspherical_rec = lens_matcher.match_lenses(
        db, prescription, filters, prefer_stock, prefer_aspherical
    )

    return schemas.MatchResponse(
        prescription=schemas.PrescriptionResponse.model_validate(prescription),
        results=results,
        total_matches=len(results),
        stock_count=stock_count,
        rx_count=rx_count,
        transposition_applied=prescription.transposition_applied,
        index_recommendation=index_rec,
        aspherical_recommendation=aspherical_rec
    )


@router.get("/{prescription_id}/recommendations")
def get_recommendations(prescription_id: int, db: Session = Depends(get_db)):
    """الحصول على التوصيات البصرية فقط"""
    prescription = crud.get_prescription(db, prescription_id)
    if not prescription:
        raise HTTPException(status_code=404, detail="الوصفة غير موجودة")

    max_sph = max(abs(prescription.od_sph), abs(prescription.os_sph))
    max_cyl = max(abs(prescription.od_cyl or 0), abs(prescription.os_cyl or 0))
    max_add = max(prescription.od_add or 0, prescription.os_add or 0)

    recommender = OpticsRecommender()

    index_val, index_desc = recommender.recommend_index(max_sph)
    need_aspherical, aspherical_desc = recommender.recommend_aspherical(max_sph, max_cyl)
    category, category_desc = recommender.recommend_category(max_add)

    return {
        "prescription_id": prescription_id,
        "transposition_applied": prescription.transposition_applied,
        "index_recommendation": {
            "value": index_val,
            "description": index_desc
        },
        "aspherical_recommendation": {
            "needed": need_aspherical,
            "description": aspherical_desc
        },
        "category_recommendation": {
            "value": category,
            "description": category_desc
        },
        "warnings": []
    }


@router.delete("/{prescription_id}")
def delete_prescription(prescription_id: int, db: Session = Depends(get_db)):
    """حذف وصفة"""
    if crud.delete_prescription(db, prescription_id):
        return {"message": "تم الحذف بنجاح"}
    raise HTTPException(status_code=404, detail="الوصفة غير موجودة")
