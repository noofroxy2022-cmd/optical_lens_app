"""
OCR باستخدام Google Vision API - دقة أعلى للوصفات الطبية
"""
import os
import re
import cv2
import numpy as np
from PIL import Image
from typing import Optional, Dict, Any, List
from google.cloud import vision
from google.oauth2 import service_account
from app.schemas import PrescriptionBase, EyePrescription, OCRResponse


class GoogleVisionOCR:
    """مستخرج الوصفات باستخدام Google Vision API"""

    PATTERNS = {
        "sph": re.compile(r"SPH[\s:]*([+-]?\d+\.?\d*)", re.IGNORECASE),
        "cyl": re.compile(r"CYL[\s:]*([+-]?\d+\.?\d*)", re.IGNORECASE),
        "axis": re.compile(r"AXIS[\s:]*(\d{1,3})", re.IGNORECASE),
        "add": re.compile(r"ADD[\s:]*([+-]?\d+\.?\d*)", re.IGNORECASE),
        "pd": re.compile(r"PD[\s:]*(\d{2,3}\.?\d*)", re.IGNORECASE),
        "od": re.compile(r"\b(OD|R\.?E\.?|Right|O\.D\.)\b", re.IGNORECASE),
        "os": re.compile(r"\b(OS|L\.?E\.?|Left|O\.S\.)\b", re.IGNORECASE),
    }

    def __init__(self):
        # يمكن تعيين credentials عبر متغير بيئة GOOGLE_APPLICATION_CREDENTIALS
        self.client = vision.ImageAnnotatorClient()
        self.confidence_threshold = 75.0

    def preprocess_image(self, image_path: str) -> bytes:
        """معالجة الصورة وتحويلها لـ bytes"""
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"تعذر قراءة الصورة: {image_path}")

        # تحسين الصورة
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # تكبير
        scale = 200
        width = int(gray.shape[1] * scale / 100)
        height = int(gray.shape[0] * scale / 100)
        resized = cv2.resize(gray, (width, height), interpolation=cv2.INTER_CUBIC)

        # تقليل ضوضاء
        denoised = cv2.fastNlMeansDenoising(resized, None, 10, 7, 21)

        # تحسين تباين
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)

        # تحويل لـ bytes
        success, encoded = cv2.imencode('.png', enhanced)
        if not success:
            raise ValueError("فشل ترميز الصورة")

        return encoded.tobytes()

    def detect_text(self, image_bytes: bytes) -> tuple[str, float]:
        """اكتشاف النص باستخدام Google Vision"""
        image = vision.Image(content=image_bytes)

        # استخدام DOCUMENT_TEXT_DETECTION للوثائق المكتوبة
        response = self.client.document_text_detection(image=image)

        if response.error.message:
            raise Exception(f"Vision API Error: {response.error.message}")

        # استخراج النص الكامل
        full_text = response.full_text_annotation.text if response.full_text_annotation else ""

        # حساب الثقة المتوسطة
        confidences = []
        for page in response.full_text_annotation.pages:
            for block in page.blocks:
                confidences.append(block.confidence)

        avg_confidence = (sum(confidences) / len(confidences) * 100) if confidences else 0.0

        return full_text, avg_confidence

    def parse_prescription(self, text: str) -> Optional[PrescriptionBase]:
        """تحليل النص المستخرج"""
        lines = text.split('\n')

        od_data = {"sph": None, "cyl": 0.0, "axis": 0, "add": 0.0}
        os_data = {"sph": None, "cyl": 0.0, "axis": 0, "add": 0.0}
        pd_value = None

        current_eye = None  # 'od' or 'os'

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # تحديد العين
            if self.PATTERNS["od"].search(line):
                current_eye = "od"
                continue
            elif self.PATTERNS["os"].search(line):
                current_eye = "os"
                continue

            # استخراج القيم
            sph_match = self.PATTERNS["sph"].search(line)
            cyl_match = self.PATTERNS["cyl"].search(line)
            axis_match = self.PATTERNS["axis"].search(line)
            add_match = self.PATTERNS["add"].search(line)
            pd_match = self.PATTERNS["pd"].search(line)

            target = od_data if current_eye == "od" else (os_data if current_eye == "os" else od_data)

            if sph_match:
                target["sph"] = float(sph_match.group(1))
            if cyl_match:
                target["cyl"] = float(cyl_match.group(1))
            if axis_match:
                target["axis"] = int(axis_match.group(1))
            if add_match:
                target["add"] = float(add_match.group(1))
            if pd_match and pd_value is None:
                pd_value = float(pd_match.group(1))

        # التحقق من وجود SPH على الأقل
        if od_data["sph"] is None and os_data["sph"] is None:
            return None

        # إذا لم تُحدد عين واحدة، افترض أن القيم لـ OD
        if od_data["sph"] is None and os_data["sph"] is not None:
            od_data = os_data.copy()
        elif os_data["sph"] is None and od_data["sph"] is not None:
            os_data = od_data.copy()

        try:
            return PrescriptionBase(
                od=EyePrescription(
                    sph=od_data["sph"] or 0.0,
                    cyl=od_data["cyl"],
                    axis=od_data["axis"],
                    add=od_data["add"],
                ),
                os=EyePrescription(
                    sph=os_data["sph"] or 0.0,
                    cyl=os_data["cyl"],
                    axis=os_data["axis"],
                    add=os_data["add"],
                ),
                pd=pd_value,
            )
        except Exception:
            return None

    def process_image(self, image_path: str) -> OCRResponse:
        """معالجة الصورة الكاملة"""
        try:
            image_bytes = self.preprocess_image(image_path)
            raw_text, confidence = self.detect_text(image_bytes)
            prescription = self.parse_prescription(raw_text)

            if prescription and confidence >= self.confidence_threshold:
                return OCRResponse(
                    success=True,
                    prescription=prescription,
                    confidence=confidence,
                    raw_text=raw_text,
                    message="تم استخراج الوصفة بنجاح عبر Google Vision",
                )
            elif prescription:
                return OCRResponse(
                    success=True,
                    prescription=prescription,
                    confidence=confidence,
                    raw_text=raw_text,
                    message="تم الاستخراج لكن الثقة منخفضة - يرجى التحقق",
                )
            else:
                return OCRResponse(
                    success=False,
                    confidence=confidence,
                    raw_text=raw_text,
                    message="تعذر استخراج الوصفة - يرجى الإدخال اليدوي",
                )
        except Exception as e:
            return OCRResponse(
                success=False,
                confidence=0.0,
                message=f"خطأ: {str(e)}",
            )


# instance
ocr_service = GoogleVisionOCR()
