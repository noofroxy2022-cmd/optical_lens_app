"""
محرك مطابقة العدسات النهائي - Optics Matching Logic

القواعد البصرية المطبقة:
1. Transposition: تحويل CYL الموجب إلى السلبي والعكس
2. Index Recommendation: توصية تلقائية بناءً على SPH
3. Aspherical Preference: تفضيل Aspherical للقوة العالية
4. Stock vs RX: تصنيف واضح
5. ADD Support: توجيه Progressive/Bifocal
"""
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session, joinedload
from app import models, schemas


class TranspositionEngine:
    """محرك Transposition - تحويل صيغ CYL"""

    @staticmethod
    def transpose(sph: float, cyl: float, axis: int) -> Tuple[float, float, int]:
        """
        تحويل الوصفة إلى صيغة CYL سالبة (الأكثر شيوعاً في الكتالوجات)

        القاعدة:
        - إذا CYL موجب: SPH_new = SPH + CYL, CYL_new = -CYL, Axis_new = Axis ± 90
        - إذا CYL سالب: لا تغيير
        """
        if cyl is None or cyl == 0:
            return sph, cyl or 0.0, axis or 0

        if cyl > 0:  # CYL موجب - يحتاج Transposition
            new_sph = sph + cyl
            new_cyl = -cyl
            new_axis = (axis + 90) % 180
            if new_axis == 0:
                new_axis = 180
            return round(new_sph, 2), round(new_cyl, 2), new_axis

        return sph, cyl, axis  # CYL سالب - لا تغيير

    @staticmethod
    def apply_to_prescription(prescription: schemas.PrescriptionCreate) -> schemas.PrescriptionCreate:
        """تطبيق Transposition على الوصفة الكاملة"""
        od_transposed = TranspositionEngine.transpose(
            prescription.od.sph,
            prescription.od.cyl or 0.0,
            prescription.od.axis or 0
        )
        os_transposed = TranspositionEngine.transpose(
            prescription.os.sph,
            prescription.os.cyl or 0.0,
            prescription.os.axis or 0
        )

        return schemas.PrescriptionCreate(
            customer_name=prescription.customer_name,
            customer_phone=prescription.customer_phone,
            od=schemas.EyePrescription(
                sph=od_transposed[0],
                cyl=od_transposed[1],
                axis=od_transposed[2],
                add=prescription.od.add
            ),
            os=schemas.EyePrescription(
                sph=os_transposed[0],
                cyl=os_transposed[1],
                axis=os_transposed[2],
                add=prescription.os.add
            ),
            pd=prescription.pd,
            notes=prescription.notes
        )


class OpticsRecommender:
    """محرك التوصيات البصرية"""

    INDEX_THRESHOLDS = [
        (2.0, 1.50, "CR-39 - اقتصادي للقوة المنخفضة"),
        (3.0, 1.56, "1.56 - خيار متوازن"),
        (4.0, 1.60, "1.60 - خفيف ورفيع"),
        (5.0, 1.61, "1.61 - أداء ممتاز"),
        (7.0, 1.67, "1.67 - رفيع جداً للقوة العالية"),
        (float('inf'), 1.74, "1.74 - الأرفع للقوة العالية جداً")
    ]

    @classmethod
    def recommend_index(cls, sph_power: float) -> Tuple[float, str]:
        """توصية Index بناءً على SPH"""
        abs_sph = abs(sph_power)
        for threshold, index, description in cls.INDEX_THRESHOLDS:
            if abs_sph <= threshold:
                return index, description
        return 1.74, "1.74 - الأرفع"

    @classmethod
    def recommend_aspherical(cls, sph_power: float, cyl_power: float) -> Tuple[bool, str]:
        """
        توصية Aspherical

        القواعد:
        - SPH > 3.0: يفضل Aspherical
        - CYL > 2.0: يفضل Aspherical
        - SPH + CYL > 4.0: يفضل Aspherical
        """
        abs_sph = abs(sph_power)
        abs_cyl = abs(cyl_power or 0)
        total = abs_sph + abs_cyl

        if total > 6.0:
            return True, "Aspherical ضروري للقوة العالية جداً"
        elif abs_sph > 3.0 or abs_cyl > 2.0:
            return True, "Aspherical موصى به لتحسين الجودة"
        elif total > 4.0:
            return True, "Aspherical يحسن الراحة البصرية"

        return False, "Spherical كافٍ للقوة المنخفضة"

    @classmethod
    def recommend_category(cls, add_value: float, age: Optional[int] = None) -> Tuple[str, str]:
        """توصية نوع العدسة بناءً على ADD"""
        if add_value is None or add_value == 0:
            return "single_vision", "عدسة أحادية البؤرة"
        elif add_value <= 1.50:
            return "progressive", "Progressive - للقراءة والبعد"
        elif add_value <= 2.50:
            return "progressive", "Progressive - إضافة متوسطة"
        else:
            return "bifocal", "Bifocal - إضافة عالية"


