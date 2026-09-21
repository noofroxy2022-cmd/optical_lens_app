"""Seller needs, separate from manufacturer terminology. Exact evidence only.

Blue/photo reuse the audited V1.2 registry, including its priced add-on scope.
Additional entries are SCOPE.pdf printed row identities reconciled in
tests/test_scope_import.py ROW26 (R05, R12/13/21/22, R23/24/25, R26).
They describe catalog capabilities, never clinical benefit or certification.
No inference from material enum, index alone, brand substring or frame type.
"""
import math

# Explicit business evidence supplied for V1.4.1. This does not classify other
# manufacturers as foreign, and does not impose an order between these two.
LOCAL_EGYPT_MANUFACTURERS = frozenset({"SCOPE", "PLATINUM"})


def local_manufacturing(result):
    # CENTRALIZED (owner-confirmed HAT fix, 2026-09-21): a company/manufacturing
    # identity, not a subtype rule. LOCAL_EGYPT_MANUFACTURERS (SCOPE, PLATINUM)
    # are Egyptian manufacturers - every RX/manufactured lens of theirs, in
    # every category (progressive, bifocal, anti_fatigue, myopia_control,
    # office, digital, single_vision, and any future category), is
    # manufactured inside Egypt. Earlier revisions gated this on an explicit
    # category tuple ("progressive", "bifocal", then "anti_fatigue" added
    # 2026-09-21) that had to be hand-extended every time a new RX-eligible
    # category was introduced - that was the root cause of SCOPE Myopia
    # Control (and, before that, Young/Anti-Fatigue) rows silently missing
    # manufacturing_location="egypt". The category tuple is gone; this is now
    # the single source of truth both UI grouping (product_search.py) and
    # seller_order() below consume, so they can never drift apart again.
    return (result.pair_fulfillment.status == "rx"
            and result.company_name in LOCAL_EGYPT_MANUFACTURERS)


def seller_order(result):
    """Called only after actionable(): availability, price, then score."""
    status = result.pair_fulfillment.status
    base = {"stock_egypt": 0, "stock_outside": 1, "rx": 2}[status]
    # Sub-tier only matters within the RX base tier (local_manufacturing()
    # already requires status == "rx", so it is always False - a fixed,
    # order-neutral constant - for stock rows).
    sub = 0 if local_manufacturing(result) else 1
    return base, sub, result.pair_fulfillment.price_pair, -float(result.match_score)

TECHNOLOGY = {
    "screens_blue_light": "blue_light",
    "photochromic_gray": "photo_gray",
    "photochromic_brown": "photo_brown",
    # RECONCILED (Catalog Truth Audit, 2026-09-18, Section G item 3): defers
    # entirely to technology_evidence's single central impact-resistance rule
    # (proven_capabilities), instead of the SCOPE-only gate this need used to
    # get via `proves()`/SCOPE_ROWS below - that hardcoded gate blocked even
    # HOYA's already-proven PNX-1.53 lenses from ever satisfying this need.
    "high_impact_resistance": "impact_resistant",
}
LABELS = {
    "none": "بدون احتياج إضافي",
    "screens_blue_light": "الشاشات / ترشيح الضوء الأزرق",
    "photochromic_gray": "فوتوكروميك رمادي",
    "photochromic_brown": "فوتوكروميك بني",
    "driving": "القيادة",
    "sun": "الشمس",
    "thinner_lens": "عدسة رقيقة حسب وصف الكتالوج",
    "high_impact_resistance": "مقاومة الصدمات حسب الكتالوج",
    "best_optical_clarity": "أفضل نقاء بصري",
}
SCOPE_ROWS = {
    "driving": {"Night Rider (Blue+Yellow Light, Day/Night Driving)"},
    "sun": {"Sun Gray", "Sun Gray with Revo Mirror (Blue/Silver/Gold)",
            "Sun Polarized Gray-Brown-Green"},
    "thinner_lens": {"Non Water-Tintable Thin"},
}


def proves(need, company, treatment):
    if need in (None, "none") or need in TECHNOLOGY:
        return True  # technology gate runs separately, on the fulfilling route
    return company == "SCOPE" and treatment in SCOPE_ROWS.get(need, set())


def valid_rx(prescription):
    for eye in ("od", "os"):
        sph = getattr(prescription, eye + "_sph", None)
        cyl = getattr(prescription, eye + "_cyl", None)
        axis = getattr(prescription, eye + "_axis", None)
        add = getattr(prescription, eye + "_add", None)
        if sph is None or not math.isfinite(sph):
            return False
        if cyl is not None and not math.isfinite(cyl):
            return False
        if axis is not None and (not math.isfinite(axis) or not 0 <= axis <= 180):
            return False
        if cyl and axis is None:
            return False
        if add is not None and (not math.isfinite(add) or add < 0):
            return False
    return True


def actionable(result):
    pf = result.pair_fulfillment
    return (pf.status in ("stock_egypt", "stock_outside", "rx")
            and pf.provenance == "single_route" and bool(pf.source_pricing_ids)
            and not pf.needs_review and not pf.price_confirmation_note
            and pf.price_pair is not None and pf.price_pair.is_finite()
            and pf.price_pair > 0 and bool(pf.currency))


def seller_reason(result, need, technology):
    pf = result.pair_fulfillment
    route = {"stock_egypt": "STOCK مصر حسب الكتالوج",
             "stock_outside": "STOCK خارج مصر حسب الكتالوج", "rx": "متاح للتصنيع RX"}[pf.status]
    if local_manufacturing(result):
        route = "تصنيع داخل مصر"
    bits = ["متوافق مع وصفة العينين", route]
    if need and need != "none":
        bits.append("احتياج مثبت: " + LABELS[need])
    if technology and technology != "none":
        evidence = pf.technology_addon.label if pf.technology_addon else " / ".join(
            x for x in (result.coating_name, result.treatment_band, result.color_variant) if x)
        bits.append("تقنية مثبتة: " + evidence)
    elif need in SCOPE_ROWS:
        bits.append(result.treatment_band)
    bits.append(f"سعر الزوج النهائي {pf.price_pair} {pf.currency}")
    bits.append(f"Index {result.index_value:g}")
    if result.design_variant:
        bits.append(result.design_variant)
    return "؛ ".join(bits)
