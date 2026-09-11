"""
روتر الوصفات الطبية النهائي - مع Transposition
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app import crud, schemas
from app import product_search as product_search_service
from app.ocr_service import ocr_service
from app.lens_matcher import TranspositionEngine, OpticsRecommender
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


@router.post("/{prescription_id}/match", response_model=schemas.ProductSearchResponse,
            deprecated=True)
def match_lenses(
    prescription_id: int,
    filters: Optional[schemas.LensFilters] = None,
    prefer_stock: bool = True,
    prefer_aspherical: bool = True,
    db: Session = Depends(get_db)
):
    """DEPRECATED - compatibility alias for POST /prescriptions/{id}/search.

    There must be exactly ONE prescription-eligibility decision path. This
    endpoint used to call the frozen lens_matcher.match_lenses() directly,
    which has no concept of VariantPricing.power_eligibility and could report
    a row whose real power limits are not yet modeled (power_eligibility =
    UNRESOLVED - e.g. a ZEISS catalog price with an unmodeled graphical/
    footnote range) as a proven compatible RX lens for ANY prescription.

    Audited callers: the dashboard never calls this route (Prescriptions.js
    uses prescriptionAPI.search / POST .../search exclusively) and no test
    exercises it at the HTTP layer - only lens_matcher.match_lenses() itself
    is unit-tested directly, which is untouched. There is therefore no live
    caller depending on the old MatchResponse shape, so this is a clean
    deprecation: it now delegates to the SAME tri-state-safe
    product_search.search() as /search and returns its ProductSearchResponse
    - targeted mode (honouring `filters`, exactly like the old endpoint always
    applied a supplied filter set) when `filters` is given, automatic mode
    otherwise. The frozen matcher is never called from here again."""
    prescription = crud.get_prescription(db, prescription_id)
    if not prescription:
        raise HTTPException(status_code=404, detail="الوصفة غير موجودة")

    req = schemas.ProductSearchRequest(
        mode="targeted" if filters is not None else "automatic",
        filters=filters,
        prefer_stock=prefer_stock,
        prefer_aspherical=prefer_aspherical,
    )
    return product_search_service.search(db, prescription, req)


@router.post("/{prescription_id}/search", response_model=schemas.ProductSearchResponse)
def product_search(
    prescription_id: int,
    req: Optional[schemas.ProductSearchRequest] = None,
    db: Session = Depends(get_db),
):
    """V1.0.1 fast product search.

    mode="automatic": every lens optically valid for the prescription.
    mode="targeted":  that result, then `filters` applied as strict AND (never
    silently relaxed). Results come back grouped and ordered availability-first
    (STOCK Egypt -> STOCK Out Of Egypt -> RX), with a direct availability answer
    and - only when a targeted search has zero exact results - a SEPARATE
    alternatives list (never mixed with or labelled as exact matches). The
    optical matcher and its score are unchanged.
    """
    prescription = crud.get_prescription(db, prescription_id)
    if not prescription:
        raise HTTPException(status_code=404, detail="الوصفة غير موجودة")
    req = req or schemas.ProductSearchRequest()
    return product_search_service.search(db, prescription, req)


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
