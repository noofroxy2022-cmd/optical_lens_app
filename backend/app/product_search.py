"""V1.0.1 product-search layer: availability-first ordering, strict targeted
AND filters, a direct availability answer, and a SEPARATE alternatives list.

This is a thin layer on top of the FROZEN optical matcher. It never changes
optical eligibility or match_score - it only:
  * applies the V1.0.1 targeted filters that `lens_matcher` does not already
    read (lens_model_id / design_variant / color_variant) as strict AND,
  * re-orders results availability-first (STOCK Egypt -> STOCK Out Of Egypt
    -> RX; within a tier: match_score desc, then retail price asc),
  * groups results into the three fixed buckets,
  * derives the operator's availability answer,
  * computes commercially-close alternatives (existing dimensions only) when a
    targeted search has no exact result - kept in their own list, never mixed
    with or labelled as exact matches.
"""
from typing import List, Optional, Tuple
from decimal import Decimal

from sqlalchemy.orm import Session

from app import schemas, models
from app.lens_matcher import lens_matcher


# ---------------------------------------------------------------- market / tier
def _norm(v: Optional[str]) -> str:
    return (v or "").strip().lower()


def market_is_egypt(market_scope: Optional[str]) -> Optional[bool]:
    """True = Egypt, False = a named non-Egypt market, None = unspecified."""
    s = _norm(market_scope)
    if not s:
        return None
    if "out" in s and "egypt" in s:      # "Out Of Egypt", "out_of_egypt"
        return False
    if s in ("egypt", "eg", "مصر"):
        return True
    if "egypt" in s:                      # bare "Egypt ..." with no "out"
        return True
    return False                          # any other named market -> treat as non-Egypt


def result_tier(r: schemas.LensMatchResult) -> int:
    """0 = STOCK Egypt, 1 = STOCK (non-Egypt / unspecified), 2 = RX."""
    if r.availability == "stock":
        return 0 if market_is_egypt(r.market_scope) is True else 1
    return 2


def order_results(results: List[schemas.LensMatchResult]) -> List[schemas.LensMatchResult]:
    """Authoritative availability-first order. No RX ever sits between STOCK
    rows. Within a tier: existing match_score first, then retail price as a
    deterministic tie-break."""
    return sorted(
        results,
        key=lambda r: (result_tier(r), -float(r.match_score), Decimal(str(r.price_pair))),
    )


_GROUP_DEFS = [
    ("stock_egypt", "🇪🇬 STOCK داخل مصر", "stock", "egypt"),
    ("stock_out_of_egypt", "🌍 STOCK خارج مصر", "stock", "out_of_egypt"),
    ("rx", "🏭 RX / تصنيع", "rx", None),
]


def build_groups(ordered: List[schemas.LensMatchResult]) -> List[schemas.LensSearchGroup]:
    buckets = {"stock_egypt": [], "stock_out_of_egypt": [], "rx": []}
    for r in ordered:
        t = result_tier(r)
        buckets["stock_egypt" if t == 0 else "stock_out_of_egypt" if t == 1 else "rx"].append(r)
    groups = []
    for key, label, avail, market in _GROUP_DEFS:
        rows = buckets[key]
        groups.append(schemas.LensSearchGroup(
            key=key, label=label, availability=avail, market=market,
            catalog_note="حسب الكتالوج" if avail == "stock" else "تصنيع حسب الطلب",
            count=len(rows), results=rows,
        ))
    return groups


# ---------------------------------------------------------------- targeted AND
# filters that lens_matcher already enforces internally
_MATCHER_NATIVE = {
    "company_id", "category", "index_value", "min_index", "max_index",
    "material", "design_type", "prefer_aspherical", "coating", "market_scope",
    "availability", "max_price", "features", "is_active",
}
# extra V1.0.1 dimensions the matcher does not read - enforced here
_IDENTITY_EXTRA = {"lens_model_id", "design_variant", "color_variant"}


def _passes_extra_identity(r: schemas.LensMatchResult, f: schemas.LensFilters) -> bool:
    if f.lens_model_id is not None and r.lens_model.id != f.lens_model_id:
        return False
    if f.design_variant:
        if _norm(f.design_variant) not in _norm(r.design_variant or r.variant.design_variant):
            return False
    if f.color_variant:
        if _norm(f.color_variant) not in _norm(r.color_variant or r.variant.color_variant):
            return False
    return True


def _identity_filters_only(f: schemas.LensFilters) -> schemas.LensFilters:
    """A copy with availability & market_scope dropped - used to answer 'does
    this product exist for the Rx at all, in any tier?'."""
    data = f.model_dump()
    data["availability"] = None
    data["market_scope"] = None
    return schemas.LensFilters(**data)


def _matcher_filters(f: Optional[schemas.LensFilters]) -> Optional[schemas.LensFilters]:
    """Strip the extra V1.0.1 dimensions so we pass the matcher only what it
    already understands (it would ignore them anyway; this keeps intent clear)."""
    if f is None:
        return None
    data = f.model_dump()
    for k in _IDENTITY_EXTRA:
        data[k] = None
    return schemas.LensFilters(**data)


