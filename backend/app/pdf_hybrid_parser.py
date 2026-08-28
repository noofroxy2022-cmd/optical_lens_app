"""
PDF Hybrid Parser - مستخرج هجين

يدمج:
1. pdfplumber (للجداول المنظمة)
2. Google Vision API (للجداول الملونة/المركبة)
3. شاشة Preview & Confirm

الأنماط المدعومة:
- جداول بسيطة: SPH | CYL | ADD
- جداول Matrix: SPH × CYL
- جداول ملونة: Stock (أخضر) vs RX (أحمر)
- نطاقات قوة معقدة مع قيود
"""
import re
import os
import json
import pdfplumber
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from google.cloud import vision
from google.oauth2 import service_account
import cv2
import numpy as np
from PIL import Image


@dataclass
class ExtractedPowerRange:
    sph_min: float
    sph_max: float
    cyl_min: float = -10.0
    cyl_max: float = 0.0
    add_min: Optional[float] = None
    add_max: Optional[float] = None
    index_value: Optional[float] = None
    material: Optional[str] = None
    availability: str = "stock"
    price: Optional[float] = None
    design_type: str = "spherical"
    is_aspherical: bool = False
    notes: Optional[str] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class ExtractedLensModel:
    name: str
    name_ar: Optional[str] = None
    lens_code: Optional[str] = None
    category: str = "single_vision"
    description: Optional[str] = None
    features: List[str] = None
    variants: List[Dict[str, Any]] = None
    power_ranges: List[ExtractedPowerRange] = None

    def __post_init__(self):
        if self.features is None:
            self.features = []
        if self.variants is None:
            self.variants = []
        if self.power_ranges is None:
            self.power_ranges = []

    def to_dict(self):
        return {
            "name": self.name,
            "name_ar": self.name_ar,
            "lens_code": self.lens_code,
            "category": self.category,
            "description": self.description,
            "features": self.features,
            "variants": self.variants,
            "power_ranges": [pr.to_dict() for pr in self.power_ranges]
        }


