"""V1.0.2 product-search layer.

Two things sit on top of the FROZEN optical matcher (`lens_matcher`), which is
never modified and whose eligibility maths / match_score are reused verbatim:

  1. V1.0.1 - two search modes, strict targeted AND filters, availability-first
     grouping, a direct availability answer, a SEPARATE alternatives list.

  2. V1.0.2 - for every exact commercial option, evaluate OD and OS
     INDEPENDENTLY against each pricing route (STOCK Egypt / STOCK Out Of Egypt
     / RX), then decide the best VERIFIED way to fulfill the PAIR:
        - a tier qualifies only when BOTH eyes are covered by the SAME
          commercial option at that tier;
        - a pair price is shown ONLY when one proven VariantPricing route (or
          same-identity/same-tier OR-clause rows carrying one identical catalog
          pair price) covers BOTH eyes - never /2, never half+half, never
          STOCK+RX, never estimated;
        - otherwise the pair is `split` (both eyes sourceable separately, no
          proven mixed price) or `unavailable` (an eye has no route at all).

  Per-eye eligibility calls `lens_matcher.check_power_range(pr, prescription,
  eye)` directly - the existing G1/G2/G3 / transposition / principal-meridian /
  RX-range logic, one eye at a time. Nothing optical is re-implemented here.
"""
from typing import List, Optional, Tuple, Dict
from decimal import Decimal

from sqlalchemy.orm import Session

from app import schemas, models
from app.lens_matcher import lens_matcher

_RX = models.PricingAvailability.RX
_STOCK = models.PricingAvailability.STOCK
_TIERS = ("stock_egypt", "stock_outside", "rx")


# ---------------------------------------------------------------- market / tier
def _norm(v: Optional[str]) -> str:
    return (v or "").strip().lower()


def market_is_egypt(market_scope: Optional[str]) -> Optional[bool]:
    """True = Egypt, False = a named non-Egypt market, None = unspecified."""
    s = _norm(market_scope)
    if not s:
        return None
    if "out" in s and "egypt" in s:
        return False
    if s in ("egypt", "eg", "مصر"):
        return True
    if "egypt" in s:
        return True
    return False


def _row_route(p: models.VariantPricing) -> str:
    if p.availability == _STOCK:
        return "stock_egypt" if market_is_egypt(p.market_scope) is True else "stock_outside"
    return "rx"


# ------------------------------------------------------- V1.0.1 alternatives bits
def result_tier(r: schemas.LensMatchResult) -> int:
    if r.availability == "stock":
        return 0 if market_is_egypt(r.market_scope) is True else 1
    return 2


def _family_token(name: Optional[str]) -> str:
    return _norm((name or "").split()[0]) if name else ""


def _alt_scored(r: schemas.LensMatchResult, f: schemas.LensFilters,
                ref_family: str) -> Tuple[int, List[str], str]:
    score = 0
    matches: List[str] = []
    relaxed: List[str] = []
    if f.company_id is not None:
        if r.lens_model.company_id == f.company_id:
            score += 3; matches.append("نفس الشركة")
        else:
            relaxed.append("الشركة")
    if f.lens_model_id is not None:
        if r.lens_model.id == f.lens_model_id:
            score += 4; matches.append("نفس المنتج")
        else:
            relaxed.append("المنتج/الموديل")
            if ref_family and _family_token(r.lens_model.name) == ref_family:
                score += 2; matches.append("نفس العائلة")
    if f.index_value is not None:
        if abs(r.variant.index_value - f.index_value) <= 0.01:
            score += 3; matches.append(f"نفس Index {f.index_value}")
        else:
            relaxed.append(f"Index {f.index_value}")
    if f.category is not None:
        if r.lens_model.category == f.category:
            score += 2; matches.append("نفس الفئة")
        else:
            relaxed.append("الفئة")
    if f.coating:
        if _norm(f.coating) == _norm(r.coating_code):
            score += 3; matches.append("نفس الطلاء")
        else:
            relaxed.append(f"الطلاء ({f.coating})")
    if f.color_variant:
        if _norm(f.color_variant) in _norm(r.color_variant or r.variant.color_variant):
            score += 3; matches.append("نفس التقنية/اللون")
        else:
            relaxed.append(f"التقنية/اللون ({f.color_variant})")
    if f.design_variant:
        if _norm(f.design_variant) in _norm(r.design_variant or r.variant.design_variant):
            score += 1; matches.append("نفس التصميم")
        else:
            relaxed.append(f"التصميم ({f.design_variant})")
    if f.max_price is not None:
        if r.price_pair <= Decimal(str(f.max_price)):
            score += 1
        else:
            relaxed.append(f"السعر ≤ {f.max_price}")
    if f.availability is not None and getattr(f.availability, "value", f.availability) != "both":
        want = getattr(f.availability, "value", f.availability)
        if r.availability != want:
            relaxed.append(f"التوفر ({want.upper()})")
        else:
            score += 1
    if f.market_scope:
        want_eg = market_is_egypt(f.market_scope)
        if market_is_egypt(r.market_scope) != want_eg:
            relaxed.append("السوق (مصر)" if want_eg else "السوق (خارج مصر)")
        else:
            score += 1
    score += (2 - result_tier(r))
    reason = "، ".join(matches) if matches else "أقرب بديل متوافق مع الوصفة"
    return score, relaxed, reason


