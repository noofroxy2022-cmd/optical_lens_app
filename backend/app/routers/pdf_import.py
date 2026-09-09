"""
روتر استيراد PDF النهائي - مع Preview & Confirm
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database import get_db
from app import crud, schemas, models
from app.pdf_hybrid_parser import PDFHybridParser, preview_pdf_file
import os
import shutil
from datetime import datetime

router = APIRouter(prefix="/pdf-import", tags=["استيراد PDF"])

CATALOGS_DIR = "uploads/catalogs"
os.makedirs(CATALOGS_DIR, exist_ok=True)


@router.post("/upload")
async def upload_catalog(
    company_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """رفع كتالوج PDF"""
    company = crud.get_company(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="الشركة غير موجودة")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = file.filename.split(".")[-1]
    file_path = f"{CATALOGS_DIR}/company_{company_id}_{timestamp}.{ext}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file_size = os.path.getsize(file_path)

    catalog = crud.create_catalog(
        db, company_id=company_id,
        filename=file.filename,
        file_path=file_path,
        file_size=file_size
    )

    return {
        "catalog_id": catalog.id,
        "filename": file.filename,
        "file_path": file_path,
        "status": "uploaded",
        "message": "تم رفع الكتالوج. استخدم /preview أو /extract لتحليله."
    }


@router.post("/preview/{catalog_id}")
def preview_catalog(catalog_id: int, db: Session = Depends(get_db)):
    """معاينة البيانات المستخرجة من PDF (بدون حفظ في DB)"""
    catalog = crud.get_catalog(db, catalog_id)
    if not catalog:
        raise HTTPException(status_code=404, detail="الكتالوج غير موجود")

    if not os.path.exists(catalog.file_path):
        raise HTTPException(status_code=404, detail="ملف PDF غير موجود")

    try:
        result = preview_pdf_file(catalog.file_path, use_vision=True)

        # تحديث حالة الكتالوج
        crud.update_catalog_status(db, catalog_id, "preview_ready")

        return result

    except Exception as e:
        crud.update_catalog_status(db, catalog_id, "failed", errors=str(e))
        raise HTTPException(status_code=500, detail=f"فشل المعاينة: {str(e)}")


@router.post("/extract/{catalog_id}")
def extract_catalog(
    catalog_id: int,
    req: Optional[schemas.ExtractRequest] = None,
    db: Session = Depends(get_db)
):
    """استخراج البيانات وحفظها في CatalogExtraction للمعاينة.

    Optional JSON body (schemas.ExtractRequest) carries the per-catalog import
    policy: dual_price_semantics (only 'left_wholesale_right_retail' accepted;
    any other non-null value -> 422), use_vision, save_to_preview. No body ->
    generic parse, no dual-price policy.
    """
    req = req or schemas.ExtractRequest()
    catalog = crud.get_catalog(db, catalog_id)
    if not catalog:
        raise HTTPException(status_code=404, detail="الكتالوج غير موجود")

    if not os.path.exists(catalog.file_path):
        raise HTTPException(status_code=404, detail="ملف PDF غير موجود")

    dps = req.dual_price_semantics
    if dps is not None and dps != PDFHybridParser.DUAL_PRICE_LEFT_WHOLESALE_RIGHT_RETAIL:
        raise HTTPException(
            status_code=422,
            detail=(
                f"unsupported dual_price_semantics {dps!r}; the only accepted "
                f"value is '{PDFHybridParser.DUAL_PRICE_LEFT_WHOLESALE_RIGHT_RETAIL}' "
                f"(or omit it)"
            ),
        )

    try:
        parser = PDFHybridParser(use_vision=req.use_vision, dual_price_semantics=dps)
        extracted = parser.parse_pdf(catalog.file_path)

        if req.save_to_preview:
            parser.save_extractions_to_db(catalog_id, db)

        crud.update_catalog_status(db, catalog_id, "extracted")

        return {
            "catalog_id": catalog_id,
            "extracted_models": len(extracted),
            "total_power_ranges": sum(len(m.power_ranges) for m in extracted),
            "status": "extracted",
            "message": f"تم استخراج {len(extracted)} نموذج. استخدم /extractions للمعاينة."
        }

    except Exception as e:
        crud.update_catalog_status(db, catalog_id, "failed", errors=str(e))
        raise HTTPException(status_code=500, detail=f"فشل الاستخراج: {str(e)}")


@router.get("/extractions/{catalog_id}", response_model=List[schemas.CatalogExtractionResponse])
def get_extractions(
    catalog_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """جلب البيانات المستخرجة للمعاينة"""
    return crud.get_extractions_by_catalog(db, catalog_id, status=status)


@router.put("/extractions/{extraction_id}", response_model=schemas.CatalogExtractionResponse)
def update_extraction(
    extraction_id: int,
    update: schemas.CatalogExtractionUpdate,
    db: Session = Depends(get_db)
):
    """تعديل بيانات مستخرجة قبل التأكيد"""
    extraction = crud.update_extraction(db, extraction_id, update)
    if not extraction:
        raise HTTPException(status_code=404, detail="البيانات غير موجودة")
    return extraction


@router.post("/extractions/{extraction_id}/confirm")
def confirm_extraction(
    extraction_id: int,
    reviewed_by: str = "admin",
    db: Session = Depends(get_db)
):
    """Row-level QA / review approval ONLY.

    Marks the extraction review-approved. It does NOT write any commercial
    pricing - the only commercial writer is POST /pdf-import/bulk-confirm/{catalog_id}.
    A `not_found` (or still-unset) coating blocks approval; `explicit_none` is fine.
    """
    extraction = crud.get_extraction(db, extraction_id)
    if not extraction:
        raise HTTPException(status_code=404, detail="البيانات غير موجودة")

    if extraction.status == "confirmed":
        raise HTTPException(status_code=400, detail="البيانات مؤكدة مسبقاً")

    coating_status = extraction.coating_extraction_status
    if coating_status is None or coating_status == models.CoatingExtractionStatus.NOT_FOUND:
        raise HTTPException(
            status_code=422,
            detail="Coating unresolved (not_found). Resolve the coating or mark it "
                   "explicit_none before approving this row.",
        )

    crud.confirm_extraction(db, extraction_id, reviewed_by)
    return {
        "success": True,
        "message": "Extraction review approved (no commercial pricing written).",
        "extraction_id": extraction_id,
        "status": "confirmed",
    }


@router.post("/extractions/{extraction_id}/reject")
def reject_extraction(
    extraction_id: int,
    notes: str = "",
    db: Session = Depends(get_db)
):
    """رفض بيانات مستخرجة"""
    extraction = crud.reject_extraction(db, extraction_id, notes)
    if not extraction:
        raise HTTPException(status_code=404, detail="البيانات غير موجودة")
    return {"success": True, "message": "تم الرفض"}


@router.post("/bulk-confirm/{catalog_id}", response_model=schemas.BulkConfirmResult)
def bulk_confirm(
    catalog_id: int,
    reviewed_by: str = "admin",
    db: Session = Depends(get_db)
):
    """The ONLY commercial writer.

    Confirms the SAFE subset of the catalog atomically and PARKS the rest
    (unresolved rows / true-duplicate collapses / price conflicts) back to
    needs_review with an exact reason - a minority of bad rows never zeros out
    the good ones. Response carries confirmed / skipped_unresolved /
    true_duplicates_collapsed / conflicts / parked[]. Only when ZERO rows are
    confirmable is the request rejected 422. Any write fault rolls back fully.
    """
    try:
        result = crud.confirm_catalog_commercial(db, catalog_id, reviewed_by)
    except crud.CommercialValidationError as ve:
        raise HTTPException(
            status_code=422,
            detail={"message": "Catalog confirmation blocked", "errors": ve.errors},
        )
    except HTTPException:
        raise
    except Exception as e:  # confirm_catalog_commercial has already rolled back
        raise HTTPException(
            status_code=500, detail=f"Confirmation failed and was rolled back: {e}"
        )
    return {"success": True, **result}


@router.post("/bulk-upload", deprecated=True)
def bulk_upload_power_ranges(
    data: schemas.BulkUploadRequest,
    db: Session = Depends(get_db)
):
    """DISABLED in Phase 2.

    This path wrote LensModel / LensVariant / PowerRange directly and never went
    through VariantPricing, so it could bypass append-only pricing history and the
    one-confirmed-catalog rule. Commercial pricing is now written only via
    POST /pdf-import/bulk-confirm/{catalog_id}.
    """
    raise HTTPException(
        status_code=410,
        detail="Endpoint disabled. Commercial pricing is written only via "
               "POST /pdf-import/bulk-confirm/{catalog_id}.",
    )
