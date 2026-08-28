"""
PDF Parser لاستخراج جداول نطاقات القوة من كتالوجات الشركات

يدعم:
- استخراج الجداول من PDF
- التعرف على SPH, CYL, ADD, Index
- التعرف على Stock vs RX
- تصدير إلى قاعدة البيانات

المتطلبات:
- pdfplumber (لاستخراج الجداول)
- camelot-py (بديل للجداول المعقدة)
- tabula-py (بديل آخر)
"""
import re
import pdfplumber
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AvailabilityType(str, Enum):
    STOCK = "stock"
    RX = "rx"
    BOTH = "both"


@dataclass
class ExtractedPowerRange:
    """نطاق قوة مستخرج من PDF"""
    sph_min: float
    sph_max: float
    cyl_min: float = -10.0
    cyl_max: float = 0.0
    add_min: Optional[float] = None
    add_max: Optional[float] = None
    index_value: Optional[float] = None
    material: Optional[str] = None
    availability: AvailabilityType = AvailabilityType.STOCK
    price: Optional[float] = None
    notes: Optional[str] = None


@dataclass
class ExtractedLensModel:
    """نموذج عدسة مستخرج من PDF"""
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


class PDFCatalogParser:
    """
    محلل كتالوجات PDF للعدسات البصرية

    يدعم أنماط مختلفة من الجداول:
    1. جداول بسيطة: SPH | CYL | Index
    2. جداول Matrix: SPH × CYL
    3. جداول متعددة الصفحات
    """

    # أنماط regex للتعرف على القيم
    INDEX_PATTERNS = [
        re.compile(r"1\.50|1\.56|1\.60|1\.61|1\.67|1\.74", re.IGNORECASE),
        re.compile(r"Index[\s:]*(1\.\d{2})", re.IGNORECASE),
        re.compile(r"(1\.\d{2})[\s]*Index", re.IGNORECASE),
    ]

    SPH_PATTERNS = [
        re.compile(r"SPH[\s:]*([+-]?\d+\.?\d*)[\s]*to[\s]*([+-]?\d+\.?\d*)", re.IGNORECASE),
        re.compile(r"([+-]?\d+\.?\d*)[\s]*≤?[\s]*SPH[\s]*≤?[\s]*([+-]?\d+\.?\d*)", re.IGNORECASE),
        re.compile(r"([+-]?\d+\.?\d*)[\s]*-[\s]*([+-]?\d+\.?\d*)", re.IGNORECASE),
    ]

    CYL_PATTERNS = [
        re.compile(r"CYL[\s:]*([+-]?\d+\.?\d*)[\s]*to[\s]*([+-]?\d+\.?\d*)", re.IGNORECASE),
        re.compile(r"([+-]?\d+\.?\d*)[\s]*≤?[\s]*CYL[\s]*≤?[\s]*([+-]?\d+\.?\d*)", re.IGNORECASE),
    ]

    ADD_PATTERNS = [
        re.compile(r"ADD[\s:]*([+-]?\d+\.?\d*)[\s]*to[\s]*([+-]?\d+\.?\d*)", re.IGNORECASE),
        re.compile(r"([+-]?\d+\.?\d*)[\s]*≤?[\s]*ADD[\s]*≤?[\s]*([+-]?\d+\.?\d*)", re.IGNORECASE),
    ]

    STOCK_KEYWORDS = ["stock", "in stock", "available", "ready", "سريع"]
    RX_KEYWORDS = ["rx", "custom", "made to order", "fabrication", "تفصيل", "تصنيع"]

    def __init__(self):
        self.extracted_models: List[ExtractedLensModel] = []
        self.errors: List[str] = []

    def parse_pdf(self, pdf_path: str, company_name: str = "") -> List[ExtractedLensModel]:
        """
        تحليل ملف PDF كامل
        """
        logger.info(f"Parsing PDF: {pdf_path}")
        self.extracted_models = []
        self.errors = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                logger.info(f"Total pages: {len(pdf.pages)}")

                current_model: Optional[ExtractedLensModel] = None
                current_index: Optional[float] = None
                current_availability: AvailabilityType = AvailabilityType.STOCK

                for page_num, page in enumerate(pdf.pages, 1):
                    logger.info(f"Processing page {page_num}")

                    # استخراج النص
                    text = page.extract_text() or ""

                    # التعرف على اسم نموذج العدسة
                    model_name = self._extract_model_name(text)
                    if model_name:
                        if current_model:
                            self.extracted_models.append(current_model)
                        current_model = ExtractedLensModel(name=model_name)
                        logger.info(f"Found lens model: {model_name}")

                    # التعرف على Index
                    index = self._extract_index(text)
                    if index:
                        current_index = index

                    # التعرف على التوفر
                    availability = self._detect_availability(text)
                    if availability:
                        current_availability = availability

                    # استخراج الجداول
                    tables = page.extract_tables()
                    for table in tables:
                        ranges = self._parse_table(
                            table, 
                            current_index, 
                            current_availability,
                            current_model.name if current_model else "Unknown"
                        )
                        if current_model:
                            current_model.power_ranges.extend(ranges)

                        # استخراج variants من الجدول
                        variants = self._extract_variants_from_table(table)
                        if current_model:
                            current_model.variants.extend(variants)

                # إضافة آخر نموذج
                if current_model:
                    self.extracted_models.append(current_model)

        except Exception as e:
            self.errors.append(f"Error parsing PDF: {str(e)}")
            logger.error(f"PDF parsing error: {e}")

        logger.info(f"Extracted {len(self.extracted_models)} lens models")
        return self.extracted_models

    def _extract_model_name(self, text: str) -> Optional[str]:
        """استخراج اسم نموذج العدسة من النص"""
        # أنماط شائعة لأسماء العدسات
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
        """استخراج معامل الانكسار"""
        for pattern in self.INDEX_PATTERNS:
            match = pattern.search(text)
            if match:
                try:
                    return float(match.group(1))
                except (ValueError, IndexError):
                    continue
        return None

    def _detect_availability(self, text: str) -> Optional[AvailabilityType]:
        """اكتشاف نوع التوفر (Stock vs RX)"""
        text_lower = text.lower()

        has_stock = any(kw in text_lower for kw in self.STOCK_KEYWORDS)
        has_rx = any(kw in text_lower for kw in self.RX_KEYWORDS)

        if has_stock and has_rx:
            return AvailabilityType.BOTH
        elif has_rx:
            return AvailabilityType.RX
        elif has_stock:
            return AvailabilityType.STOCK

        return None

    def _parse_table(
        self, 
        table: List[List[str]], 
        default_index: Optional[float],
        default_availability: AvailabilityType,
        model_name: str
    ) -> List[ExtractedPowerRange]:
        """
        تحليل جدول واستخراج نطاقات القوة

        يدعم أنماط:
        - SPH | CYL | ADD
        - SPH Range | CYL Range | Index
        - Matrix: SPH × CYL
        """
        ranges = []

        if not table or len(table) < 2:
            return ranges

        headers = [str(h).strip().lower() if h else "" for h in table[0]]

        # تحديد أعمدة SPH, CYL, ADD
        sph_col = self._find_column_index(headers, ["sph", "sphere", "power", "قوة"])
        cyl_col = self._find_column_index(headers, ["cyl", "cylinder", "استجماتيزم"])
        add_col = self._find_column_index(headers, ["add", "addition", "إضافة"])
        index_col = self._find_column_index(headers, ["index", "indx", "معامل", "انكسار"])
        price_col = self._find_column_index(headers, ["price", "cost", "سعر", "السعر"])

        for row in table[1:]:
            if not row or all(not cell for cell in row):
                continue

            try:
                range_data = ExtractedPowerRange(
                    sph_min=0, sph_max=0,
                    index_value=default_index,
                    availability=default_availability
                )

                # استخراج SPH
                if sph_col is not None and sph_col < len(row):
                    sph_values = self._parse_range_value(str(row[sph_col]))
                    if sph_values:
                        range_data.sph_min, range_data.sph_max = sph_values

                # استخراج CYL
                if cyl_col is not None and cyl_col < len(row):
                    cyl_values = self._parse_range_value(str(row[cyl_col]))
                    if cyl_values:
                        range_data.cyl_min, range_data.cyl_max = cyl_values

                # استخراج ADD
                if add_col is not None and add_col < len(row):
                    add_values = self._parse_range_value(str(row[add_col]))
                    if add_values:
                        range_data.add_min, range_data.add_max = add_values

                # استخراج Index
                if index_col is not None and index_col < len(row):
                    idx = self._extract_index(str(row[index_col]))
                    if idx:
                        range_data.index_value = idx

                # استخراج السعر
                if price_col is not None and price_col < len(row):
                    price = self._extract_price(str(row[price_col]))
                    if price:
                        range_data.price = price

                # التحقق من صحة البيانات
                if range_data.sph_min != 0 or range_data.sph_max != 0:
                    ranges.append(range_data)

            except Exception as e:
                self.errors.append(f"Error parsing row {row}: {str(e)}")
                continue

        return ranges

    def _find_column_index(self, headers: List[str], keywords: List[str]) -> Optional[int]:
        """البحث عن عمود بناءً على الكلمات المفتاحية"""
        for i, header in enumerate(headers):
            for keyword in keywords:
                if keyword.lower() in header.lower():
                    return i
        return None

    def _parse_range_value(self, value: str) -> Optional[Tuple[float, float]]:
        """
        تحليل قيمة النطاق
        يدعم: "-6.00 to +6.00", "±6.00", "-6.00 / +6.00", "0 ~ -10"
        """
        value = value.strip().replace("±", "+-")

        # نمط: -6.00 to +6.00
        match = re.search(r"([+-]?\d+\.?\d*)\s*(?:to|~|/|\-|\+)\s*([+-]?\d+\.?\d*)", value)
        if match:
            try:
                min_val = float(match.group(1))
                max_val = float(match.group(2))
                return (min(min_val, max_val), max(min_val, max_val))
            except ValueError:
                pass

        # نمط: ±6.00
        match = re.search(r"[+-]?\s*(\d+\.?\d*)", value)
        if match:
            try:
                val = float(match.group(1))
                return (-val, val)
            except ValueError:
                pass

        return None

    def _extract_price(self, value: str) -> Optional[float]:
        """استخراج السعر من النص"""
        match = re.search(r"(\d+\.?\d*)", value.replace(",", ""))
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        return None

    def _extract_variants_from_table(self, table: List[List[str]]) -> List[Dict[str, Any]]:
        """استخراج variants من الجدول"""
        variants = []
        # هذا تبسيط - في الواقع يحتاج منطق أكثر تعقيداً
        return variants

    def to_db_format(self, company_id: int) -> List[Dict[str, Any]]:
        """
        تحويل البيانات المستخرجة إلى صيغة قاعدة البيانات
        """
        result = []

        for model in self.extracted_models:
            model_data = {
                "company_id": company_id,
                "name": model.name,
                "name_ar": model.name_ar,
                "lens_code": model.lens_code,
                "category": model.category,
                "description": model.description,
                "features": model.features,
                "variants": [],
                "power_ranges": []
            }

            # تجميع variants فريدة
            seen_variants = set()
            for pr in model.power_ranges:
                variant_key = (pr.index_value, pr.material, pr.availability.value)
                if variant_key not in seen_variants:
                    seen_variants.add(variant_key)
                    model_data["variants"].append({
                        "material": pr.material or "CR39",
                        "index_value": pr.index_value or 1.50,
                        "availability": pr.availability.value,
                        "price": pr.price or 0,
                    })

                model_data["power_ranges"].append({
                    "sph_min": pr.sph_min,
                    "sph_max": pr.sph_max,
                    "cyl_min": pr.cyl_min,
                    "cyl_max": pr.cyl_max,
                    "add_min": pr.add_min,
                    "add_max": pr.add_max,
                    "index_value": pr.index_value,
                    "availability": pr.availability.value,
                    "notes": pr.notes,
                })

            result.append(model_data)

        return result