# ---------------------------------------------------------------- availability answer
def _answer_from_tiers(has0: bool, has1: bool, has2: bool, *, requested_market_egypt: Optional[bool]) -> schemas.AvailabilityAnswer:
    if has0:
        return schemas.AvailabilityAnswer(
            code="stock_egypt",
            title="✅ متوفر STOCK داخل مصر لهذه الوصفة",
            detail="حسب الكتالوج الحالي.",
        )
    if has1:
        return schemas.AvailabilityAnswer(
            code="stock_out_of_egypt",
            title="🌍 غير متوفر داخل مصر — متوفر STOCK خارج مصر",
            detail="حسب الكتالوج الحالي.",
        )
    if has2:
        return schemas.AvailabilityAnswer(
            code="rx_only",
            title="🏭 غير متوفر STOCK — متاح RX / تصنيع",
            detail="يُصنع حسب الطلب.",
        )
    return schemas.AvailabilityAnswer(
        code="none",
        title="❌ لا توجد عدسة بهذه المواصفات متوافقة مع الوصفة في الكتالوج الحالي",
        detail="جرّب البحث التلقائي أو راجع أقرب البدائل." ,
    )


# ---------------------------------------------------------------- alternatives
def _family_token(name: Optional[str]) -> str:
    return _norm((name or "").split()[0]) if name else ""


def _alt_scored(
    r: schemas.LensMatchResult, f: schemas.LensFilters,
    ref_family: str,
) -> Tuple[int, List[str], str]:
    """proximity_score, relaxed_filters (unsatisfied requested dims), reason."""
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
    # requested availability / market that this alternative does not meet
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
    # closest availability tier is always a mild plus for STOCK Egypt
    score += (2 - result_tier(r))
    reason = "، ".join(matches) if matches else "أقرب بديل متوافق مع الوصفة"
    return score, relaxed, reason


def compute_alternatives(
    all_results: List[schemas.LensMatchResult],
    exact_ids: set,
    f: schemas.LensFilters,
    limit: int = 15,
) -> List[schemas.AlternativeResult]:
    ref_family = ""  # resolved lazily from the first requested-model match if any
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
            result=r, relaxed_filters=relaxed, proximity_reason=reason, proximity_score=score,
        ))
    alts.sort(key=lambda a: (
        -a.proximity_score,
        result_tier(a.result),
        -float(a.result.match_score),
        Decimal(str(a.result.price_pair)),
    ))
    return alts[:limit]


# ---------------------------------------------------------------- entry point
def search(
    db: Session,
    prescription: models.Prescription,
    req: schemas.ProductSearchRequest,
) -> schemas.ProductSearchResponse:
    targeted = (req.mode or "automatic").strip().lower() == "targeted"
    filters = req.filters if targeted else None

    # 1) FROZEN matcher - full automatic candidate set for this prescription
    all_results, _sc, _rc, index_desc, aspherical_desc = lens_matcher.match_lenses(
        db, prescription, None, req.prefer_stock, req.prefer_aspherical
    )

    if not targeted or filters is None:
        exact = list(all_results)
        answer_pool = exact
        alternatives: List[schemas.AlternativeResult] = []
        alt_note = None
    else:
        # 2a) matcher-native filters (strict) via a second matcher pass -> honours
        #     company/index/category/coating/market/availability/max_price exactly
        native, _s2, _r2, _i2, _a2 = lens_matcher.match_lenses(
            db, prescription, _matcher_filters(filters), req.prefer_stock, req.prefer_aspherical
        )
        # 2b) extra V1.0.1 identity dimensions (strict AND) applied here
        exact = [r for r in native if _passes_extra_identity(r, filters)]

        # identity-only pool (drops availability & market) -> answers "does this
        # product exist for the Rx at all, in any tier?"
        id_only = _identity_filters_only(filters)
        id_native, *_ = lens_matcher.match_lenses(
            db, prescription, _matcher_filters(id_only), req.prefer_stock, req.prefer_aspherical
        )
        answer_pool = [r for r in id_native if _passes_extra_identity(r, id_only)]

        alternatives = []
        alt_note = None
        if not exact and req.include_alternatives:
            exact_ids = {r.source_pricing_id for r in exact}
            alternatives = compute_alternatives(all_results, exact_ids, filters)
            if alternatives:
                alt_note = ("لا يوجد مطابق تام للمواصفات المطلوبة؛ هذه أقرب البدائل "
                            "تجارياً وهي ليست مطابقات تامة.")

    # 3) availability answer from the answer pool's tiers
    has0 = any(result_tier(r) == 0 for r in answer_pool)
    has1 = any(result_tier(r) == 1 for r in answer_pool)
    has2 = any(result_tier(r) == 2 for r in answer_pool)
    req_market_eg = market_is_egypt(filters.market_scope) if (targeted and filters) else None
    answer = _answer_from_tiers(has0, has1, has2, requested_market_egypt=req_market_eg)
    # targeted: nothing at all after ALL filters, but the product exists in
    # another tier -> keep the informative tier answer, it is carried by the
    # alternatives list below.
    if targeted and filters is not None and not exact and not answer_pool:
        answer = _answer_from_tiers(False, False, False, requested_market_egypt=req_market_eg)

    ordered = order_results(exact)
    groups = build_groups(ordered)
    stock_eg = sum(1 for r in ordered if result_tier(r) == 0)
    stock_ooe = sum(1 for r in ordered if result_tier(r) == 1)
    rx_n = sum(1 for r in ordered if result_tier(r) == 2)

    return schemas.ProductSearchResponse(
        prescription=schemas.PrescriptionResponse.model_validate(prescription),
        mode="targeted" if targeted else "automatic",
        transposition_applied=prescription.transposition_applied,
        index_recommendation=index_desc,
        aspherical_recommendation=aspherical_desc,
        availability_answer=answer,
        exact_total=len(ordered),
        best_match=ordered[0] if ordered else None,
        groups=groups,
        stock_egypt_count=stock_eg,
        stock_out_of_egypt_count=stock_ooe,
        rx_count=rx_n,
        alternatives=alternatives,
        alternatives_note=alt_note,
    )
