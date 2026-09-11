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
from decimal import Decimal
from sqlalchemy.orm import Session, joinedload, selectinload
from app import models, schemas


def _norm_scope(value: Optional[str]) -> str:
    """Deterministic key for a nullable market/power scope string."""
    return (value or "").strip().lower()


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

    # ----- signed-cylinder convention handling --------------------------------
    @staticmethod
    def _plus_form(sph, cyl, axis):
        """Derive the PLUS-cylinder equivalent of a stored (minus) form using
        the project's existing transposition algebra: S' = S + C, C' = -C,
        Axis' = (Axis + 90) mod 180 (0 -> 180). CYL == 0 -> unchanged. Rounded
        exactly as TranspositionEngine.transpose does. No second optical formula."""
        c = cyl or 0.0
        if c == 0:
            return round(sph, 2), 0.0, (axis or 0)
        new_axis = ((axis or 0) + 90) % 180
        if new_axis == 0:
            new_axis = 180
        return round(sph + c, 2), round(-c, 2), new_axis

    def _eye_forms(self, prescription: models.Prescription, eye: str):
        """Both optically equivalent representations for one eye, derived from
        the stored NORMALISED (minus-cyl) prescription. ADD is form-invariant."""
        if eye == "od":
            sph, cyl, axis, add = (prescription.od_sph, prescription.od_cyl,
                                   prescription.od_axis, prescription.od_add)
        else:
            sph, cyl, axis, add = (prescription.os_sph, prescription.os_cyl,
                                   prescription.os_axis, prescription.os_add)
        minus = (sph, cyl or 0.0, axis or 0, add)
        p_sph, p_cyl, p_axis = self._plus_form(sph, cyl, axis)
        return {"minus": minus, "plus": (p_sph, p_cyl, p_axis, add)}

    @staticmethod
    def _range_convention(power_range: models.PowerRange) -> str:
        """Which Rx form a PowerRange must be tested against, from its sign only
        (no cyl_convention field). 'minus' | 'plus' | 'both'."""
        # G3 "Total Sph+Cyl" clause is defined ONLY in the catalog's normalized
        # minus-cyl convention - it is always evaluated against the stored minus
        # form, never the plus form. This branch runs BEFORE the sign detection.
        if (getattr(power_range, "total_power_min", None) is not None
                or getattr(power_range, "total_power_max", None) is not None
                or getattr(power_range, "max_cyl_abs", None) is not None):
            # A signed single-total with a genuinely POSITIVE directional CYL
            # interval [0, +c] is written in PLUS-cyl notation - test it against
            # the transposed plus form, reusing the G1 plus-form machinery.
            # Unsigned single totals (max_cyl_abs set) and two-number / signed-
            # negative totals (cyl_max <= 0) stay on the stored minus form.
            if (getattr(power_range, "max_cyl_abs", None) is None
                    and getattr(power_range, "cyl_min", None) is not None
                    and getattr(power_range, "cyl_max", None) is not None
                    and power_range.cyl_min >= 0 and power_range.cyl_max > 0):
                return "plus"
            return "minus"
        lo, hi = power_range.cyl_min, power_range.cyl_max
        if lo == 0 and hi == 0:
            return "minus"                      # plano - minus form (cyl 0) is fine
        if hi <= 0:
            return "minus"                      # minus-cyl blank  [-c, 0]
        if lo >= 0:
            return "plus"                       # plus-cyl blank   [0, +c]
        return "both"                           # defensive zero-spanning range

    def _range_eye_sph(self, power_range: models.PowerRange,
                       prescription: models.Prescription, eye: str) -> float:
        """The eye's SPH in the representation this PowerRange is tested against
        (used for distance / score so SPH stays paired with its CYL form)."""
        forms = self._eye_forms(prescription, eye)
        conv = self._range_convention(power_range)
        return forms["plus"][0] if conv == "plus" else forms["minus"][0]

    def _check_form_against_range(self, power_range, form) -> list:
        sph, cyl, axis, add = form
        cyl_needed = cyl or 0.0
        issues = []
        if not (power_range.sph_min - self.tolerance_sph <= sph
                <= power_range.sph_max + self.tolerance_sph):
            issues.append(f"SPH {sph} خارج [{power_range.sph_min}, {power_range.sph_max}]")
        if not (power_range.cyl_min - self.tolerance_cyl <= cyl_needed
                <= power_range.cyl_max + self.tolerance_cyl):
            issues.append(f"CYL {cyl_needed} خارج [{power_range.cyl_min}, {power_range.cyl_max}]")
        if add and add > 0:
            if power_range.add_min is None or power_range.add_max is None:
                issues.append("لا يدعم ADD")
            elif not (power_range.add_min - self.tolerance_add <= add
                      <= power_range.add_max + self.tolerance_add):
                issues.append(f"ADD {add} خارج [{power_range.add_min}, {power_range.add_max}]")
        # high-SPH cylinder cap - evaluated with THIS form's sph/cyl together
        if (power_range.max_cyl_for_high_sph is not None
                and power_range.sph_threshold is not None
                and abs(sph) >= abs(power_range.sph_threshold)):
            if abs(cyl_needed) > abs(power_range.max_cyl_for_high_sph):
                issues.append(f"CYL محدود لـ SPH ≥ {power_range.sph_threshold}")
        # G3 authoritative constraint: the two PRINCIPAL MERIDIAN powers must sit
        # inside the total-power envelope, AND abs(CYL) <= max_cyl_abs. Evaluated
        # on the stored minus form (see _range_convention), where
        #   high_meridian = SPH,   low_meridian = SPH + CYL
        # The unordered meridian pair {SPH, SPH+CYL} is invariant under
        # plus/minus-cyl transposition, so an equivalent Rx entered in either
        # notation normalizes to the same pair and matches identically.
        # total_power_min bounds the LOW meridian; total_power_max bounds the
        # HIGH meridian. The sph/cyl box checks above are only a coarse prefilter
        # for G3 rows. This is a manufacturer HARD limit, not a fuzzy-matching
        # box - unlike the coarse checks above, it is evaluated with NO
        # tolerance: the boundary itself is inclusive, but nothing beyond it
        # passes, by even 0.01D.
        tp_min = getattr(power_range, "total_power_min", None)
        tp_max = getattr(power_range, "total_power_max", None)
        mca = getattr(power_range, "max_cyl_abs", None)
        if tp_min is not None or tp_max is not None:
            # convention-independent: the unordered meridian pair {SPH, SPH+CYL}
            # is transposition-invariant, so this is a no-op for a minus form
            # (cyl <= 0) and correct for a plus form (cyl >= 0).
            m1, m2 = sph, sph + cyl_needed
            low_meridian, high_meridian = min(m1, m2), max(m1, m2)
            if tp_min is not None and low_meridian < tp_min:
                issues.append(
                    f"low meridian {round(low_meridian, 2)} < total_power_min {tp_min}")
            if tp_max is not None and high_meridian > tp_max:
                issues.append(
                    f"high meridian {round(high_meridian, 2)} > total_power_max {tp_max}")
        if mca is not None:
            if abs(cyl_needed) > mca:
                issues.append(f"CYL magnitude {abs(cyl_needed)} > {mca}")
        return issues

    def check_power_range(
        self,
        power_range: models.PowerRange,
        prescription: models.Prescription,
        eye: str = "od"
    ) -> Tuple[bool, str]:
        """التحقق من نطاق القوة لعين واحدة.

        The prescription is compared in the representation that matches the
        PowerRange's cylinder sign - a plus-cyl range against the plus-cyl Rx
        form, a minus-cyl range against the stored minus form - so SPH, CYL and
        AXIS always move together. The catalog range is never transposed."""
        forms = self._eye_forms(prescription, eye)
        conv = self._range_convention(power_range)
        if conv == "both":
            m_issues = self._check_form_against_range(power_range, forms["minus"])
            if not m_issues:
                return True, "✓ مناسبة"
            p_issues = self._check_form_against_range(power_range, forms["plus"])
            return (not p_issues), ("✓ مناسبة" if not p_issues else "; ".join(p_issues))
        issues = self._check_form_against_range(power_range, forms[conv])
        return (len(issues) == 0), ("✓ مناسبة" if not issues else "; ".join(issues))

    def calculate_match_score(
        self,
        lens_model: models.LensModel,
        variant: models.LensVariant,
        pricing: models.VariantPricing,
        power_range: Optional[models.PowerRange],
        prescription: models.Prescription,
        filters: Optional[schemas.LensFilters] = None,
        prefer_stock: bool = True,
        prefer_aspherical: bool = True
    ) -> float:
        """حساب درجة المطابقة (0-100).

        Commercial inputs (availability, price) come ONLY from `pricing`
        (VariantPricing), never from the legacy LensVariant columns.
        `power_range` is None for RX made-to-order without an explicit range.
        """
        score = 0.0
        max_sph = max(abs(prescription.od_sph), abs(prescription.os_sph))
        max_cyl = max(abs(prescription.od_cyl or 0), abs(prescription.os_cyl or 0))

        # 1. دقة نطاق القوة (30%)
        if power_range is not None:
            sph_center = (power_range.sph_min + power_range.sph_max) / 2
            sph_range = power_range.sph_max - power_range.sph_min
            # SPH in the representation matching this range's cylinder sign
            od_dist = abs(self._range_eye_sph(power_range, prescription, "od") - sph_center)
            os_dist = abs(self._range_eye_sph(power_range, prescription, "os") - sph_center)
            avg_dist = (od_dist + os_dist) / 2
            power_score = max(0, 30 * (1 - avg_dist / (sph_range / 2))) if sph_range > 0 else (30 if avg_dist < 0.5 else 0)
        else:
            # RX made-to-order: no discrete range to score against
            power_score = 18.0
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

        # 4. التوفر (15%) - authoritative availability is on VariantPricing
        if prefer_stock:
            score += 15 if pricing.availability == models.PricingAvailability.STOCK else 8
        else:
            score += 15

        # 5. الميزات (10%)
        feature_score = 10
        if filters and filters.features:
            model_features = lens_model.features or []
            matched = sum(1 for f in filters.features if f in model_features)
            feature_score = (matched / len(filters.features)) * 10
        score += feature_score

        # 6. السعر (7%) - authoritative price is VariantPricing.price_pair (Decimal)
        if filters and filters.max_price is not None:
            score += 7 if pricing.price_pair <= Decimal(str(filters.max_price)) else 0
        else:
            score += 7

        # 7. الشركة (3%)
        if filters and filters.company_id:
            score += 3 if lens_model.company_id == filters.company_id else 0.5
        else:
            score += 3

        return min(100, max(0, round(score, 1)))

    # ----- helpers -------------------------------------------------------------
    def _best_matching_range(
        self, ranges: List[models.PowerRange], prescription: models.Prescription
    ) -> Optional[models.PowerRange]:
        """Return the covering PowerRange closest to the prescription, or None."""
        best = None
        best_dist = None
        for pr in ranges:
            od_valid, _ = self.check_power_range(pr, prescription, "od")
            os_valid, _ = self.check_power_range(pr, prescription, "os")
            if not (od_valid and os_valid):
                continue
            center = (pr.sph_min + pr.sph_max) / 2
            # distance uses the eye's SPH in the SAME representation the range
            # was tested against (plus-form SPH for a plus-cyl range).
            dist = (abs(self._range_eye_sph(pr, prescription, "od") - center)
                    + abs(self._range_eye_sph(pr, prescription, "os") - center))
            if best_dist is None or dist < best_dist:
                best, best_dist = pr, dist
        return best

    def _passes_commercial_and_optical_filters(
        self,
        variant: models.LensVariant,
        lens_model: models.LensModel,
        pricing: models.VariantPricing,
        filters: Optional[schemas.LensFilters],
    ) -> bool:
        if not filters:
            return True
        # optical / structural
        if filters.material and variant.material != filters.material:
            return False
        if filters.index_value and abs(variant.index_value - filters.index_value) > 0.01:
            return False
        if filters.min_index and variant.index_value < filters.min_index:
            return False
        if filters.max_index and variant.index_value > filters.max_index:
            return False
        if filters.design_type and variant.design_type != filters.design_type:
            return False
        if filters.prefer_aspherical and not variant.is_aspherical:
            return False
        if filters.category and lens_model.category != filters.category:
            return False
        if filters.company_id and lens_model.company_id != filters.company_id:
            return False
        # commercial -> VariantPricing only
        if filters.availability is not None and filters.availability != schemas.LensAvailability.BOTH:
            if pricing.availability.value != filters.availability.value:
                return False
        if filters.max_price is not None and pricing.price_pair > Decimal(str(filters.max_price)):
            return False
        if filters.coating:
            code = (pricing.coating.code if pricing.coating else "")
            if code.strip().lower() != filters.coating.strip().lower():
                return False
        if filters.market_scope:
            if _norm_scope(pricing.market_scope) != _norm_scope(filters.market_scope):
                return False
        return True

    def _current_pricing_candidates(
        self, db: Session, filters: Optional[schemas.LensFilters]
    ) -> List[models.VariantPricing]:
        """Every CURRENT (effective_to IS NULL) VariantPricing row on an active
        variant/model/company, eagerly loaded to avoid N+1."""
        query = (
            db.query(models.VariantPricing)
            .join(models.LensVariant, models.VariantPricing.variant_id == models.LensVariant.id)
            .join(models.LensModel, models.LensVariant.lens_model_id == models.LensModel.id)
            .join(models.Company, models.LensModel.company_id == models.Company.id)
            .filter(
                models.VariantPricing.effective_to.is_(None),   # CURRENT ONLY - never history
                models.LensVariant.is_active == True,
                models.LensModel.is_active == True,
                models.LensModel.is_deleted == False,
                models.Company.is_active == True,
                models.Company.is_deleted == False,
            )
            .options(
                joinedload(models.VariantPricing.variant)
                .joinedload(models.LensVariant.lens_model)
                .joinedload(models.LensModel.company),
                joinedload(models.VariantPricing.coating),
                selectinload(models.VariantPricing.power_ranges),
                joinedload(models.VariantPricing.variant)
                .selectinload(models.LensVariant.power_ranges),
                joinedload(models.VariantPricing.variant)
                .joinedload(models.LensVariant.lens_model)
                .selectinload(models.LensModel.variants),
                joinedload(models.VariantPricing.variant)
                .joinedload(models.LensVariant.lens_model)
                .selectinload(models.LensModel.power_ranges),
            )
        )
        if filters and filters.company_id:
            query = query.filter(models.LensModel.company_id == filters.company_id)
        return query.all()

    def match_lenses(
        self,
        db: Session,
        prescription: models.Prescription,
        filters: Optional[schemas.LensFilters] = None,
        prefer_stock: bool = True,
        prefer_aspherical: bool = True
    ) -> Tuple[List[schemas.LensMatchResult], int, int, str, str]:
        """
        مطابقة الوصفة - candidates come from CURRENT VariantPricing only.

        Returns: (results, stock_count, rx_count, index_rec, aspherical_rec)
        """
        max_sph = max(abs(prescription.od_sph), abs(prescription.os_sph))
        max_cyl = max(abs(prescription.od_cyl or 0), abs(prescription.os_cyl or 0))
        recommended_index, index_desc = self.recommender.recommend_index(max_sph)
        need_aspherical, aspherical_desc = self.recommender.recommend_aspherical(max_sph, max_cyl)

        # 1) gather (pricing, variant, model, matched_range, is_stock) candidates
        raw = []
        for pricing in self._current_pricing_candidates(db, filters):
            variant = pricing.variant
            if variant is None or not variant.is_active:
                continue
            lens_model = variant.lens_model
            if not self._passes_commercial_and_optical_filters(variant, lens_model, pricing, filters):
                continue

            own_ranges = list(pricing.power_ranges)          # ONLY ranges of THIS pricing row
            is_stock = pricing.availability == models.PricingAvailability.STOCK

            if is_stock:
                matched = self._best_matching_range(own_ranges, prescription)
                if matched is None:
                    continue                                  # STOCK needs its own covering range
                raw.append((pricing, variant, lens_model, matched, True))
            else:
                if own_ranges:
                    matched = self._best_matching_range(own_ranges, prescription)
                    if matched is None:
                        continue                              # RX with explicit limits that don't cover
                    raw.append((pricing, variant, lens_model, matched, False))
                else:
                    raw.append((pricing, variant, lens_model, None, False))   # RX made-to-order

        # 2) STOCK-over-RX suppression, grouped by (variant, coating, market_scope)
        stock_groups = {
            (p.variant_id, p.coating_id, _norm_scope(p.market_scope))
            for (p, _v, _m, _r, is_stock) in raw if is_stock
        }
        kept = [
            c for c in raw
            if c[4] or (c[0].variant_id, c[0].coating_id, _norm_scope(c[0].market_scope)) not in stock_groups
        ]

        # 2b) commercial deduplication. One customer-visible lens option may be
        # persisted as several CURRENT VariantPricing rows - one per power_scope
        # - because the catalog states it with multiple OR PowerRange clauses.
        # A prescription covered by more than one clause must yield ONE result,
        # not several identical rows. Runs AFTER STOCK-over-RX suppression and
        # BEFORE result construction/sort, so no availability semantics change.
        # Merge ONLY when every commercial dimension is identical; power_scope,
        # pricing.id and the matched PowerRange are matching routes, not
        # customer-distinct products. Survivor per group: highest match_score,
        # then a range-bearing candidate over a no-range one, then lowest
        # pricing.id (deterministic tie-break only).
        scored = [
            (c, self.calculate_match_score(
                c[2], c[1], c[0], c[3],
                prescription, filters, prefer_stock, prefer_aspherical))
            for c in kept
        ]
        _groups: dict = {}
        for c, sc in scored:
            pr = c[0]
            key = (
                c[2].id, c[1].id, pr.coating_id, pr.availability,
                _norm_scope(pr.market_scope), pr.price_pair, pr.currency,
            )
            _groups.setdefault(key, []).append((c, sc))
        deduped = [
            max(members, key=lambda cs: (
                cs[1],                                   # highest match_score
                1 if cs[0][3] is not None else 0,        # range-bearing wins a tie
                -cs[0][0].id,                            # then lowest pricing.id
            ))
            for members in _groups.values()
        ]

        # 3) build results
        results: List[schemas.LensMatchResult] = []
        for (pricing, variant, lens_model, matched_range, is_stock), score in deduped:
            reason = self._build_reason(
                lens_model, variant, pricing, matched_range, prescription, score,
                recommended_index, need_aspherical
            )
            results.append(schemas.LensMatchResult(
                lens_model=schemas.LensModelResponse.model_validate(lens_model),
                variant=schemas.LensVariantResponse.model_validate(variant),
                match_score=score,
                reason=reason,
                power_range=(
                    schemas.PowerRangeResponse.model_validate(matched_range)
                    if matched_range is not None else None
                ),
                is_recommended=score >= 60,
                index_recommended=abs(variant.index_value - recommended_index) < 0.1,
                aspherical_recommended=bool(variant.is_aspherical and need_aspherical),
                stock_available=is_stock,
                availability=pricing.availability.value,
                price_pair=pricing.price_pair,
                currency=pricing.currency,
                coating_id=pricing.coating_id,
                coating_code=(pricing.coating.code if pricing.coating else None),
                coating_name=(pricing.coating.name if pricing.coating else None),
                market_scope=pricing.market_scope,
                power_scope=pricing.power_scope,
                design_variant=variant.design_variant,
                color_variant=variant.color_variant,
                source_pricing_id=pricing.id,
                source_catalog_id=pricing.source_catalog_id,
            ))

        # 4) sort: optical quality, then STOCK before RX, then cheaper current price
        results.sort(key=lambda r: (-r.match_score, 0 if r.availability == "stock" else 1, r.price_pair))

        stock_count = sum(1 for r in results if r.availability == "stock")
        rx_count = sum(1 for r in results if r.availability == "rx")
        return results, stock_count, rx_count, index_desc, aspherical_desc

    def _build_reason(self, lens_model, variant, pricing, power_range, prescription, score,
                      rec_index, need_aspherical):
        """بناء رسالة توصية - commercial facts come from `pricing` (VariantPricing)."""
        reasons = []

        if score >= 90:
            reasons.append("⭐ مطابقة ممتازة")
        elif score >= 75:
            reasons.append("✓ مطابقة جيدة جداً")
        elif score >= 60:
            reasons.append("✓ مطابقة مقبولة")

        if abs(variant.index_value - rec_index) < 0.1:
            reasons.append(f"Index {variant.index_value} مثالي")

        if variant.is_aspherical and need_aspherical:
            reasons.append("✓ Aspherical للقوة العالية")

        # commercial design / colour lines
        if variant.design_variant:
            reasons.append(f"تصميم: {variant.design_variant}")
        if variant.color_variant:
            reasons.append(f"لون: {variant.color_variant}")

        # availability - authoritative from VariantPricing
        if pricing.availability == models.PricingAvailability.STOCK:
            if power_range is not None:
                reasons.append(
                    f"📦 STOCK ضمن النطاق [{power_range.sph_min}, {power_range.sph_max}]"
                )
            else:
                reasons.append("📦 STOCK")
        else:
            reasons.append("⏱ RX - يحتاج تصنيع")

        # coating
        if pricing.coating is not None:
            reasons.append(f"طلاء: {pricing.coating.name}")

        # market
        if pricing.market_scope:
            reasons.append(f"سوق: {pricing.market_scope}")

        # price - VariantPricing.price_pair (Decimal), never LensVariant.price
        reasons.append(f"السعر: {pricing.price_pair} {pricing.currency} / زوج")

        features = lens_model.features or []
        if features:
            feature_names = {
                "anti_reflective": "AR",
                "photochromic": "Photo",
                "blue_light_filter": "Blue Light",
                "uv_protection": "UV",
            }
            feature_list = [feature_names.get(f, f) for f in features[:3]]
            reasons.append(f"ميزات: {', '.join(feature_list)}")

        return " | ".join(filter(None, reasons))


# instance
lens_matcher = LensMatcherFinal()