def _proven_eligible_for_alternatives(
    db: Session, all_results: List[schemas.LensMatchResult], prescription: models.Prescription,
    applicability_key: Optional[str] = None,
) -> List[schemas.LensMatchResult]:
    """Phase 3C safety gate: alternatives must be prescription-safe too. A
    candidate is only a USABLE alternative when its underlying VariantPricing
    row is PROVEN eligible for BOTH eyes - reusing the exact same tri-state
    `_row_eye_status` the exact per-eye/pair path already uses (no new optical
    logic, no lens_matcher.py change).

    The frozen matcher's own `match_lenses()` has no concept of
    power_eligibility: a row with no PowerRange and availability=RX is always
    returned as "eligible" by its long-standing "made-to-order = any power"
    rule, even when power_eligibility=UNRESOLVED (e.g. a ZEISS catalog price
    whose real limits are not yet modeled). Filtering happens HERE, after the
    frozen matcher runs and before compute_alternatives() ever sees the
    candidate - "ineligible" and "unknown" are both excluded; only "eligible"
    passes."""
    ids = {r.source_pricing_id for r in all_results}
    if not ids:
        return all_results
    rows = {
        vp.id: vp
        for vp in db.query(models.VariantPricing)
        .filter(models.VariantPricing.id.in_(ids))
        .all()
    }
    out = []
    for r in all_results:
        vp = rows.get(r.source_pricing_id)
        if vp is None:
            continue  # defensive: row vanished between the match and this lookup
        if (_row_eye_status(vp, prescription, "od", applicability_key) == "eligible"
                and _row_eye_status(vp, prescription, "os", applicability_key) == "eligible"):
            out.append(r)
    return out


def compute_alternatives(all_results: List[schemas.LensMatchResult], exact_ids: set,
                         f: schemas.LensFilters, limit: int = 15) -> List[schemas.AlternativeResult]:
    ref_family = ""
    if f.lens_model_id is not None:
        for r in all_results:
            if r.lens_model.id == f.lens_model_id:
                ref_family = _family_token(r.lens_model.name)
                break
    alts: List[schemas.AlternativeResult] = []
    for r in all_results:
        if r.source_pricing_id in exact_ids:
            continue
        score, relaxed, reason = _alt_scored(r, f, ref_family)
        alts.append(schemas.AlternativeResult(
            result=r, relaxed_filters=relaxed, proximity_reason=reason, proximity_score=score))
    alts.sort(key=lambda a: (-a.proximity_score, result_tier(a.result),
                             -float(a.result.match_score), Decimal(str(a.result.price_pair))))
    return alts[:limit]


# ---------------------------------------------------------------- per-eye engine
_UNRESOLVED = models.PowerEligibilityStatus.UNRESOLVED


def _applicable_ranges(p: models.VariantPricing, applicability_key: Optional[str]):
    """The PowerRange rows of `p` that an explicit subtype filter leaves in
    play. `applicability_key=None` (the default, and the ONLY case for every
    manufacturer that never splits one price into optical sub-options) never
    filters anything - full backward compatibility.

    When a caller DOES ask for one specific sub-option (e.g. "POL"):
      - if this row genuinely offers that sub-option (some range carries that
        exact key), narrow to just those ranges - the other sub-option's
        range(s) must never be consulted for this eye.
      - if this row is split into sub-options but NONE of them is the one
        requested, there is nothing to evaluate for the requested subtype -
        return an empty list (the caller then correctly reports ineligible,
        never falling back to "no range -> any power").
      - if this row was never split at all (no ranges, or every range has
        applicability_key=None), the filter simply does not apply to it -
        return the ranges unchanged so ordinary (non-ZEISS-split) rows are
        completely unaffected by a filter that has no meaning for them.
    """
    ranges = list(p.power_ranges)
    if applicability_key is None:
        return ranges
    keys_present = {pr.applicability_key for pr in ranges}
    if keys_present in (set(), {None}):
        return ranges   # never split - filter not applicable, unchanged
    return [pr for pr in ranges if pr.applicability_key == applicability_key]