class LensMatcherFinal:
    """محرك المطابقة النهائي"""

    def __init__(self):
        self.tolerance_sph = 0.25
        self.tolerance_cyl = 0.25
        self.tolerance_add = 0.25
        self.transposition = TranspositionEngine()
        self.recommender = OpticsRecommender()

    def check_power_range(
        self,
        power_range: models.PowerRange,
        prescription: models.Prescription,
        eye: str = "od"
    ) -> Tuple[bool, str]:
        """التحقق من نطاق القوة لعين واحدة"""
        sph = prescription.od_sph if eye == "od" else prescription.os_sph
        cyl = prescription.od_cyl if eye == "od" else prescription.os_cyl
        add = prescription.od_add if eye == "od" else prescription.os_add

        issues = []

        # SPH
        if not (power_range.sph_min - self.tolerance_sph <= sph <= power_range.sph_max + self.tolerance_sph):
            issues.append(f"SPH {sph} خارج [{power_range.sph_min}, {power_range.sph_max}]")

        # CYL
        cyl_needed = cyl or 0.0
        if not (power_range.cyl_min - self.tolerance_cyl <= cyl_needed <= power_range.cyl_max + self.tolerance_cyl):
            issues.append(f"CYL {cyl_needed} خارج [{power_range.cyl_min}, {power_range.cyl_max}]")

        # ADD
        if add and add > 0:
            if power_range.add_min is None or power_range.add_max is None:
                issues.append("لا يدعم ADD")
            elif not (power_range.add_min - self.tolerance_add <= add <= power_range.add_max + self.tolerance_add):
                issues.append(f"ADD {add} خارج [{power_range.add_min}, {power_range.add_max}]")

        # قيد SPH المرتفع
        if (power_range.max_cyl_for_high_sph is not None and 
            power_range.sph_threshold is not None and
            abs(sph) >= abs(power_range.sph_threshold)):
            if abs(cyl_needed) > abs(power_range.max_cyl_for_high_sph):
                issues.append(f"CYL محدود لـ SPH ≥ {power_range.sph_threshold}")

        is_valid = len(issues) == 0
        return is_valid, "✓ مناسبة" if is_valid else "; ".join(issues)

    def calculate_match_score(
        self,
        lens_model: models.LensModel,
        variant: models.LensVariant,
        power_range: models.PowerRange,
        prescription: models.Prescription,
        filters: Optional[schemas.LensFilters] = None,
        prefer_stock: bool = True,
        prefer_aspherical: bool = True
    ) -> float:
        """حساب درجة المطابقة (0-100)"""
        score = 0.0
        max_sph = max(abs(prescription.od_sph), abs(prescription.os_sph))
        max_cyl = max(abs(prescription.od_cyl or 0), abs(prescription.os_cyl or 0))

        # 1. دقة نطاق القوة (30%)
        sph_center = (power_range.sph_min + power_range.sph_max) / 2
        sph_range = power_range.sph_max - power_range.sph_min
        od_dist = abs(prescription.od_sph - sph_center)
        os_dist = abs(prescription.os_sph - sph_center)
        avg_dist = (od_dist + os_dist) / 2
        power_score = max(0, 30 * (1 - avg_dist / (sph_range / 2))) if sph_range > 0 else (30 if avg_dist < 0.5 else 0)
        score += power_score

        # 2. Index مناسب (20%)
        recommended_index, _ = self.recommender.recommend_index(max_sph)
        index_diff = abs(variant.index_value - recommended_index)
        index_score = max(0, 20 - (index_diff * 25))
        score += index_score

        # 3. Aspherical (15%)
        need_aspherical, _ = self.recommender.recommend_aspherical(max_sph, max_cyl)
        if need_aspherical and variant.is_aspherical:
            score += 15
        elif not need_aspherical:
            score += 15  # لا حاجة = نقاط كاملة
        elif need_aspherical and not variant.is_aspherical:
            score += 5   # يحتاج لكن غير متوفر

        # 4. التوفر (15%)
        if prefer_stock:
            if variant.availability == models.LensAvailability.STOCK:
                score += 15
            elif variant.availability == models.LensAvailability.BOTH:
                score += 12
            else:
                score += 6
        else:
            score += 15

        # 5. الميزات (10%)
        feature_score = 10
        if filters and filters.features:
            model_features = lens_model.features or []
            matched = sum(1 for f in filters.features if f in model_features)
            feature_score = (matched / len(filters.features)) * 10
        score += feature_score

        # 6. السعر (7%)
        if filters and filters.max_price:
            score += 7 if variant.price <= filters.max_price else 0
        else:
            score += 7

        # 7. الشركة (3%)
        if filters and filters.company_id:
            score += 3 if lens_model.company_id == filters.company_id else 0.5
        else:
            score += 3

        return min(100, max(0, round(score, 1)))

    def match_lenses(
        self,
        db: Session,
        prescription: models.Prescription,
        filters: Optional[schemas.LensFilters] = None,
        prefer_stock: bool = True,
        prefer_aspherical: bool = True
    ) -> Tuple[List[schemas.LensMatchResult], int, int, str, str]:
        """
        مطابقة الوصفة

        Returns: (results, stock_count, rx_count, index_rec, aspherical_rec)
        """
        results = []
        stock_count = 0
        rx_count = 0

        max_sph = max(abs(prescription.od_sph), abs(prescription.os_sph))
        max_cyl = max(abs(prescription.od_cyl or 0), abs(prescription.os_cyl or 0))

        # التوصيات
        recommended_index, index_desc = self.recommender.recommend_index(max_sph)
        need_aspherical, aspherical_desc = self.recommender.recommend_aspherical(max_sph, max_cyl)

        # جلب العدسات
        query = db.query(models.LensModel).options(
            joinedload(models.LensModel.company),
            joinedload(models.LensModel.variants).joinedload(models.LensVariant.power_ranges)
        ).join(models.Company).filter(
            models.Company.is_active == True,
            models.Company.is_deleted == False,
            models.LensModel.is_active == True,
            models.LensModel.is_deleted == False,
        )

        if filters:
            if filters.company_id:
                query = query.filter(models.LensModel.company_id == filters.company_id)
            if filters.category:
                query = query.filter(models.LensModel.category == filters.category)

        lens_models = query.all()

        for lens_model in lens_models:
            for variant in lens_model.variants:
                if not variant.is_active:
                    continue

                # فلترة
                if filters:
                    if filters.material and variant.material != filters.material:
                        continue
                    if filters.index_value and abs(variant.index_value - filters.index_value) > 0.01:
                        continue
                    if filters.min_index and variant.index_value < filters.min_index:
                        continue
                    if filters.max_index and variant.index_value > filters.max_index:
                        continue
                    if filters.availability and variant.availability != filters.availability:
                        continue
                    if filters.design_type and variant.design_type != filters.design_type:
                        continue
                    if filters.prefer_aspherical is not None:
                        if filters.prefer_aspherical and not variant.is_aspherical:
                            continue
                    if filters.max_price and variant.price > filters.max_price:
                        continue

                # التحقق من نطاقات القوة
                for power_range in variant.power_ranges:
                    od_valid, _ = self.check_power_range(power_range, prescription, "od")
                    os_valid, _ = self.check_power_range(power_range, prescription, "os")

                    if od_valid and os_valid:
                        score = self.calculate_match_score(
                            lens_model, variant, power_range,
                            prescription, filters, prefer_stock, prefer_aspherical
                        )

                        reason = self._build_reason(lens_model, variant, power_range, prescription, score, 
                                                    recommended_index, need_aspherical)

                        result = schemas.LensMatchResult(
                            lens_model=schemas.LensModelResponse.model_validate(lens_model),
                            variant=schemas.LensVariantResponse.model_validate(variant),
                            match_score=score,
                            reason=reason,
                            power_range=schemas.PowerRangeResponse.model_validate(power_range),
                            is_recommended=score >= 60,
                            index_recommended=abs(variant.index_value - recommended_index) < 0.1,
                            aspherical_recommended=variant.is_aspherical and need_aspherical,
                            stock_available=variant.availability in [models.LensAvailability.STOCK, models.LensAvailability.BOTH]
                        )

                        results.append(result)

                        if variant.availability in [models.LensAvailability.STOCK, models.LensAvailability.BOTH]:
                            stock_count += 1
                        if variant.availability in [models.LensAvailability.RX, models.LensAvailability.BOTH]:
                            rx_count += 1

        results.sort(key=lambda x: x.match_score, reverse=True)

        return results, stock_count, rx_count, index_desc, aspherical_desc

    def _build_reason(self, lens_model, variant, power_range, prescription, score, 
                      rec_index, need_aspherical):
        """بناء رسالة توصية"""
        reasons = []
        max_sph = max(abs(prescription.od_sph), abs(prescription.os_sph))

        if score >= 90:
            reasons.append("⭐ مطابقة ممتازة")
        elif score >= 75:
            reasons.append("✓ مطابقة جيدة جداً")
        elif score >= 60:
            reasons.append("✓ مطابقة مقبولة")

        # Index
        if abs(variant.index_value - rec_index) < 0.1:
            reasons.append(f"Index {variant.index_value} مثالي")

        # Aspherical
        if variant.is_aspherical and need_aspherical:
            reasons.append("✓ Aspherical للقوة العالية")

        # التوفر
        avail_map = {
            models.LensAvailability.STOCK: "📦 متوفر فوراً",
            models.LensAvailability.RX: "⏱ يحتاج تصنيع",
            models.LensAvailability.BOTH: "📦 متوفر Stock & RX"
        }
        reasons.append(avail_map.get(variant.availability, ""))

        # ميزات
        features = lens_model.features or []
        if features:
            feature_names = {
                "anti_reflective": "AR",
                "photochromic": "Photo",
                "blue_light_filter": "Blue Light",
                "uv_protection": "UV"
            }
            feature_list = [feature_names.get(f, f) for f in features[:3]]
            reasons.append(f"ميزات: {', '.join(feature_list)}")

        return " | ".join(filter(None, reasons))


# instance
lens_matcher = LensMatcherFinal()
