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
    save_to_preview: bool = True,
    db: Session = Depends(get_db)
):
    """استخراج البيانات وحفظها في CatalogExtraction للمعاينة"""
    catalog = crud.get_catalog(db, catalog_id)
    if not catalog:
        raise HTTPException(status_code=404, detail="الكتالوج غير موجود")

    if not os.path.exists(catalog.file_path):
        raise HTTPException(status_code=404, detail="ملف PDF غير موجود")

    try:
        parser = PDFHybridParser(use_vision=True)
        extracted = parser.parse_pdf(catalog.file_path)

        if save_to_preview:
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
    """تأكيد بيانات مستخرجة ونقلها إلى قاعدة البيانات الرئيسية"""
    extraction = crud.get_extraction(db, extraction_id)
    if not extraction:
        raise HTTPException(status_code=404, detail="البيانات غير موجودة")

    if extraction.status == "confirmed":
        raise HTTPException(status_code=400, detail="البيانات مؤكدة مسبقاً")

    # تحديث الحالة
    crud.confirm_extraction(db, extraction_id, reviewed_by)

    # نقل إلى قاعدة البيانات الرئيسية
    try:
        # البحث أو إنشاء LensModel
        model = db.query(models.LensModel).filter(
            models.LensModel.company_id == extraction.catalog.company_id,
            models.LensModel.name == extraction.extracted_name
        ).first()

        if not model:
            model = crud.create_lens_model(db, schemas.LensModelCreate(
                company_id=extraction.catalog.company_id,
                name=extraction.extracted_name,
                category=extraction.extracted_category or "single_vision"
            ))

        # البحث أو إنشاء Variant
        variant = db.query(models.LensVariant).filter(
            models.LensVariant.lens_model_id == model.id,
            models.LensVariant.index_value == extraction.extracted_index
        ).first()

        if not variant:
            variant = crud.create_lens_variant(db, schemas.LensVariantCreate(
                lens_model_id=model.id,
                material=extraction.extracted_material or "CR39",
                index_value=extraction.extracted_index or 1.50,
                availability=extraction.extracted_availability or "stock",
                price=extraction.extracted_price or 0
            ))

        # إنشاء PowerRange
        crud.create_power_range(db, schemas.PowerRangeCreate(
            lens_model_id=model.id,
            variant_id=variant.id,
            sph_min=extraction.sph_min or -10.0,
            sph_max=extraction.sph_max or 10.0,
            cyl_min=extraction.cyl_min or -10.0,
            cyl_max=extraction.cyl_max or 0.0,
            add_min=extraction.add_min,
            add_max=extraction.add_max
        ))

        return {
            "success": True,
            "message": "تم التأكيد ونقل البيانات إلى قاعدة البيانات",
            "lens_model_id": model.id,
            "variant_id": variant.id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"فشل النقل: {str(e)}")


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


@router.post("/bulk-confirm/{catalog_id}")
def bulk_confirm(
    catalog_id: int,
    reviewed_by: str = "admin",
    db: Session = Depends(get_db)
):
    """تأكيد جميع البيانات المستخرجة من كتالوج"""
    extractions = crud.get_extractions_by_catalog(db, catalog_id, status="pending")

    confirmed = 0
    errors = []

    for ext in extractions:
        try:
            # نفس منطق confirm_extraction
            model = db.query(models.LensModel).filter(
                models.LensModel.company_id == ext.catalog.company_id,
                models.LensModel.name == ext.extracted_name
            ).first()

            if not model:
                model = crud.create_lens_model(db, schemas.LensModelCreate(
                    company_id=ext.catalog.company_id,
                    name=ext.extracted_name,
                    category=ext.extracted_category or "single_vision"
                ))

            variant = db.query(models.LensVariant).filter(
                models.LensVariant.lens_model_id == model.id,
                models.LensVariant.index_value == ext.extracted_index
            ).first()

            if not variant:
                variant = crud.create_lens_variant(db, schemas.LensVariantCreate(
                    lens_model_id=model.id,
                    material=ext.extracted_material or "CR39",
                    index_value=ext.extracted_index or 1.50,
                    availability=ext.extracted_availability or "stock",
                    price=ext.extracted_price or 0
                ))

            crud.create_power_range(db, schemas.PowerRangeCreate(
                lens_model_id=model.id,
                variant_id=variant.id,
                sph_min=ext.sph_min or -10.0,
                sph_max=ext.sph_max or 10.0,
                cyl_min=ext.cyl_min or -10.0,
                cyl_max=ext.cyl_max or 0.0,
                add_min=ext.add_min,
                add_max=ext.add_max
            ))

            crud.confirm_extraction(db, ext.id, reviewed_by)
            confirmed += 1

        except Exception as e:
            errors.append(f"Error with extraction {ext.id}: {str(e)}")

    return {
        "success": True,
        "confirmed": confirmed,
        "total": len(extractions),
        "errors": errors,
        "message": f"تم تأكيد {confirmed} من {len(extractions)} بنجاح"
    }


@router.post("/bulk-upload")
def bulk_upload_power_ranges(
    data: schemas.BulkUploadRequest,
    db: Session = Depends(get_db)
):
    """رفع نطاقات قوة مجمعة"""
    company = crud.get_company(db, data.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="الشركة غير موجودة")

    imported = 0
    errors = []

    for item in data.ranges:
        try:
            model = db.query(models.LensModel).filter(
                models.LensModel.company_id == data.company_id,
                models.LensModel.name == item.lens_model_name
            ).first()

            if not model:
                model = crud.create_lens_model(db, schemas.LensModelCreate(
                    company_id=data.company_id,
                    name=item.lens_model_name,
                    category="single_vision"
                ))

            variant = db.query(models.LensVariant).filter(
                models.LensVariant.lens_model_id == model.id,
                models.LensVariant.index_value == item.variant_index
            ).first()

            if not variant:
                variant = crud.create_lens_variant(db, schemas.LensVariantCreate(
                    lens_model_id=model.id,
                    material=item.variant_material,
                    index_value=item.variant_index,
                    availability=item.availability,
                    design_type=item.design_type,
                    is_aspherical=item.is_aspherical,
                    price=item.price
                ))

            crud.create_power_range(db, schemas.PowerRangeCreate(
                lens_model_id=model.id,
                variant_id=variant.id,
                sph_min=item.sph_min,
                sph_max=item.sph_max,
                cyl_min=item.cyl_min,
                cyl_max=item.cyl_max,
                add_min=item.add_min,
                add_max=item.add_max
            ))

            imported += 1

        except Exception as e:
            errors.append(f"Error: {str(e)}")

    return {
        "success": True,
        "imported": imported,
        "errors": errors,
        "message": f"تم استيراد {imported} نطاق قوة"
    }