def _row_eye_status(p: models.VariantPricing, prescription: models.Prescription, eye: str,
                    applicability_key: Optional[str] = None) -> str:
    """Tri-state optical eligibility of ONE pricing row for ONE eye:
    "eligible" | "ineligible" | "unknown".

    A row WITH explicit PowerRange(s) is always checked normally: any covering
    OR-range -> eligible, else ineligible - `power_eligibility` is irrelevant
    once a real range exists. A row with NO PowerRange falls back to the
    frozen matcher's long-standing "RX made-to-order = any power" rule ONLY
    when `power_eligibility` is UNRESTRICTED (the catalog genuinely states no
    restriction, or predates Phase 3 and defaults there). When it is
    UNRESOLVED - the catalog's real power limits are simply not modeled yet -
    eligibility is UNKNOWN, never silently True.

    `applicability_key`, when given, restricts evaluation to that one optical
    sub-option's range(s) only - see _applicable_ranges."""
    ranges = _applicable_ranges(p, applicability_key)
    if ranges:
        ok = any(lens_matcher.check_power_range(pr, prescription, eye)[0] for pr in ranges)
        return "eligible" if ok else "ineligible"
    if list(p.power_ranges):
        return "ineligible"       # split row that doesn't offer the requested subtype at all
    if p.availability != _RX:
        return "ineligible"       # STOCK with no range is not a real commercial row
    if getattr(p, "power_eligibility", None) == _UNRESOLVED:
        return "unknown"
    return "eligible"              # genuinely unrestricted RX made-to-order


def _row_covers_eye(p: models.VariantPricing, prescription: models.Prescription, eye: str,
                    applicability_key: Optional[str] = None) -> bool:
    """Backward-compatible boolean view: True only for a PROVEN-eligible row."""
    return _row_eye_status(p, prescription, eye, applicability_key) == "eligible"


def _row_eye_proving_keys(p: models.VariantPricing, prescription: models.Prescription,
                          eye: str, applicability_key: Optional[str] = None) -> frozenset:
    """Which PowerRange.applicability_key value(s) prove this eye eligible for
    this ONE pricing row - None for an ordinary undifferentiated range (the
    overwhelming majority: HOYA, and every non-split ZEISS row). A row can
    carry MULTIPLE optically distinct sub-options under one price (e.g.
    ZEISS's single-priced "Polarized / AdaptiveSun" offer, whose POL and
    AdaptiveSun PowerRanges differ) - this reports exactly which of them this
    eye's Rx actually satisfies, so pair-fulfillment can require the SAME
    sub-option on both eyes rather than silently letting one eye's POL match
    and the other eye's AdaptiveSun match count as "the same offer covers
    both". Empty frozenset = not proven eligible via any range on this row.

    A row with NO PowerRange at all (the ordinary RX-made-to-order / STOCK-
    with-no-explicit-range shape most HOYA rows use) has no range to report
    a key for, but IS eligible via _row_eye_status's existing fallback -
    that case reports {None} (the universal "no sub-option" key) rather
    than an empty set, so it still intersects correctly against the same
    row's other eye and against any other undifferentiated (key=None) row.

    `applicability_key`, when given, restricts consideration to that one
    sub-option, exactly like _row_eye_status."""
    ranges = _applicable_ranges(p, applicability_key)
    if not ranges:
        if list(p.power_ranges):
            return frozenset()   # split row, requested subtype not offered here
        return frozenset({None}) if _row_eye_status(p, prescription, eye) == "eligible" else frozenset()
    return frozenset(
        pr.applicability_key
        for pr in ranges
        if lens_matcher.check_power_range(pr, prescription, eye)[0]
    )


def _route_eye_status(rows: List[models.VariantPricing], prescription: models.Prescription,
                      eye: str, applicability_key: Optional[str] = None) -> str:
    """Tri-state aggregation across every row of one route for one eye:
    "eligible" if ANY row is proven eligible (an eligible row always wins over
    an unknown one elsewhere in the same route); else "unknown" if ANY row is
    unresolved; else "ineligible"."""
    statuses = [_row_eye_status(p, prescription, eye, applicability_key) for p in rows]
    if any(s == "eligible" for s in statuses):
        return "eligible"
    if any(s == "unknown" for s in statuses):
        return "unknown"
    return "ineligible"


def _route_covers_eye(rows: List[models.VariantPricing], prescription: models.Prescription,
                      eye: str, applicability_key: Optional[str] = None) -> bool:
    return _route_eye_status(rows, prescription, eye, applicability_key) == "eligible"


def _eye_availability(routes: Dict[str, List[models.VariantPricing]],
                      prescription: models.Prescription, eye: str,
                      applicability_key: Optional[str] = None) -> schemas.EyeAvailability:
    se = _route_eye_status(routes["stock_egypt"], prescription, eye, applicability_key)
    so = _route_eye_status(routes["stock_outside"], prescription, eye, applicability_key)
    rx = _route_eye_status(routes["rx"], prescription, eye, applicability_key)
    best = ("stock_egypt" if se == "eligible" else
            "stock_outside" if so == "eligible" else
            "rx" if rx == "eligible" else
            "unknown" if "unknown" in (se, so, rx) else "none")
    return schemas.EyeAvailability(
        stock_egypt=(se == "eligible"), stock_outside=(so == "eligible"), rx=(rx == "eligible"),
        stock_egypt_unknown=(se == "unknown"), stock_outside_unknown=(so == "unknown"),
        rx_unknown=(rx == "unknown"), best=best)