class PDFHybridParser:
    """
    محلل هجين لكتالوجات PDF

    يستخدم pdfplumber للجداول البسيطة
    و Google Vision للجداول المعقدة/الملونة
    """

    # أنماط regex
    INDEX_PATTERNS = [
        re.compile(r"1\.50|1\.56|1\.60|1\.61|1\.67|1\.74", re.IGNORECASE),
        re.compile(r"Index[\s:]*(1\.\d{2})", re.IGNORECASE),
        re.compile(r"(1\.\d{2})[\s]*Index", re.IGNORECASE),
        re.compile(r"Index[\s]+(1\.\d{2})", re.IGNORECASE),
    ]

    SPH_PATTERNS = [
        re.compile(r"SPH[\s:]*([+-]?\d+\.?\d*)[\s]*to[\s]*([+-]?\d+\.?\d*)", re.IGNORECASE),
        re.compile(r"([+-]?\d+\.?\d*)[\s]*≤?[\s]*SPH[\s]*≤?[\s]*([+-]?\d+\.?\d*)", re.IGNORECASE),
        re.compile(r"([+-]?\d+\.?\d*)[\s]*-[\s]*([+-]?\d+\.?\d*)", re.IGNORECASE),
        re.compile(r"([+-]?\d+\.?\d*)[\s]*~[\s]*([+-]?\d+\.?\d*)", re.IGNORECASE),
    ]

    STOCK_COLORS = [(0, 150, 0), (50, 200, 50), (100, 255, 100)]  # أخضر
    RX_COLORS = [(200, 50, 50), (255, 100, 100), (255, 150, 150)]  # أحمر

    def __init__(self, use_vision: bool = True):
        self.use_vision = use_vision
        self.client = None
        if use_vision:
            try:
                self.client = vision.ImageAnnotatorClient()
            except Exception as e:
                print(f"Warning: Could not initialize Vision API: {e}")

        self.extracted_models: List[ExtractedLensModel] = []
        self.errors: List[str] = []

    def parse_pdf(self, pdf_path: str, company_name: str = "") -> List[ExtractedLensModel]:
        """تحليل PDF كامل"""
        self.extracted_models = []
        self.errors = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                current_model: Optional[ExtractedLensModel] = None
                current_index: Optional[float] = None
                current_availability: str = "stock"

                for page_num, page in enumerate(pdf.pages, 1):
                    text = page.extract_text() or ""

                    # التعرف على نموذج جديد
                    model_name = self._extract_model_name(text)
                    if model_name:
                        if current_model:
                            self.extracted_models.append(current_model)
                        current_model = ExtractedLensModel(name=model_name)
                        current_index = None
                        current_availability = "stock"

                    # استخراج Index
                    idx = self._extract_index(text)
                    if idx:
                        current_index = idx

                    # استخراج التوفر من الألوان (إذا كان Vision متاح)
                    if self.client:
                        availability = self._detect_availability_by_color(page)
                        if availability:
                            current_availability = availability

                    # استخراج الجداول
                    tables = page.extract_tables()
                    for table in tables:
                        ranges = self._parse_table(table, current_index, current_availability)
                        if current_model:
                            current_model.power_ranges.extend(ranges)

                if current_model:
                    self.extracted_models.append(current_model)

                # تجميع variants من power ranges
                self._consolidate_variants()

        except Exception as e:
            self.errors.append(f"Error: {str(e)}")

        return self.extracted_models

    def _extract_model_name(self, text: str) -> Optional[str]:
        """استخراج اسم النموذج"""
        patterns = [
            re.compile(r"(?:Lens|Lenses|عدسة|عدسات)[\s:]*([A-Z][A-Za-z0-9\s\-]+)", re.IGNORECASE),
            re.compile(r"(?:Model|Series|سلسلة)[\s:]*([A-Z][A-Za-z0-9\s\-]+)", re.IGNORECASE),
            re.compile(r"^([A-Z][A-Za-z0-9\s\-]{3,50})$", re.MULTILINE),
        ]
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return match.group(1).strip()
        return None

    def _extract_index(self, text: str) -> Optional[float]:
        """استخراج Index"""
        for pattern in self.INDEX_PATTERNS:
            match = pattern.search(text)
            if match:
                try:
                    return float(match.group(1))
                except:
                    continue
        return None

    def _detect_availability_by_color(self, page) -> Optional[str]:
        """اكتشاف Stock/RX من ألوان الخلايا"""
        if not self.client:
            return None

        try:
            # تحويل الصفحة لصورة
            img = page.to_image(resolution=150)
            img_bytes = img.original

            # تحليل الألوان
            nparr = np.frombuffer(img_bytes, np.uint8)
            img_cv = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img_cv is None:
                return None

            # حساب متوسط الألوان
            hsv = cv2.cvtColor(img_cv, cv2.COLOR_BGR2HSV)

            # نطاقات الألوان
            green_mask = cv2.inRange(hsv, (35, 50, 50), (85, 255, 255))
            red_mask1 = cv2.inRange(hsv, (0, 50, 50), (10, 255, 255))
            red_mask2 = cv2.inRange(hsv, (170, 50, 50), (180, 255, 255))
            red_mask = cv2.bitwise_or(red_mask1, red_mask2)

            green_pixels = cv2.countNonZero(green_mask)
            red_pixels = cv2.countNonZero(red_mask)

            if green_pixels > red_pixels * 2:
                return "stock"
            elif red_pixels > green_pixels * 2:
                return "rx"
            elif green_pixels > 1000 and red_pixels > 1000:
                return "both"

        except Exception as e:
            self.errors.append(f"Color detection error: {e}")

        return None

    def _parse_table(self, table, default_index, default_availability):
        """تحليل جدول"""
        ranges = []
        if not table or len(table) < 2:
            return ranges

        headers = [str(h).strip().lower() if h else "" for h in table[0]]

        sph_col = self._find_col(headers, ["sph", "sphere", "power", "قوة"])
        cyl_col = self._find_col(headers, ["cyl", "cylinder", "استجماتيزم"])
        add_col = self._find_col(headers, ["add", "addition", "إضافة"])
        index_col = self._find_col(headers, ["index", "indx", "انكسار"])
        price_col = self._find_col(headers, ["price", "cost", "سعر"])
        material_col = self._find_col(headers, ["material", "مادة", "خامة"])
        design_col = self._find_col(headers, ["design", "تصميم", "aspherical"])

        for row in table[1:]:
            if not row or all(not cell for cell in row):
                continue

            try:
                pr = ExtractedPowerRange(
                    sph_min=0, sph_max=0,
                    index_value=default_index,
                    availability=default_availability
                )

                if sph_col is not None and sph_col < len(row):
                    vals = self._parse_range(str(row[sph_col]))
                    if vals:
                        pr.sph_min, pr.sph_max = vals

                if cyl_col is not None and cyl_col < len(row):
                    vals = self._parse_range(str(row[cyl_col]))
                    if vals:
                        pr.cyl_min, pr.cyl_max = vals

                if add_col is not None and add_col < len(row):
                    vals = self._parse_range(str(row[add_col]))
                    if vals:
                        pr.add_min, pr.add_max = vals

                if index_col is not None and index_col < len(row):
                    idx = self._extract_index(str(row[index_col]))
                    if idx:
                        pr.index_value = idx

                if price_col is not None and price_col < len(row):
                    pr.price = self._extract_price(str(row[price_col]))

                if material_col is not None and material_col < len(row):
                    pr.material = str(row[material_col]).strip()

                if design_col is not None and design_col < len(row):
                    design_text = str(row[design_col]).lower()
                    if "aspherical" in design_text or "asp" in design_text:
                        pr.is_aspherical = True
                        pr.design_type = "aspherical"
                    elif "free" in design_text:
                        pr.design_type = "free_form"

                if pr.sph_min != 0 or pr.sph_max != 0:
                    ranges.append(pr)

            except Exception as e:
                self.errors.append(f"Row error: {e}")
                continue

        return ranges

    def _find_col(self, headers, keywords):
        for i, h in enumerate(headers):
            for kw in keywords:
                if kw.lower() in h.lower():
                    return i
        return None

    def _parse_range(self, value):
        value = str(value).strip().replace("±", "+-")
        match = re.search(r"([+-]?\d+\.?\d*)\s*(?:to|~|/|-|\+)\s*([+-]?\d+\.?\d*)", value)
        if match:
            try:
                a, b = float(match.group(1)), float(match.group(2))
                return (min(a, b), max(a, b))
            except:
                pass
        match = re.search(r"[+-]?\s*(\d+\.?\d*)", value)
        if match:
            try:
                v = float(match.group(1))
                return (-v, v)
            except:
                pass
        return None

    def _extract_price(self, value):
        match = re.search(r"(\d+\.?\d*)", str(value).replace(",", ""))
        if match:
            try:
                return float(match.group(1))
            except:
                pass
        return None

    def _consolidate_variants(self):
        """تجميع variants فريدة من power ranges"""
        for model in self.extracted_models:
            seen = set()
            for pr in model.power_ranges:
                key = (pr.index_value, pr.material, pr.availability, pr.design_type, pr.is_aspherical)
                if key not in seen:
                    seen.add(key)
                    model.variants.append({
                        "material": pr.material or "CR39",
                        "index_value": pr.index_value or 1.50,
                        "availability": pr.availability,
                        "design_type": pr.design_type,
                        "is_aspherical": pr.is_aspherical,
                        "price": pr.price or 0,
                    })

    def to_preview_format(self) -> List[Dict[str, Any]]:
        """تحويل لصيغة المعاينة"""
        preview = []
        for i, model in enumerate(self.extracted_models):
            preview.append({
                "id": i,
                "name": model.name,
                "category": model.category,
                "variants_count": len(model.variants),
                "power_ranges_count": len(model.power_ranges),
                "variants": model.variants,
                "sample_ranges": [
                    {
                        "sph": f"[{r.sph_min}, {r.sph_max}]",
                        "cyl": f"[{r.cyl_min}, {r.cyl_max}]",
                        "add": f"[{r.add_min}, {r.add_max}]" if r.add_min else "—",
                        "index": r.index_value,
                        "availability": r.availability,
                        "design": r.design_type,
                        "aspherical": r.is_aspherical,
                    }
                    for r in model.power_ranges[:3]
                ]
            })
        return preview

    def save_extractions_to_db(self, catalog_id: int, db_session):
        """حفظ البيانات المستخرجة في جدول CatalogExtraction للمعاينة"""
        from app import models

        for model in self.extracted_models:
            for pr in model.power_ranges:
                extraction = models.CatalogExtraction(
                    catalog_id=catalog_id,
                    extracted_name=model.name,
                    extracted_category=model.category,
                    extracted_material=pr.material,
                    extracted_index=pr.index_value,
                    extracted_availability=pr.availability,
                    sph_min=pr.sph_min,
                    sph_max=pr.sph_max,
                    cyl_min=pr.cyl_min,
                    cyl_max=pr.cyl_max,
                    add_min=pr.add_min,
                    add_max=pr.add_max,
                    extracted_price=pr.price,
                    extracted_features=model.features,
                    status="pending"
                )
                db_session.add(extraction)

        db_session.commit()


def preview_pdf_file(pdf_path: str, use_vision: bool = True) -> Dict[str, Any]:
    """معاينة سريعة لملف PDF"""
    parser = PDFHybridParser(use_vision=use_vision)
    extracted = parser.parse_pdf(pdf_path)

    return {
        "success": len(parser.errors) == 0,
        "extracted_models": len(extracted),
        "preview": parser.to_preview_format(),
        "errors": parser.errors
    }
