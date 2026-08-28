"""
خدمة OCR لاستخراج بيانات الوصفة الطبية من الصور

ملاحظة: هذا نموذج أولي. في الإنتاج، استخدم:
- Tesseract OCR + معالجة مسبقة
- أو خدمات سحابية (Google Vision API, Azure Form Recognizer)
- أو نماذج ML مخصصة (YOLO + CRNN)
"""
import re
import cv2
import numpy as np
from PIL import Image
from typing import Optional, Dict, Any
import pytesseract
from app.schemas import PrescriptionBase, EyePrescription, OCRResponse


class PrescriptionOCR:
    """مستخرج بيانات الوصفة الطبية من الصور"""

    # أنماط regex لاستخراج القيم
    PATTERNS = {
        "sph": re.compile(r"SPH[\s:]*([+-]?\d+\.?\d*)", re.IGNORECASE),
        "cyl": re.compile(r"CYL[\s:]*([+-]?\d+\.?\d*)", re.IGNORECASE),
        "axis": re.compile(r"AXIS[\s:]*(\d{1,3})", re.IGNORECASE),
        "add": re.compile(r"ADD[\s:]*([+-]?\d+\.?\d*)", re.IGNORECASE),
        "pd": re.compile(r"PD[\s:]*(\d{2,3}\.?\d*)", re.IGNORECASE),
    }

    def __init__(self):
        self.confidence_threshold = 60.0

    def preprocess_image(self, image_path: str) -> np.ndarray:
        """
        معالجة الصورة مسبقاً لتحسين دقة OCR
        """
        # قراءة الصورة
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"تعذر قراءة الصورة: {image_path}")

        # تحويل إلى رمادي
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # تكبير الصورة لتحسين OCR
        scale_percent = 200  # تكبير 200%
        width = int(gray.shape[1] * scale_percent / 100)
        height = int(gray.shape[0] * scale_percent / 100)
        resized = cv2.resize(gray, (width, height), interpolation=cv2.INTER_CUBIC)

        # تقليل الضوضاء
        denoised = cv2.fastNlMeansDenoising(resized, None, 10, 7, 21)

        # تحسين التباين
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)

        # ثنائية الصورة
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        return binary

    def extract_values(self, text: str) -> Dict[str, Any]:
        """
        استخراج القيم من النص باستخدام Regex
        """
        values = {}

        for field, pattern in self.PATTERNS.items():
            matches = pattern.findall(text)
            if matches:
                # أخذ أول قيمتين (OD ثم OS)
                values[field] = matches[:2]

        return values

    def parse_prescription(self, text: str) -> Optional[PrescriptionBase]:
        """
        تحليل النص واستخراج بيانات الوصفة
        """
        values = self.extract_values(text)

        # التحقق من وجود SPH على الأقل
        if "sph" not in values or len(values["sph"]) < 1:
            return None

        try:
            # العين اليمنى (OD) - القيمة الأولى
            od_sph = float(values["sph"][0])
            od_cyl = float(values["cyl"][0]) if "cyl" in values and len(values["cyl"]) > 0 else 0.0
            od_axis = int(values["axis"][0]) if "axis" in values and len(values["axis"]) > 0 else 0
            od_add = float(values["add"][0]) if "add" in values and len(values["add"]) > 0 else 0.0

            # العين اليسرى (OS) - القيمة الثانية أو نفس القيمة الأولى
            os_sph = float(values["sph"][1]) if len(values["sph"]) > 1 else od_sph
            os_cyl = float(values["cyl"][1]) if "cyl" in values and len(values["cyl"]) > 1 else od_cyl
            os_axis = int(values["axis"][1]) if "axis" in values and len(values["axis"]) > 1 else od_axis
            os_add = float(values["add"][1]) if "add" in values and len(values["add"]) > 1 else od_add

            # PD
            pd_value = None
            if "pd" in values:
                pd_value = float(values["pd"][0])

            prescription = PrescriptionBase(
                od=EyePrescription(sph=od_sph, cyl=od_cyl, axis=od_axis, add=od_add),
                os=EyePrescription(sph=os_sph, cyl=os_cyl, axis=os_axis, add=os_add),
                pd=pd_value
            )

            return prescription

        except (ValueError, IndexError) as e:
            return None

    def process_image(self, image_path: str) -> OCRResponse:
        """
        معالجة صورة الوصفة واستخراج البيانات
        """
        try:
            # معالجة الصورة
            processed_img = self.preprocess_image(image_path)

            # تشغيل OCR
            custom_config = r"--oem 3 --psm 6 -l eng+ara"
            raw_text = pytesseract.image_to_string(processed_img, config=custom_config)

            # حساب الثقة (تقريبية)
            data = pytesseract.image_to_data(processed_img, config=custom_config, output_type=pytesseract.Output.DICT)
            confidences = [int(c) for c in data["conf"] if int(c) > 0]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

            # تحليل الوصفة
            prescription = self.parse_prescription(raw_text)

            if prescription and avg_confidence >= self.confidence_threshold:
                return OCRResponse(
                    success=True,
                    prescription=prescription,
                    confidence=avg_confidence,
                    raw_text=raw_text,
                    message="تم استخراج الوصفة بنجاح"
                )
            elif prescription:
                return OCRResponse(
                    success=True,
                    prescription=prescription,
                    confidence=avg_confidence,
                    raw_text=raw_text,
                    message="تم استخراج الوصفة لكن الثقة منخفضة - يرجى التحقق"
                )
            else:
                return OCRResponse(
                    success=False,
                    confidence=avg_confidence,
                    raw_text=raw_text,
                    message="تعذر استخراج الوصفة - يرجى الإدخال اليدوي"
                )

        except Exception as e:
            return OCRResponse(
                success=False,
                confidence=0.0,
                message=f"خطأ في المعالجة: {str(e)}"
            )


# instance عالمي
ocr_service = PrescriptionOCR()