def _same_pricing_offer(a: models.VariantPricing, b: models.VariantPricing) -> bool:
    """Proven (from persistence) to be OR-clause rows of ONE catalog pricing
    offer: same source extraction line AND same catalog AND identical commercial
    facets. Distinct source_extraction_id => two separate catalog lines that only
    happen to match; NOT provable as one offer."""
    if a.id == b.id:
        return True
    return (a.source_extraction_id is not None
            and a.source_extraction_id == b.source_extraction_id
            and a.source_catalog_id == b.source_catalog_id
            and a.variant_id == b.variant_id
            and a.coating_id == b.coating_id
            and a.availability == b.availability
            and _norm(a.market_scope) == _norm(b.market_scope)
            and a.price_pair == b.price_pair
            and a.currency == b.currency)


def _pair_fulfillment(routes: Dict[str, List[models.VariantPricing]],
                      od: schemas.EyeAvailability, os_: schemas.EyeAvailability,
                      prescription: models.Prescription,
                      applicability_key: Optional[str] = None) -> schemas.PairFulfillment:
    od_ok = {"stock_egypt": od.stock_egypt, "stock_outside": od.stock_outside, "rx": od.rx}
    os_ok = {"stock_egypt": os_.stock_egypt, "stock_outside": os_.stock_outside, "rx": os_.rx}
    tier_label = {"stock_egypt": "STOCK داخل مصر", "stock_outside": "STOCK خارج مصر", "rx": "RX / تصنيع"}

    for tier in _TIERS:
        if not (od_ok[tier] and os_ok[tier]):
            continue
        rows = routes[tier]
        od_rows = [p for p in rows if _row_covers_eye(p, prescription, "od", applicability_key)]
        os_rows = [p for p in rows if _row_covers_eye(p, prescription, "os", applicability_key)]

        # (a) ONE VariantPricing row (its OR PowerRanges) covers BOTH eyes -> a
        #     single proven pricing route. Its catalog pair price stands -
        #     PROVIDED both eyes are proven via the SAME optical sub-option
        #     when the row carries more than one (applicability_key). A row
        #     with only undifferentiated ranges (every key None) always
        #     matches here unchanged; one whose OD proof and OS proof come
        #     from DIFFERENT non-overlapping sub-options (e.g. OD via "POL",
        #     OS via "AdaptiveSun" under one "Polarized / AdaptiveSun" offer)
        #     must NOT be treated as proving this row for the pair. An
        #     explicit applicability_key filter narrows BOTH eyes to that one
        #     sub-option from the start (via od_rows/os_rows above), so the
        #     intersection here is naturally restricted to it already.
        both = None
        proving_key = None
        for p in od_rows:
            if not _row_covers_eye(p, prescription, "os", applicability_key):
                continue
            common = (_row_eye_proving_keys(p, prescription, "od", applicability_key)
                     & _row_eye_proving_keys(p, prescription, "os", applicability_key))
            if common:
                both, proving_key = p, next(iter(common - {None}), None)
                break
        if both is not None:
            subtype_note = f" (subtype: {proving_key})" if proving_key else ""
            return schemas.PairFulfillment(
                status=tier, price_pair=both.price_pair, currency=both.currency,
                source_pricing_ids=[both.id], provenance="single_route", needs_review=False,
                reason=f"مسار تسعير واحد يغطي العينين ({tier_label[tier]}){subtype_note} — سعر الزوج من الكتالوج.",
                applicability_key=proving_key)

        # (a2) OD and OS covered by DIFFERENT rows, but a proven OR-clause pair of
        #      ONE catalog pricing offer (same source_extraction_id + facets) -
        #      same same-sub-option discipline as (a).
        proven = None
        proving_key = None
        for a in od_rows:
            for b in os_rows:
                if a.id == b.id or not _same_pricing_offer(a, b):
                    continue
                common = (_row_eye_proving_keys(a, prescription, "od", applicability_key)
                         & _row_eye_proving_keys(b, prescription, "os", applicability_key))
                if common:
                    proven, proving_key = (a, b), next(iter(common - {None}), None)
                    break
            if proven:
                break
        if proven is not None:
            a, b = proven
            subtype_note = f" (subtype: {proving_key})" if proving_key else ""
            return schemas.PairFulfillment(
                status=tier, price_pair=a.price_pair, currency=a.currency,
                source_pricing_ids=sorted({a.id, b.id}), provenance="single_route",
                needs_review=False,
                reason=(f"عرض تسعير واحد بعدة مدى قوة (OR) يغطي العينين ({tier_label[tier]})"
                        f"{subtype_note} — سعر الزوج من الكتالوج."),
                applicability_key=proving_key)

        # (b) both eyes at this tier, but via SEPARATE VariantPricing rows whose
        #     belonging to one catalog offer cannot be proven -> NO pair price.
        ids = sorted({p.id for p in od_rows} | {p.id for p in os_rows})
        return schemas.PairFulfillment(
            status=tier, price_pair=None, currency=None,
            source_pricing_ids=ids, provenance="unproven_mixed", needs_review=True,
            reason=(f"العينان متاحتان ضمن {tier_label[tier]} لكن عبر صفوف تسعير منفصلة "
                    f"لنفس المنتج؛ لا يمكن إثبات أنها نفس عرض السعر الواحد — سعر الزوج غير "
                    f"مثبت (unproven mixed pricing provenance). يحتاج مراجعة."))

    # No tier has BOTH eyes PROVEN eligible. If either eye's optical eligibility
    # is itself unresolved (not proven ineligible - simply unproven, e.g. a
    # ZEISS grid price whose real catalog power limits are not modeled yet),
    # the pair must NEVER be reported as a proven STOCK/RX route just because
    # nothing was disproven either. Checked BEFORE the split/unavailable
    # fallback, which must stay based on PROVEN eligibility only.
    if od.best == "unknown" or os_.best == "unknown":
        unresolved_ids = sorted({
            p.id for tier in _TIERS for p in routes[tier]
            if _row_eye_status(p, prescription, "od", applicability_key) == "unknown"
            or _row_eye_status(p, prescription, "os", applicability_key) == "unknown"
        })
        return schemas.PairFulfillment(
            status="eligibility_unknown", price_pair=None, currency=None,
            source_pricing_ids=unresolved_ids, provenance="none", needs_review=True,
            reason="المنتج موجود في الكتالوج، لكن توافقه مع هذه الوصفة غير مؤكد بسبب نطاق القوة.")

    # no single tier covers both eyes, and neither eye is unresolved -> the
    # existing proven split/unavailable logic, unchanged.
    od_any = od.stock_egypt or od.stock_outside or od.rx
    os_any = os_.stock_egypt or os_.stock_outside or os_.rx
    if od_any and os_any:
        return schemas.PairFulfillment(
            status="split", price_pair=None, currency=None, source_pricing_ids=[],
            provenance="none", needs_review=False,
            reason=("يمكن توفير العينين من مصدرين مختلفين، لكن سعر الزوج المختلط غير مثبت "
                    "في الكتالوج."))
    missing = "العين اليمنى (OD)" if not od_any else "العين اليسرى (OS)"
    if not od_any and not os_any:
        missing = "كلتا العينين"
    return schemas.PairFulfillment(
        status="unavailable", price_pair=None, currency=None, source_pricing_ids=[],
        provenance="none", needs_review=False,
        reason=f"{missing} غير متوافقة مع أي مسار متوفر لهذا المنتج في الكتالوج الحالي.")


