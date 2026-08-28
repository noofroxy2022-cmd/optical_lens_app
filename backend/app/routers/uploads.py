"""
روتر رفع الملفات
"""
from fastapi import APIRouter, UploadFile, File
import shutil
import os
from datetime import datetime

router = APIRouter(prefix="/uploads", tags=["الملفات"])

UPLOAD_DIR = "uploads/temp"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/image")
async def upload_image(file: UploadFile = File(...)):
    """رفع صورة مؤقتة"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = f"{UPLOAD_DIR}/{timestamp}_{file.filename}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"filename": file.filename, "path": file_path}