# ===== دوال مساعدة للـ Import =====
def import_pdf_to_db(
    pdf_path: str,
    company_id: int,
    db_session,
    override_existing: bool = False
) -> Dict[str, Any]:
    """
    استيراد PDF مباشرة إلى قاعدة البيانات
    """
    from app import crud, models, schemas

    parser = PDFCatalogParser()
    extracted = parser.parse_pdf(pdf_path)

    imported_models = 0
    imported_variants = 0
    imported_ranges = 0

    for model_data in parser.to_db_format(company_id):
        # إنشاء LensModel
        lens_model = crud.create_lens_model(
            db_session,
            schemas.LensModelCreate(
                company_id=company_id,
                name=model_data["name"],
                name_ar=model_data.get("name_ar"),
                lens_code=model_data.get("lens_code"),
                category=model_data.get("category", "single_vision"),
                description=model_data.get("description"),
                features=model_data.get("features"),
            )
        )
        imported_models += 1

        # إنشاء Variants
        for variant_data in model_data["variants"]:
            variant = crud.create_lens_variant(
                db_session,
                schemas.LensVariantCreate(
                    lens_model_id=lens_model.id,
                    material=variant_data["material"],
                    index_value=variant_data["index_value"],
                    availability=variant_data["availability"],
                    price=variant_data["price"],
                )
            )
            imported_variants += 1

            # إنشاء PowerRanges
            for range_data in model_data["power_ranges"]:
                if (range_data.get("index_value") == variant_data["index_value"] and
                    range_data.get("availability") == variant_data["availability"]):
                    crud.create_power_range(
                        db_session,
                        schemas.PowerRangeCreate(
                            lens_model_id=lens_model.id,
                            variant_id=variant.id,
                            sph_min=range_data["sph_min"],
                            sph_max=range_data["sph_max"],
                            cyl_min=range_data.get("cyl_min", -10.0),
                            cyl_max=range_data.get("cyl_max", 0.0),
                            add_min=range_data.get("add_min"),
                            add_max=range_data.get("add_max"),
                            notes=range_data.get("notes"),
                        )
                    )
                    imported_ranges += 1

    return {
        "success": True,
        "extracted_models": imported_models,
        "extracted_variants": imported_variants,
        "extracted_ranges": imported_ranges,
        "errors": parser.errors,
        "message": f"تم استيراد {imported_models} نموذج، {imported_variants} متغير، {imported_ranges} نطاق قوة"
    }