# --------------------------------------------------- commercial-option gathering
_IDENTITY_EXTRA = ("lens_model_id", "design_variant", "color_variant",
                   "design_tier", "treatment_band")


def _probe_filters(f: Optional[schemas.LensFilters]) -> Optional[schemas.LensFilters]:
    """What the matcher's own candidate gather / native-filter check sees: the
    identity dimensions it already understands, WITHOUT availability / market /
    max_price / the V1.0.2-only dims (those are applied afterwards so the full
    OD/OS/tier matrix stays visible)."""
    if f is None:
        return None
    data = f.model_dump()
    for k in ("availability", "market_scope", "max_price", *_IDENTITY_EXTRA):
        data[k] = None
    return schemas.LensFilters(**data)


def _passes_extra_identity(variant: models.LensVariant, f: schemas.LensFilters) -> bool:
    if f.lens_model_id is not None and variant.lens_model_id != f.lens_model_id:
        return False
    if f.design_variant and _norm(f.design_variant) not in _norm(variant.design_variant):
        return False
    if f.color_variant and _norm(f.color_variant) not in _norm(variant.color_variant):
        return False
    if f.design_tier and _norm(f.design_tier) not in _norm(variant.design_tier):
        return False
    if f.treatment_band and _norm(f.treatment_band) not in _norm(variant.treatment_band):
        return False
    return True


def _identity_key(p: models.VariantPricing):
    v = p.variant
    m = v.lens_model
    return (m.company_id, m.id, v.id, round(v.index_value, 3),
            getattr(v.material, "value", v.material),
            getattr(m.category, "value", m.category),
            _norm(v.design_variant), _norm(v.color_variant),
            _norm(v.design_tier), _norm(v.treatment_band),
            p.coating_id, p.currency)


def _per_eye_results(db: Session, prescription: models.Prescription,
                     filters: Optional[schemas.LensFilters], req: schemas.ProductSearchRequest,
                     rec_index: float, need_asph: bool,
                     ) -> List[schemas.PerEyeProductResult]:
    probe = _probe_filters(filters)
    rows = lens_matcher._current_pricing_candidates(db, probe)

    groups: Dict[tuple, List[models.VariantPricing]] = {}
    for p in rows:
        v = p.variant
        if v is None or not v.is_active:
            continue
        m = v.lens_model
        if probe is not None and not lens_matcher._passes_commercial_and_optical_filters(v, m, p, probe):
            continue
        if filters is not None and not _passes_extra_identity(v, filters):
            continue
        groups.setdefault(_identity_key(p), []).append(p)

    out: List[schemas.PerEyeProductResult] = []
    want_specific_product = bool(filters and filters.lens_model_id is not None)
    for _key, opt_rows in groups.items():
        routes = {
            "stock_egypt": [p for p in opt_rows if _row_route(p) == "stock_egypt"],
            "stock_outside": [p for p in opt_rows if _row_route(p) == "stock_outside"],
            "rx": [p for p in opt_rows if _row_route(p) == "rx"],
        }
        applicability_key = filters.applicability_key if filters else None
        od = _eye_availability(routes, prescription, "od", applicability_key)
        os_ = _eye_availability(routes, prescription, "os", applicability_key)
        pf = _pair_fulfillment(routes, od, os_, prescription, applicability_key)

        if pf.status == "unavailable" and not want_specific_product:
            continue  # automatic / non-specific: drop options no eye combo can use

        sample = opt_rows[0]
        v = sample.variant
        m = v.lens_model
        # score: reuse the frozen calculator on the fulfilling route's row + a
        # covering range (falls back to a representative row for split/unavailable)
        score_row = None
        if pf.source_pricing_ids:
            score_row = next((p for p in opt_rows if p.id in pf.source_pricing_ids), None)
        if score_row is None:
            score_row = (routes["stock_egypt"] or routes["stock_outside"]
                         or routes["rx"] or opt_rows)[0]
        score_range = lens_matcher._best_matching_range(list(score_row.power_ranges), prescription)
        score = lens_matcher.calculate_match_score(
            m, v, score_row, score_range, prescription, filters,
            req.prefer_stock, req.prefer_aspherical)

        bits = [f"الزوج: {_STATUS_AR.get(pf.status, pf.status)}",
                f"OD: {_EYEBEST_AR[od.best]}", f"OS: {_EYEBEST_AR[os_.best]}"]
        if abs(v.index_value - rec_index) < 0.1:
            bits.append(f"Index {v.index_value} مثالي")
        if v.is_aspherical and need_asph:
            bits.append("Aspherical مناسب")

        out.append(schemas.PerEyeProductResult(
            company_id=m.company_id, company_name=(m.company.name if m.company else None),
            lens_model_id=m.id, model_name=m.name,
            category=getattr(m.category, "value", m.category),
            variant_id=v.id, index_value=v.index_value,
            material=getattr(v.material, "value", v.material),
            design_variant=v.design_variant, color_variant=v.color_variant,
            design_tier=v.design_tier, treatment_band=v.treatment_band,
            coating_id=sample.coating_id,
            coating_code=(sample.coating.code if sample.coating else None),
            coating_name=(sample.coating.name if sample.coating else None),
            currency=sample.currency, match_score=score, reason=" | ".join(bits),
            od=od, os=os_, pair_fulfillment=pf))
    return out


_STATUS_ORDER = {"stock_egypt": 0, "stock_outside": 1, "rx": 2, "split": 3,
                 "eligibility_unknown": 4, "unavailable": 4}
_STATUS_AR = {"stock_egypt": "STOCK داخل مصر", "stock_outside": "STOCK خارج مصر",
              "rx": "RX / تصنيع", "split": "مصدر مقسّم (غير موحد)",
              "eligibility_unknown": "التوافق مع الوصفة غير مؤكد (نطاق القوة)",
              "unavailable": "غير متوفر"}
_EYEBEST_AR = {"stock_egypt": "STOCK مصر", "stock_outside": "STOCK خارج مصر",
               "rx": "RX / تصنيع", "unknown": "غير مؤكد (نطاق القوة)", "none": "غير متوفر"}


def _order_key(r: schemas.PerEyeProductResult):
    pf = r.pair_fulfillment
    price = pf.price_pair
    return (_STATUS_ORDER.get(pf.status, 3),
            0 if pf.provenance == "single_route" else 1,   # proven-price pairs first within a tier
            -float(r.match_score),
            Decimal(str(price)) if price is not None else Decimal("999999999"))


_GROUP_DEFS = [
    ("stock_egypt", "🇪🇬 زوج STOCK داخل مصر", "stock", "egypt"),
    ("stock_out_of_egypt", "🌍 زوج STOCK خارج مصر", "stock", "out_of_egypt"),
    ("rx", "🏭 زوج RX / تصنيع", "rx", None),
    ("split", "⚠️ مصدر غير موحد / غير متوفر للزوج", "mixed", None),
    ("eligibility_unknown", "❓ التوافق مع الوصفة غير مؤكد (نطاق القوة)", "unknown", None),
]
_STATUS_TO_GROUP = {"stock_egypt": "stock_egypt", "stock_outside": "stock_out_of_egypt",
                    "rx": "rx", "split": "split", "unavailable": "split",
                    "eligibility_unknown": "eligibility_unknown"}


def _build_groups(ordered: List[schemas.PerEyeProductResult]) -> List[schemas.LensSearchGroup]:
    buckets: Dict[str, List[schemas.PerEyeProductResult]] = {
        "stock_egypt": [], "stock_out_of_egypt": [], "rx": [], "split": [],
        "eligibility_unknown": []}
    for r in ordered:
        buckets[_STATUS_TO_GROUP[r.pair_fulfillment.status]].append(r)
    groups = []
    for key, label, avail, market in _GROUP_DEFS:
        rows = buckets[key]
        groups.append(schemas.LensSearchGroup(
            key=key, label=label, availability=avail, market=market,
            catalog_note=("حسب الكتالوج" if avail == "stock"
                          else "تصنيع حسب الطلب" if avail == "rx"
                          else "التوافق مع الوصفة غير مؤكد بسبب نطاق القوة" if avail == "unknown"
                          else "سعر الزوج غير مثبت"),
            count=len(rows), results=rows))
    return groups


# ---------------------------------------------------------------- answer
def _answer(ordered: List[schemas.PerEyeProductResult]) -> schemas.AvailabilityAnswer:
    statuses = {r.pair_fulfillment.status for r in ordered}
    if "stock_egypt" in statuses:
        return schemas.AvailabilityAnswer(code="stock_egypt",
            title="✅ الزوج متوفر STOCK داخل مصر لهذه الوصفة", detail="حسب الكتالوج الحالي.")
    if "stock_outside" in statuses:
        return schemas.AvailabilityAnswer(code="stock_out_of_egypt",
            title="🌍 الزوج غير متوفر داخل مصر — متوفر STOCK خارج مصر", detail="حسب الكتالوج الحالي.")
    if "rx" in statuses:
        return schemas.AvailabilityAnswer(code="rx_only",
            title="🏭 الزوج غير متوفر STOCK — متاح RX / تصنيع", detail="يُصنع حسب الطلب.")
    if "split" in statuses:
        return schemas.AvailabilityAnswer(code="split",
            title="⚠️ لا يوجد مصدر موحد مؤكد للزوج بهذه المواصفات",
            detail="يمكن توفير كل عين على حدة؛ سعر الزوج المختلط غير مثبت في الكتالوج.")
    if "eligibility_unknown" in statuses:
        # Phase 3 REQUIRED wording - never "متاح RX" or any other proven-
        # availability claim while optical eligibility is unresolved.
        return schemas.AvailabilityAnswer(code="power_eligibility_unknown",
            title="المنتج موجود في الكتالوج، لكن توافقه مع هذه الوصفة غير مؤكد بسبب نطاق القوة.",
            detail="نطاق القوة الحقيقي لهذا المنتج غير مُمثَّل بعد في النظام؛ يحتاج مراجعة "
                   "قبل اعتباره متوافقاً مع أي وصفة.")
    return schemas.AvailabilityAnswer(code="none",
        title="❌ لا توجد عدسة بهذه المواصفات متوافقة مع الوصفة في الكتالوج الحالي",
        detail="جرّب البحث التلقائي أو راجع أقرب البدائل.")


# ---------------------------------------------------------------- exact gate
def _passes_targeted_gate(r: schemas.PerEyeProductResult, f: schemas.LensFilters) -> bool:
    """availability / market / max_price applied to the PAIR fulfillment (strict
    AND, never relaxed)."""
    st = r.pair_fulfillment.status
    if f.max_price is not None:
        p = r.pair_fulfillment.price_pair
        if p is None or p > Decimal(str(f.max_price)):
            return False
    if f.availability is not None:
        want = getattr(f.availability, "value", f.availability)
        if want == "stock" and st not in ("stock_egypt", "stock_outside"):
            return False
        if want == "rx" and st != "rx":
            return False
    if f.market_scope:
        want_eg = market_is_egypt(f.market_scope)
        if want_eg is True and st != "stock_egypt":
            return False
        if want_eg is False and st not in ("stock_outside", "rx"):
            return False
    return True


# ---------------------------------------------------------------- entry point
def search(db: Session, prescription: models.Prescription,
           req: schemas.ProductSearchRequest) -> schemas.ProductSearchResponse:
    targeted = (req.mode or "automatic").strip().lower() == "targeted"
    filters = req.filters if targeted else None

    max_sph = max(abs(prescription.od_sph), abs(prescription.os_sph))
    max_cyl = max(abs(prescription.od_cyl or 0), abs(prescription.os_cyl or 0))
    rec_index, index_desc = lens_matcher.recommender.recommend_index(max_sph)
    need_asph, aspherical_desc = lens_matcher.recommender.recommend_aspherical(max_sph, max_cyl)

    # per-eye / pair analysis for every commercial option that satisfies the
    # IDENTITY filters (company / product / index / category / design / coating /
    # colour-technology). Availability / market / max_price are NOT applied here.
    options = _per_eye_results(db, prescription, filters, req, rec_index, need_asph)

    alternatives: List[schemas.AlternativeResult] = []
    alt_note = None
    intel: List[schemas.PerEyeProductResult] = []
    intel_note = None

    # "eligibility_unknown" is never a proven automatic/exact match (Phase 3):
    # excluded exactly like "unavailable", UNLESS a specific product is pinned
    # with no availability/market/price gate - then it must surface so the
    # employee sees the "compatibility unresolved" answer instead of nothing.
    _UNPROVEN = ("unavailable", "eligibility_unknown")

    if not targeted or filters is None:
        exact = [r for r in options if r.pair_fulfillment.status not in _UNPROVEN]
    else:
        # ALL requested targeted filters stay strict AND - availability / market /
        # max_price gate the pair fulfillment and are NEVER relaxed, not even for
        # a pinned product.
        gated = bool(filters.availability is not None or filters.market_scope or filters.max_price is not None)
        # a pinned product with no availability/market/price gate may surface even
        # when an eye is impossible or unresolved, so §7's per-eye matrix + the
        # power-eligibility warning can show.
        keep_unresolved = filters.lens_model_id is not None and not gated
        exact = [r for r in options
                 if _passes_targeted_gate(r, filters)
                 and (keep_unresolved or r.pair_fulfillment.status not in _UNPROVEN)]

        if not exact and gated:
            # same requested commercial option(s), just outside the requested
            # availability / market / price - OR the same option with
            # unresolved power eligibility (Phase 3C item 4: this is
            # informational catalog evidence, never an alternative, never an
            # actionable pair price - each item's own pair_fulfillment.reason
            # still carries the precise "غير مؤكد بسبب نطاق القوة" wording for
            # an eligibility_unknown entry). Shown SEPARATELY, never counted
            # as exact, never relaxing the filters.
            intel = sorted(
                [r for r in options if r.pair_fulfillment.status != "unavailable"],
                key=_order_key)
            if intel:
                intel_note = ("المطلوب غير متوفر بالتوفر/السوق/السعر المطلوب؛ هذا نفس المنتج "
                              "المطلوب بحالة أخرى (خارج المطلوب، أو توافقه مع الوصفة غير مؤكد "
                              "بسبب نطاق القوة) — ليس نتيجة مطابقة.")

        if not exact and not intel and req.include_alternatives:
            all_results, *_ = lens_matcher.match_lenses(
                db, prescription, None, req.prefer_stock, req.prefer_aspherical)
            # Phase 3C: an alternative must be prescription-safe too - a
            # candidate whose power_eligibility is UNRESOLVED (or genuinely
            # ineligible) is never a usable fallback, never offered as a
            # priced recommendation.
            all_results = _proven_eligible_for_alternatives(
                db, all_results, prescription, filters.applicability_key if filters else None)
            alternatives = compute_alternatives(all_results, set(), filters)
            if alternatives:
                alt_note = ("لا يوجد مطابق تام للمواصفات المطلوبة؛ هذه أقرب البدائل تجارياً "
                            "وهي ليست مطابقات تامة.")

    ordered = sorted(exact, key=_order_key)
    groups = _build_groups(ordered)
    answer = _answer(ordered)

    if not ordered and intel:
        want_bits = []
        if filters and filters.availability is not None:
            want_bits.append(getattr(filters.availability, "value", filters.availability).upper())
        if filters and filters.market_scope:
            want_bits.append(filters.market_scope)
        want = " / ".join(want_bits) if want_bits else "المواصفات المطلوبة"
        answer = schemas.AvailabilityAnswer(
            code="none",
            title=f"❌ غير متوفر بهذه المواصفات ({want})",
            detail="راجع «توفر نفس المنتج» أدناه — نفس المنتج متاح خارج المطلوب.")

    counts = {"stock_egypt": 0, "stock_out_of_egypt": 0, "rx": 0, "split": 0,
              "eligibility_unknown": 0}
    for r in ordered:
        counts[_STATUS_TO_GROUP[r.pair_fulfillment.status]] += 1

    return schemas.ProductSearchResponse(
        prescription=schemas.PrescriptionResponse.model_validate(prescription),
        mode="targeted" if targeted else "automatic",
        transposition_applied=prescription.transposition_applied,
        index_recommendation=index_desc, aspherical_recommendation=aspherical_desc,
        availability_answer=answer, exact_total=len(ordered),
        best_match=ordered[0] if ordered else None, groups=groups,
        stock_egypt_count=counts["stock_egypt"],
        stock_out_of_egypt_count=counts["stock_out_of_egypt"],
        eligibility_unknown_count=counts["eligibility_unknown"],
        rx_count=counts["rx"], split_count=counts["split"],
        alternatives=alternatives, alternatives_note=alt_note,
        availability_intelligence=intel, availability_intelligence_note=intel_note)
