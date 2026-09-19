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
import re
from typing import List, Optional, Tuple, Dict
from decimal import Decimal

from sqlalchemy.orm import Session

from app import schemas, models
from app import technology_evidence
from app import customer_needs
from app.lens_matcher import lens_matcher

_RX = models.PricingAvailability.RX
_STOCK = models.PricingAvailability.STOCK
# "stock_market_unknown": a STOCK row whose market_scope is genuinely
# unspecified in the catalog (market_is_egypt() -> None). Distinct from BOTH
# stock_egypt and stock_outside - never proven Egypt, never proven Out Of
# Egypt. Kept as its own tier (not folded into stock_outside) so a NULL-market
# STOCK row is never mislabeled as a confirmed non-Egypt market (Phase 3C).
_TIERS = ("stock_egypt", "stock_outside", "stock_market_unknown", "rx")


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
        eg = market_is_egypt(p.market_scope)
        if eg is True:
            return "stock_egypt"
        if eg is False:
            return "stock_outside"
        return "stock_market_unknown"   # market_scope is NULL/unspecified - never assumed Out Of Egypt
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
    rule (per the permanent domain rule, RX manufacturing eligibility is not
    dependent on a printed range by default). Filtering happens HERE, after
    the frozen matcher runs and before compute_alternatives() ever sees the
    candidate - a row that IS split into optical sub-options but doesn't
    offer the one requested is still correctly excluded ("ineligible"/
    "unknown" from `_row_eye_status`); only "eligible" passes."""
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
        # V1: company is never a "relaxable" dimension for alternatives - a
        # shop user who explicitly asked for one manufacturer must never be
        # shown another manufacturer's lens as a same-request alternative.
        # Every other supplied filter (index, design, coating, ...) may still
        # be relaxed and merely lowers proximity_score/relaxed_filters below.
        if f.company_id is not None and r.lens_model.company_id != f.company_id:
            continue
        # V1.0.1: category is a HARD boundary, never a relaxable dimension - a
        # shop user searching Single Vision must never be shown a Progressive
        # or Bifocal lens as a same-request alternative (different optical
        # product entirely, not a commercial substitute). Same rule shape as
        # company_id above.
        if f.category is not None and r.lens_model.category != f.category:
            continue
        # V1: max_price is a hard budget ceiling, never a relaxable dimension
        # (matches the exact-match gate's own "never relaxed" rule in
        # _passes_targeted_gate) - an alternative over budget must never be
        # shown merely for being otherwise relevant.
        if f.max_price is not None and r.price_pair > Decimal(str(f.max_price)):
            continue
        score, relaxed, reason = _alt_scored(r, f, ref_family)
        alts.append(schemas.AlternativeResult(
            result=r, relaxed_filters=relaxed, proximity_reason=reason, proximity_score=score))
    # V1: alternatives must be sorted by retail pair price (ascending) first -
    # a shop user comparing options needs the cheapest proven-eligible option
    # first. Proximity/tier/match-score remain as tiebreakers only for equal
    # prices, never overriding price order.
    alts.sort(key=lambda a: (Decimal(str(a.result.price_pair)), -a.proximity_score,
                             result_tier(a.result), -float(a.result.match_score)))
    return alts[:limit]


# ---------------------------------------------------------------- per-eye engine
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
    OR-range -> eligible, else ineligible - this is the ONLY way a row's
    eligibility is ever restricted; `power_eligibility` plays no part in it.

    A row with NO PowerRange at all:
      - RX / Manufacturing: made-to-order, ALWAYS "eligible" - a manufacturing
        lens is not dependent on a printed range by default (permanent domain
        rule). Absence of a manufacturer-published range means "no
        restriction supplied", never "compatibility unknown" and never
        "incompatible" - so `power_eligibility` (UNRESTRICTED vs UNRESOLVED)
        is NOT consulted here either; only an explicit PowerRange (checked
        above) ever narrows an RX row's eligibility. `power_eligibility` is
        kept only as historical catalog provenance on the row - it no longer
        drives eligibility once a row has zero ranges.
      - STOCK: "ineligible" - a STOCK row proves a lens is commercially priced
        and stocked, never that a specific prescription's power is physically
        in inventory; that requires a printed Stock PowerRange, which this
        row does not have.

    `applicability_key`, when given, restricts evaluation to that one optical
    sub-option's range(s) only - see _applicable_ranges.

    "unknown" is never returned by this function any more (permanent domain
    rule change): every shape this schema can represent resolves to a
    definite "eligible" or "ineligible". The tri-state name and the
    "unknown"/"eligibility_unknown" plumbing downstream (EyeAvailability.
    *_unknown, PairFulfillment.status="eligibility_unknown",
    AvailabilityAnswer.code="power_eligibility_unknown") are kept as-is
    (harmless, unreachable from here) rather than removed in this pass."""
    ranges = _applicable_ranges(p, applicability_key)
    if ranges:
        ok = any(lens_matcher.check_power_range(pr, prescription, eye)[0] for pr in ranges)
        return "eligible" if ok else "ineligible"
    if list(p.power_ranges):
        return "ineligible"       # split row that doesn't offer the requested subtype at all
    if p.availability != _RX:
        return "ineligible"       # STOCK with no range: commercially priced, stock compatibility unproven
    return "eligible"              # RX made-to-order: no printed range = no restriction, not "unknown"


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


_DIAMETER_NOTE_RE = re.compile(r"(?:Ø|diameter_mm=)\s*(\d+)")


def _row_matching_ranges(p: models.VariantPricing, prescription: models.Prescription,
                         eye: str, applicability_key: Optional[str] = None) -> List["models.PowerRange"]:
    """Every PowerRange of `p` that actually proves ONE eye eligible for this
    prescription (never just a pass/fail bool) - used only to inspect what
    catalog EVIDENCE (e.g. a printed diameter) backed the proof, never to
    change eligibility itself."""
    ranges = _applicable_ranges(p, applicability_key)
    return [pr for pr in ranges if lens_matcher.check_power_range(pr, prescription, eye)[0]]


def _extract_diameter_mm(notes: Optional[str]) -> Optional[int]:
    """Best-effort diameter (mm) recorded as catalog evidence in a
    PowerRange.notes string - e.g. this project's own "Ø65" convention
    (Maxxee/BBGR/DIVEL) or the pre-existing ZEISS "diameter_mm=70" evidence
    format. Returns None when no diameter marker is present - NEVER inferred
    or guessed from anything else."""
    if not notes:
        return None
    m = _DIAMETER_NOTE_RE.search(notes)
    return int(m.group(1)) if m else None


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
    # .get(..., []) - Phase 3C added the "stock_market_unknown" tier after
    # several existing callers (and their tests) already built a `routes`
    # dict with only the original 3 keys; treating an absent tier as "no
    # rows at that tier" keeps this function backward-compatible with any
    # caller that has not been updated to the 4-tier shape, without ever
    # hiding a real row (every REAL row still lands in some route bucket
    # wherever `routes` is actually built from `_row_route`, e.g. _per_eye_results).
    se = _route_eye_status(routes.get("stock_egypt", []), prescription, eye, applicability_key)
    so = _route_eye_status(routes.get("stock_outside", []), prescription, eye, applicability_key)
    su = _route_eye_status(routes.get("stock_market_unknown", []), prescription, eye, applicability_key)
    rx = _route_eye_status(routes.get("rx", []), prescription, eye, applicability_key)
    best = ("stock_egypt" if se == "eligible" else
            "stock_outside" if so == "eligible" else
            "stock_market_unknown" if su == "eligible" else
            "rx" if rx == "eligible" else
            "unknown" if "unknown" in (se, so, su, rx) else "none")
    return schemas.EyeAvailability(
        stock_egypt=(se == "eligible"), stock_outside=(so == "eligible"),
        stock_market_unknown=(su == "eligible"), rx=(rx == "eligible"),
        stock_egypt_unknown=(se == "unknown"), stock_outside_unknown=(so == "unknown"),
        stock_market_unknown_unknown=(su == "unknown"),
        rx_unknown=(rx == "unknown"), best=best)


def _diameter_confirmation_note(candidates: List[Tuple[models.VariantPricing, Optional[str]]],
                                prescription: models.Prescription,
                                applicability_key: Optional[str]) -> Optional[str]:
    """When 2+ same-identity/same-tier candidate rows all prove eligible for
    the SAME prescription at DIFFERENT prices, and their proving PowerRange
    evidence records DIFFERENT diameters, the cheaper price is not
    unconditionally final - which one applies depends on a real commercial
    dimension (diameter) this matcher does not evaluate (D1 scalar-diameter
    work remains separately deferred; this is a display-only caveat, never a
    matching change). Returns None in the ordinary, unambiguous case - equal
    prices, or every candidate's proven diameter evidence agrees, or none
    records a diameter at all (e.g. Maxxee's own overlapping bands, whose
    competing ranges always share one printed diameter)."""
    if len(candidates) < 2:
        return None
    if len({c[0].price_pair for c in candidates}) < 2:
        return None
    # Resolve overlapping cylinder bands independently at each proven diameter.
    # Different band prices alone do not prove diameter-dependent pricing.
    prices_by_diameter = {}
    for p, _ in candidates:
        eye_diameters = []
        for eye in ("od", "os"):
            eye_diameters.append({d for pr in _row_matching_ranges(
                p, prescription, eye, applicability_key)
                if (d := _extract_diameter_mm(pr.notes)) is not None})
        for d in eye_diameters[0] | eye_diameters[1]:
            prices_by_diameter.setdefault(d, [])
        for d in eye_diameters[0] & eye_diameters[1]:
            prices_by_diameter[d].append(p.price_pair)
    diameters = set(prices_by_diameter)
    if len(diameters) < 2:
        return None
    if all(prices_by_diameter.values()) and len({
            min(prices) for prices in prices_by_diameter.values()}) == 1:
        return None
    dia_list = "/".join(str(d) for d in sorted(diameters))
    return (f"السعر يعتمد على قطر العدسة المطلوب ({dia_list} مم)، "
            f"ويجب تأكيد القطر قبل اعتماد السعر النهائي.")


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


def _price_confirmation_note(pricing):
    """Enforce the existing PIXEL RX policy even when persisted notes are missing.

    The catalog has no numeric Hi Power trigger and the schema has no lab
    approval state. A missing/blank note can never mean the lab confirmed it.
    """
    from app.pixel_addons_evidence import HI_POWER_CONFIRMATION_NOTE
    note = pricing.price_confirmation_note
    company = pricing.variant.lens_model.company
    if _row_route(pricing) == "rx" and company and company.name == "Pixel":
        if not note or not note.strip():
            return HI_POWER_CONFIRMATION_NOTE
    return note


def _pair_fulfillment(routes: Dict[str, List[models.VariantPricing]],
                      od: schemas.EyeAvailability, os_: schemas.EyeAvailability,
                      prescription: models.Prescription,
                      applicability_key: Optional[str] = None) -> schemas.PairFulfillment:
    od_ok = {"stock_egypt": od.stock_egypt, "stock_outside": od.stock_outside,
             "stock_market_unknown": od.stock_market_unknown, "rx": od.rx}
    os_ok = {"stock_egypt": os_.stock_egypt, "stock_outside": os_.stock_outside,
             "stock_market_unknown": os_.stock_market_unknown, "rx": os_.rx}
    tier_label = {"stock_egypt": "STOCK داخل مصر", "stock_outside": "STOCK خارج مصر",
                  "stock_market_unknown": "STOCK — مكان التوفر غير محدد", "rx": "RX / تصنيع"}

    for tier in _TIERS:
        if not (od_ok[tier] and os_ok[tier]):
            continue
        rows = routes.get(tier, [])
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
        # Multiple proven single-route rows can cover the SAME prescription
        # when a manufacturer prints overlapping power-dependent price bands
        # (e.g. a cheaper band with a tighter CYL limit alongside a pricier
        # band with a wider one, both spanning a shared SPH/CYL zone). The
        # catalog never says "pick arbitrarily" in that overlap - the only
        # non-arbitrary, generic rule is to always quote the CHEAPEST proven
        # price, never whichever row happens to come first in DB row order.
        both = None
        proving_key = None
        candidates = []
        for p in od_rows:
            if not _row_covers_eye(p, prescription, "os", applicability_key):
                continue
            common = (_row_eye_proving_keys(p, prescription, "od", applicability_key)
                     & _row_eye_proving_keys(p, prescription, "os", applicability_key))
            if common:
                candidates.append((p, next(iter(common - {None}), None)))
        if candidates:
            both, proving_key = min(candidates, key=lambda c: c[0].price_pair)
        if both is not None:
            subtype_note = f" (subtype: {proving_key})" if proving_key else ""
            # Overlapping same-identity/same-tier bands normally resolve
            # cleanly by price alone (e.g. Maxxee's own bands, which always
            # share one printed diameter) - but when the competing bands
            # carry DIFFERENT catalog-proven diameter evidence, the cheapest
            # price is not unconditionally final: which one applies depends
            # on a real commercial dimension (diameter) this matcher cannot
            # evaluate. Never silently hidden behind the cheaper price.
            diameter_note = _diameter_confirmation_note(candidates, prescription, applicability_key)
            combined_note = _price_confirmation_note(both)
            if diameter_note:
                combined_note = f"{combined_note} | {diameter_note}" if combined_note else diameter_note
            return schemas.PairFulfillment(
                status=tier, price_pair=both.price_pair, currency=both.currency,
                source_pricing_ids=[both.id], provenance="single_route", needs_review=False,
                reason=f"مسار تسعير واحد يغطي العينين ({tier_label[tier]}){subtype_note} — سعر الزوج من الكتالوج.",
                applicability_key=proving_key,
                price_confirmation_note=combined_note)

        # (a2) OD and OS covered by DIFFERENT rows, but a proven OR-clause pair of
        #      ONE catalog pricing offer (same source_extraction_id + facets) -
        #      same same-sub-option discipline as (a).
        proven = None
        proving_key = None
        or_candidates = []
        for a in od_rows:
            for b in os_rows:
                if a.id == b.id or not _same_pricing_offer(a, b):
                    continue
                common = (_row_eye_proving_keys(a, prescription, "od", applicability_key)
                         & _row_eye_proving_keys(b, prescription, "os", applicability_key))
                if common:
                    or_candidates.append(((a, b), next(iter(common - {None}), None)))
        if or_candidates:
            # same cheapest-wins tie-break as (a) above, for the OR-clause-pair case.
            proven, proving_key = min(or_candidates, key=lambda c: c[0][0].price_pair)
        if proven is not None:
            a, b = proven
            subtype_note = f" (subtype: {proving_key})" if proving_key else ""
            return schemas.PairFulfillment(
                status=tier, price_pair=a.price_pair, currency=a.currency,
                source_pricing_ids=sorted({a.id, b.id}), provenance="single_route",
                needs_review=False,
                reason=(f"عرض تسعير واحد بعدة مدى قوة (OR) يغطي العينين ({tier_label[tier]})"
                        f"{subtype_note} — سعر الزوج من الكتالوج."),
                applicability_key=proving_key,
                price_confirmation_note=" | ".join(dict.fromkeys(
                    note for note in (_price_confirmation_note(a), _price_confirmation_note(b)) if note)) or None)

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
            p.id for tier in _TIERS for p in routes.get(tier, [])
            if _row_eye_status(p, prescription, "od", applicability_key) == "unknown"
            or _row_eye_status(p, prescription, "os", applicability_key) == "unknown"
        })
        return schemas.PairFulfillment(
            status="eligibility_unknown", price_pair=None, currency=None,
            source_pricing_ids=unresolved_ids, provenance="none", needs_review=True,
            reason="المنتج موجود في الكتالوج، لكن توافقه مع هذه الوصفة غير مؤكد بسبب نطاق القوة.")

    # no single tier covers both eyes, and neither eye is unresolved -> the
    # existing proven split/unavailable logic, unchanged.
    od_any = od.stock_egypt or od.stock_outside or od.stock_market_unknown or od.rx
    os_any = os_.stock_egypt or os_.stock_outside or os_.stock_market_unknown or os_.rx
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


def _stock_egypt_range_unverified(
    db: Session, category: Optional[str], filters: Optional[schemas.LensFilters],
    technology_intent: Optional[str], customer_need: Optional[str],
    selected_needs: Optional[List[str]],
) -> List[schemas.PerEyeProductResult]:
    """Informational-only list: STOCK rows whose market IS proven Egypt (the
    P0 confirmed business fact) but that print NO catalog PowerRange at all -
    so prescription compatibility can never be proven either way. Generic:
    ANY manufacturer's Stock-Egypt row with zero PowerRange qualifies, not a
    hardcoded SEIKO/BBGR list. Deliberately entirely separate from `options`/
    `exact`/`groups`/`best_match` - never counted as a match, never
    actionable, never a confirmed price for this prescription. Customer-need/
    technology_intent still gate this list exactly like the main pipeline -
    an unproven-range row is never allowed to claim an unproven technology
    capability either."""
    q = (
        db.query(models.VariantPricing, models.LensVariant, models.LensModel, models.Coating)
        .join(models.LensVariant, models.LensVariant.id == models.VariantPricing.variant_id)
        .join(models.LensModel, models.LensModel.id == models.LensVariant.lens_model_id)
        .outerjoin(models.Coating, models.Coating.id == models.VariantPricing.coating_id)
        .filter(
            models.VariantPricing.availability == _STOCK,
            models.VariantPricing.effective_to.is_(None),
            models.LensModel.is_active.is_(True),
            models.LensModel.is_deleted.is_(False),
            models.LensVariant.is_active.is_(True),
            ~models.VariantPricing.power_ranges.any(),
        )
    )
    if category:
        q = q.filter(models.LensModel.category == category)
    if filters is not None:
        if filters.company_id is not None:
            q = q.filter(models.LensModel.company_id == filters.company_id)
        if filters.index_value is not None:
            q = q.filter(models.LensVariant.index_value == filters.index_value)

    required_caps = (technology_evidence.missing_capabilities(technology_intent, set())
                     | set(selected_needs or []))
    out: List[schemas.PerEyeProductResult] = []
    for vp, v, m, coating in q.all():
        if market_is_egypt(vp.market_scope) is not True:
            continue
        if filters is not None and not _passes_extra_identity(v, filters):
            continue
        company_name = m.company.name if m.company else None
        if not customer_needs.proves(customer_need, company_name, v.treatment_band):
            continue
        caps = technology_evidence.proven_capabilities(
            company_name=company_name,
            coating_name=(coating.name if coating else None),
            treatment_band=v.treatment_band, color_variant=v.color_variant,
            model_name=m.name, index_value=v.index_value,
            material=getattr(v.material, "value", v.material))
        if not required_caps.issubset(caps):
            continue   # never claim an unproven technology for an unproven-range row
        out.append(schemas.PerEyeProductResult(
            company_id=m.company_id, company_name=(m.company.name if m.company else ""),
            lens_model_id=m.id, model_name=m.name,
            category=getattr(m.category, "value", m.category),
            variant_id=v.id, index_value=v.index_value,
            material=getattr(v.material, "value", v.material),
            design_variant=v.design_variant, color_variant=v.color_variant,
            design_tier=v.design_tier, treatment_band=v.treatment_band,
            coating_id=vp.coating_id, coating_code=(coating.code if coating else None),
            coating_name=(coating.name if coating else None),
            currency=vp.currency, match_score=0,
            reason="Stock داخل مصر - نطاق القوة غير مثبت في الكتالوج",
            catalog_price_pair=vp.price_pair,
            od=schemas.EyeAvailability(), os=schemas.EyeAvailability(),
            pair_fulfillment=schemas.PairFulfillment(
                status="stock_egypt_range_unverified", price_pair=None, currency=vp.currency,
                source_pricing_ids=[vp.id], provenance="none", needs_review=True,
                reason="متوفر Stock داخل مصر، لكن توافقه مع هذه الوصفة يحتاج تأكيد PowerRange")))
    return out


def _per_eye_results(db: Session, prescription: models.Prescription,
                     filters: Optional[schemas.LensFilters], req: schemas.ProductSearchRequest,
                     rec_index: float, need_asph: bool,
                     derived_category: Optional[str] = None,
                     technology_intent: Optional[str] = None,
                     ) -> List[schemas.PerEyeProductResult]:
    probe = _probe_filters(filters)
    rows = lens_matcher._current_pricing_candidates(db, probe)

    groups: Dict[tuple, List[models.VariantPricing]] = {}
    for p in rows:
        v = p.variant
        if v is None or not v.is_active:
            continue
        m = v.lens_model
        # V1.2 use_mode: independent hard category boundary, applied even in
        # automatic mode (which has no `filters` object to carry it). Only
        # active when targeted mode did NOT already fold it into `filters`
        # (see search()) - never a duplicate/conflicting check.
        if derived_category is not None and getattr(m.category, "value", m.category) != derived_category:
            continue
        # NOTE: technology_intent is NOT gated here. `_identity_key` already
        # groups by coating_id/treatment_band/color_variant, so every row in
        # one identity group shares identical technology evidence - the
        # Type-A/Type-B decision is made ONCE per identity group below
        # (needed to attempt Type-B add-on completion, which is scoped to a
        # row's own availability route, not to the raw candidate row here).
        if probe is not None and not lens_matcher._passes_commercial_and_optical_filters(v, m, p, probe):
            continue
        if filters is not None and not _passes_extra_identity(v, filters):
            continue
        groups.setdefault(_identity_key(p), []).append(p)

    out: List[schemas.PerEyeProductResult] = []
    want_specific_product = bool(filters and filters.lens_model_id is not None)
    required_caps = (technology_evidence.missing_capabilities(technology_intent, set())
                     | set(req.customer_needs or []))
    want_tech = bool(required_caps)
    for _key, opt_rows in groups.items():
        sample = opt_rows[0]
        v = sample.variant
        m = v.lens_model
        company_name = m.company.name if m.company else None
        if not customer_needs.proves(req.customer_need, company_name, v.treatment_band):
            continue

        routes = {
            "stock_egypt": [p for p in opt_rows if _row_route(p) == "stock_egypt"],
            "stock_outside": [p for p in opt_rows if _row_route(p) == "stock_outside"],
            "stock_market_unknown": [p for p in opt_rows if _row_route(p) == "stock_market_unknown"],
            "rx": [p for p in opt_rows if _row_route(p) == "rx"],
        }

        addon_price: Optional[Decimal] = None
        addon_label: Optional[str] = None
        addon_unit = technology_evidence.UNIT_UNRESOLVED
        if want_tech:
            caps = technology_evidence.proven_capabilities(
                company_name=company_name, coating_name=(sample.coating.name if sample.coating else None),
                treatment_band=v.treatment_band, color_variant=v.color_variant,
                model_name=m.name, index_value=v.index_value,
                material=getattr(v.material, "value", v.material))
            if required_caps.issubset(caps):
                pass  # Type A - base row already proves it; no price change
            else:
                # Type B: a proven add-on can ONLY ever complete the "rx"
                # route (see technology_evidence._ADDON_EVIDENCE) - a Stock
                # row of this SAME identity never gains the technology this
                # way, so it must never be offered as if it now qualifies.
                # Restricting `routes` to rx-only here (rather than filtering
                # `opt_rows` itself) reuses the exact same _eye_availability/
                # _pair_fulfillment logic unmodified for every other caller.
                missing = required_caps - caps
                eligible_rx = []
                completion = None
                for row in routes["rx"]:
                    offer = technology_evidence.addon_completion(
                        company_name, "rx", missing,
                        color_variant=v.color_variant, index_value=v.index_value,
                        category=getattr(m.category, "value", m.category),
                        design_variant=v.design_variant, market_scope=row.market_scope,
                        model_name=m.name, coating_name=row.coating.name if row.coating else None,
                        treatment_band=v.treatment_band,
                        design_type=getattr(v.design_type, "value", v.design_type),
                        design_tier=v.design_tier)
                    if offer is not None:
                        eligible_rx.append(row)
                        completion = offer
                if completion is None:
                    continue  # no row in the proven scope can complete the intent
                addon_price, addon_label, _, addon_unit = completion
                routes = {"stock_egypt": [], "stock_outside": [], "stock_market_unknown": [],
                          "rx": eligible_rx}

        applicability_key = filters.applicability_key if filters else None
        od = _eye_availability(routes, prescription, "od", applicability_key)
        os_ = _eye_availability(routes, prescription, "os", applicability_key)
        pf = _pair_fulfillment(routes, od, os_, prescription, applicability_key)

        if addon_price is not None:
            # Only a genuinely proven single-route RX price may be completed
            # by an add-on - never a split/unproven_mixed/unavailable base,
            # since there is then no single proven base price to add to.
            if pf.status != "rx" or pf.price_pair is None:
                continue
            unit_proven = addon_unit in (technology_evidence.UNIT_PAIR_PROVEN,
                                         technology_evidence.UNIT_PER_LENS_PROVEN)
            note = pf.price_confirmation_note
            if not unit_proven:
                note = " | ".join(x for x in (note, technology_evidence.UNIT_CONFIRMATION_NOTE) if x)
            pf = pf.model_copy(update={
                "price_pair": pf.price_pair + addon_price if unit_proven else None,
                "price_confirmation_note": note,
                "technology_addon": schemas.TechnologyAddonInfo(
                    label=addon_label, base_price=pf.price_pair, addon_price=addon_price,
                    unit_status=addon_unit),
                "reason": pf.reason + f" + إضافة مثبتة من الكتالوج: {addon_label} (+{addon_price} EGP) لتحقيق التكنولوجيا المطلوبة.",
            })

        if pf.status == "unavailable" and not want_specific_product:
            continue  # automatic / non-specific: drop options no eye combo can use

        # score: reuse the frozen calculator on the fulfilling route's row + a
        # covering range (falls back to a representative row for split/unavailable)
        score_row = None
        if pf.source_pricing_ids:
            score_row = next((p for p in opt_rows if p.id in pf.source_pricing_ids), None)
        if score_row is None:
            score_row = (routes["stock_egypt"] or routes["stock_outside"]
                         or routes["stock_market_unknown"] or routes["rx"] or opt_rows)[0]
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


_STATUS_ORDER = {"stock_egypt": 0, "stock_outside": 1, "stock_market_unknown": 2, "rx": 3,
                 "split": 4, "eligibility_unknown": 5, "unavailable": 5}
_STATUS_AR = {"stock_egypt": "STOCK داخل مصر", "stock_outside": "STOCK خارج مصر",
              "stock_market_unknown": "STOCK — مكان التوفر غير محدد في الكتالوج",
              "rx": "RX / تصنيع", "split": "مصدر مقسّم (غير موحد)",
              "eligibility_unknown": "التوافق مع الوصفة غير مؤكد (نطاق القوة)",
              "unavailable": "غير متوفر"}
_EYEBEST_AR = {"stock_egypt": "STOCK مصر", "stock_outside": "STOCK خارج مصر",
               "stock_market_unknown": "STOCK — سوق غير محدد",
               "rx": "RX / تصنيع", "unknown": "غير مؤكد (نطاق القوة)", "none": "غير متوفر"}


def _order_key(r: schemas.PerEyeProductResult):
    pf = r.pair_fulfillment
    price = pf.price_pair
    return (_STATUS_ORDER.get(pf.status, 3),
            0 if pf.provenance == "single_route" else 1,   # proven-price pairs first within a tier
            Decimal(str(price)) if price is not None else Decimal("999999999"),
            -float(r.match_score))


_GROUP_DEFS = [
    ("stock_egypt", "🇪🇬 زوج STOCK داخل مصر", "stock", "egypt"),
    ("stock_out_of_egypt", "🌍 زوج STOCK خارج مصر", "stock", "out_of_egypt"),
    ("stock_market_unknown", "❔ زوج STOCK — مكان التوفر غير محدد بالكتالوج", "stock", "unknown"),
    ("rx", "🏭 زوج RX / تصنيع", "rx", None),
    ("split", "⚠️ مصدر غير موحد / غير متوفر للزوج", "mixed", None),
    ("eligibility_unknown", "❓ التوافق مع الوصفة غير مؤكد (نطاق القوة)", "unknown", None),
]
_STATUS_TO_GROUP = {"stock_egypt": "stock_egypt", "stock_outside": "stock_out_of_egypt",
                    "stock_market_unknown": "stock_market_unknown",
                    "rx": "rx", "split": "split", "unavailable": "split",
                    "eligibility_unknown": "eligibility_unknown"}


def _build_groups(ordered: List[schemas.PerEyeProductResult]) -> List[schemas.LensSearchGroup]:
    buckets: Dict[str, List[schemas.PerEyeProductResult]] = {
        "stock_egypt": [], "stock_out_of_egypt": [], "stock_market_unknown": [],
        "rx": [], "split": [], "eligibility_unknown": []}
    for r in ordered:
        buckets[_STATUS_TO_GROUP[r.pair_fulfillment.status]].append(r)
    groups = []
    for key, label, avail, market in _GROUP_DEFS:
        rows = buckets[key]
        groups.append(schemas.LensSearchGroup(
            key=key, label=label, availability=avail, market=market,
            catalog_note=("حسب الكتالوج — مكان التوفر غير محدد" if market == "unknown"
                          else "حسب الكتالوج" if avail == "stock"
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
    if "stock_market_unknown" in statuses:
        # Phase 3C REQUIRED wording: a proven STOCK price/eligibility whose
        # market_scope is NULL in the catalog. Must never claim Egypt, and
        # must never claim Out Of Egypt / "not available inside Egypt" -
        # neither is proven.
        return schemas.AvailabilityAnswer(code="stock_market_unknown",
            title="📦 الزوج متوفر STOCK — مكان التوفر (داخل/خارج مصر) غير محدد في الكتالوج",
            detail="السعر والتوفر STOCK مؤكدان من الكتالوج، لكن السوق غير مذكور في مصدر البيانات.")
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
        if want == "stock" and st not in ("stock_egypt", "stock_outside", "stock_market_unknown"):
            return False
        if want == "rx" and st != "rx":
            return False
    if f.market_scope:
        # An explicit Egypt / Out Of Egypt market filter is a claim about a
        # PROVEN market - "stock_market_unknown" satisfies neither (Phase 3C):
        # it must never pass as if it were the requested market.
        want_eg = market_is_egypt(f.market_scope)
        if want_eg is True and st != "stock_egypt":
            return False
        if want_eg is False and st not in ("stock_outside", "rx"):
            return False
    return True


# --------------------------------------------------- V1.2 use_mode / technology
class _SearchRx:
    """Lightweight, non-persisted stand-in for a prescription's optical
    values, carrying ONLY the attributes the eligibility/scoring engine reads
    from a `models.Prescription` (see product_search.py / lens_matcher.py).
    Used to evaluate a USE-MODE-DERIVED power (e.g. the Reading near Rx)
    without ever mutating the stored prescription row. The real
    `models.Prescription` is always used unchanged for the response's own
    `prescription` field."""
    __slots__ = ("id", "customer_name", "customer_phone", "notes", "pd",
                 "transposition_applied", "od_sph", "od_cyl", "od_axis", "od_add",
                 "os_sph", "os_cyl", "os_axis", "os_add")

    def __init__(self, source: models.Prescription, *,
                 od_sph=None, os_sph=None, od_add=None, os_add=None):
        self.id = source.id
        self.customer_name = source.customer_name
        self.customer_phone = source.customer_phone
        self.notes = source.notes
        self.pd = source.pd
        self.transposition_applied = source.transposition_applied
        self.od_sph = source.od_sph if od_sph is None else od_sph
        self.od_cyl = source.od_cyl
        self.od_axis = source.od_axis
        self.od_add = source.od_add if od_add is None else od_add
        self.os_sph = source.os_sph if os_sph is None else os_sph
        self.os_cyl = source.os_cyl
        self.os_axis = source.os_axis
        self.os_add = source.os_add if os_add is None else os_add


# use_mode -> the hard category boundary it implies (Phase 2). use_mode=None
# (no caller opt-in) leaves category completely unrestricted - the exact
# pre-V1.2 automatic/targeted behaviour, for full backward compatibility.
_USE_MODE_CATEGORY = {
    "distance": "single_vision",
    "reading": "single_vision",
    "bifocal": "bifocal",
    "progressive": "progressive",
}


def _add_missing(value: Optional[float]) -> bool:
    """A clinically real ADD is always > 0; None/0/0.0 all mean "not entered
    for this eye" - never invented, per the V1.2 core-workflow requirement."""
    return value is None or float(value) == 0.0


def _validation_response(prescription: models.Prescription, req: schemas.ProductSearchRequest,
                          use_mode: Optional[str], title: str, detail: str) -> schemas.ProductSearchResponse:
    """A clear, non-fabricated validation failure (missing ADD / unknown
    use_mode) - zero results, zero best_match, never a guessed ADD value."""
    return schemas.ProductSearchResponse(
        prescription=schemas.PrescriptionResponse.model_validate(prescription),
        mode="targeted" if (req.mode or "automatic").strip().lower() == "targeted" else "automatic",
        use_mode=use_mode, technology_intent=req.technology_intent, customer_needs=req.customer_needs,
        transposition_applied=prescription.transposition_applied,
        index_recommendation="", aspherical_recommendation="",
        availability_answer=schemas.AvailabilityAnswer(code="validation_error", title=title, detail=detail),
        exact_total=0, best_match=None, groups=[])


# ---------------------------------------------------------------- entry point
def search(db: Session, prescription: models.Prescription,
           req: schemas.ProductSearchRequest) -> schemas.ProductSearchResponse:
    targeted = (req.mode or "automatic").strip().lower() == "targeted"
    filters = req.filters if targeted else None

    # Request-local copies: never rewrite the caller's advanced filters.
    filters = filters.model_copy(deep=True) if filters is not None else None
    if not customer_needs.valid_rx(prescription):
        return _validation_response(prescription, req, req.use_mode,
            "الوصفة غير صالحة", "راجع قيم SPH / CYL / AXIS / ADD لكل عين.")
    need = req.customer_need
    if req.customer_needs is not None and need is None:
        need = "none"
        req = req.model_copy(update={"customer_need": need})
    tech = req.technology_intent or "none"
    if need not in (None, *customer_needs.LABELS) or tech not in technology_evidence.INTENTS:
        return _validation_response(prescription, req, req.use_mode,
            "احتياج أو تقنية غير معروف", "اختر احتياجاً وتقنية من الخيارات المعتمدة.")
    if need == "best_optical_clarity":
        return _validation_response(prescription, req, req.use_mode,
            "الدليل الكتالوجي غير كافٍ", "لا يوجد دليل مقارنة مثبت يسمح بتوصية أفضل نقاء بصري.")
    required_tech = customer_needs.TECHNOLOGY.get(need)
    if required_tech:
        if tech == "none":
            tech = required_tech
        elif not technology_evidence.satisfies(required_tech,
                technology_evidence.missing_capabilities(tech, set())):
            return _validation_response(prescription, req, req.use_mode,
                "تعارض الاحتياج والتقنية", "التقنية المختارة لا تحقق احتياج العميل؛ راجع الاختيار.")
    req = req.model_copy(update={"technology_intent": tech})

    use_mode = (req.use_mode or "").strip().lower() or None
    if need is not None and use_mode is None:
        return _validation_response(prescription, req, use_mode,
            "حدد نوع الاستخدام", "اختر الأبعد أو القراءة أو ثنائي البؤرة أو المتدرج قبل التوصية.")
    derived_category: Optional[str] = None
    derived_rx: Optional[schemas.DerivedSearchRx] = None
    search_prescription: models.Prescription = prescription

    if use_mode is not None:
        if use_mode not in _USE_MODE_CATEGORY:
            return _validation_response(prescription, req, use_mode,
                "نوع استخدام غير معروف",
                f"القيمة '{use_mode}' غير معروفة. استخدم distance / reading / bifocal / progressive.")
        derived_category = _USE_MODE_CATEGORY[use_mode]

        if use_mode == "distance":
            # ADD must NEVER affect Single Vision Distance eligibility.
            search_prescription = _SearchRx(prescription, od_add=0.0, os_add=0.0)
        elif use_mode == "reading":
            if _add_missing(prescription.od_add) or _add_missing(prescription.os_add):
                return _validation_response(prescription, req, use_mode,
                    "بيانات القراءة غير مكتملة",
                    "قوة القراءة (ADD) غير موجودة لكل عين في هذه الوصفة. لا يمكن حساب بحث القراءة بدون ADD - أضِفه في الوصفة الأصلية أولاً.")
            od_reading_sph = round(prescription.od_sph + prescription.od_add, 2)
            os_reading_sph = round(prescription.os_sph + prescription.os_add, 2)
            # Near Rx IS the full search-power already (Distance SPH + ADD) -
            # it carries no further ADD of its own, so ADD is forced to 0 here
            # too (same reason as Distance: a single_vision range never checks
            # add_min/add_max, and forcing 0 keeps that branch inert either way).
            search_prescription = _SearchRx(prescription, od_sph=od_reading_sph, os_sph=os_reading_sph,
                                             od_add=0.0, os_add=0.0)
            derived_rx = schemas.DerivedSearchRx(
                od_sph=od_reading_sph, od_cyl=prescription.od_cyl or 0.0, od_axis=prescription.od_axis or 0,
                os_sph=os_reading_sph, os_cyl=prescription.os_cyl or 0.0, os_axis=prescription.os_axis or 0)
        else:  # bifocal / progressive - ORIGINAL Distance Rx + ADD, unchanged
            if _add_missing(prescription.od_add) or _add_missing(prescription.os_add):
                label = "Bifocal" if use_mode == "bifocal" else "Progressive"
                return _validation_response(prescription, req, use_mode,
                    f"بيانات {label} غير مكتملة",
                    f"قوة الـ ADD غير موجودة لكل عين في هذه الوصفة. {label} يحتاج ADD لكل عين - أضِفه في الوصفة الأصلية أولاً.")
            # no derivation: the stored od_sph/os_sph/od_add/os_add already ARE
            # "Distance Rx + ADD" - search_prescription stays = prescription.

        # targeted mode: fold the use_mode category into the employee's own
        # filters so the EXISTING category-hard-boundary machinery (exact-gate
        # + compute_alternatives) enforces it with no new code path; use_mode
        # is authoritative over any independently-chosen "الفئة" value.
        if filters is not None:
            if filters.category is not None and getattr(filters.category, "value", filters.category) != derived_category:
                return _validation_response(prescription, req, use_mode,
                    "تعارض الفئة ونوع الاستخدام", "اختر فئة متوافقة مع نوع الاستخدام؛ لا يتم تجاوز المرشحات.")
            filters.category = derived_category

    max_sph = max(abs(search_prescription.od_sph), abs(search_prescription.os_sph))
    max_cyl = max(abs(search_prescription.od_cyl or 0), abs(search_prescription.os_cyl or 0))
    rec_index, index_desc = lens_matcher.recommender.recommend_index(max_sph)
    need_asph, aspherical_desc = lens_matcher.recommender.recommend_aspherical(max_sph, max_cyl)

    # per-eye / pair analysis for every commercial option that satisfies the
    # IDENTITY filters (company / product / index / category / design / coating /
    # colour-technology). Availability / market / max_price are NOT applied here.
    options = _per_eye_results(db, search_prescription, filters, req, rec_index, need_asph,
                                derived_category=derived_category if filters is None else None,
                                technology_intent=req.technology_intent)

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

        if not exact and not intel and req.include_alternatives and need is None and tech == "none" and use_mode is None:
            all_results, *_ = lens_matcher.match_lenses(
                db, search_prescription, None, req.prefer_stock, req.prefer_aspherical)
            # Phase 3C: an alternative must be prescription-safe too - a
            # candidate whose power_eligibility is UNRESOLVED (or genuinely
            # ineligible) is never a usable fallback, never offered as a
            # priced recommendation.
            all_results = _proven_eligible_for_alternatives(
                db, all_results, search_prescription, filters.applicability_key if filters else None)
            alternatives = compute_alternatives(all_results, set(), filters)
            if alternatives:
                alt_note = ("لا يوجد مطابق تام للمواصفات المطلوبة؛ هذه أقرب البدائل تجارياً "
                            "وهي ليست مطابقات تامة.")

    # SV manufacturing is fallback only, after every exact-request gate.
    if use_mode in ("distance", "reading") and any(
            r.pair_fulfillment.status in ("stock_egypt", "stock_outside")
            and customer_needs.actionable(r) for r in exact):
        exact = [r for r in exact if r.pair_fulfillment.status != "rx"]

    # Location is catalog/business identity, including pending matching offers;
    # it does not grant actionability or a confirmed price.
    for r in exact:
        if customer_needs.local_manufacturing(r):
            r.manufacturing_location = "egypt"
    ordered = sorted(exact, key=_order_key)
    # Informational groups retain their existing availability/price semantics.
    # Only proven, fully priced pairs enter the seller recommendation ranking.
    recommended = sorted((r for r in exact if customer_needs.actionable(r)),
                         key=_order_key if targeted else customer_needs.seller_order)
    for r in recommended:
        r.seller_recommendation_reason = customer_needs.seller_reason(r, need, tech)
    groups = _build_groups(ordered)
    answer = _answer(ordered)

    if not ordered and intel:
        want_bits = []
        if filters and filters.availability is not None:
            want_bits.append(getattr(filters.availability, "value", filters.availability).upper())
        if filters and filters.market_scope:
            want_bits.append(filters.market_scope)
        want = " / ".join(want_bits) if want_bits else "المواصفات المطلوبة"
        # V1: when the user explicitly asked for STOCK and none exists, but the
        # SAME requested product (identity-filtered `intel`, never a different
        # company/product) is PROVEN available as RX, say so directly as the
        # primary answer instead of a generic "not available" - the employee
        # should not have to open "same product availability" to learn this.
        # A merely UNRESOLVED intel row (eligibility_unknown) never qualifies -
        # only a genuinely proven "rx" status does. This changes which message
        # is chosen, never which rows are proven/matched/priced.
        requested_stock = (filters is not None and filters.availability is not None
                           and getattr(filters.availability, "value", filters.availability) == "stock")
        rx_proven = requested_stock and any(r.pair_fulfillment.status == "rx" for r in intel)
        if rx_proven:
            answer = schemas.AvailabilityAnswer(
                code="rx_only",
                title="🏭 غير متوفر STOCK — متاح RX / تصنيع",
                detail="راجع «توفر نفس المنتج» أدناه لتفاصيل السعر والطلاء.")
        else:
            answer = schemas.AvailabilityAnswer(
                code="none",
                title=f"❌ غير متوفر بهذه المواصفات ({want})",
                detail="راجع «توفر نفس المنتج» أدناه — نفس المنتج متاح خارج المطلوب.")

    counts = {"stock_egypt": 0, "stock_out_of_egypt": 0, "stock_market_unknown": 0,
              "rx": 0, "split": 0, "eligibility_unknown": 0}
    for r in ordered:
        counts[_STATUS_TO_GROUP[r.pair_fulfillment.status]] += 1

    _search_category = derived_category
    if filters is not None and filters.category is not None:
        _search_category = getattr(filters.category, "value", filters.category)
    unverified = _stock_egypt_range_unverified(
        db, _search_category, filters, req.technology_intent,
        req.customer_need, req.customer_needs)

    return schemas.ProductSearchResponse(
        prescription=schemas.PrescriptionResponse.model_validate(prescription),
        mode="targeted" if targeted else "automatic",
        use_mode=use_mode, technology_intent=req.technology_intent, derived_search_rx=derived_rx,
        customer_needs=req.customer_needs,
        transposition_applied=prescription.transposition_applied,
        index_recommendation=index_desc, aspherical_recommendation=aspherical_desc,
        availability_answer=answer, exact_total=len(ordered),
        # Legacy clients omit customer_need and retain the informational best
        # result contract. The seller UI always sends it, including "none".
        best_match=((recommended[0] if recommended else None) if need is not None
                    else (ordered[0] if ordered else None)), groups=groups,
        customer_need=need, seller_alternatives=recommended[1:3],
        stock_egypt_count=counts["stock_egypt"],
        stock_out_of_egypt_count=counts["stock_out_of_egypt"],
        stock_market_unknown_count=counts["stock_market_unknown"],
        eligibility_unknown_count=counts["eligibility_unknown"],
        rx_count=counts["rx"], split_count=counts["split"],
        alternatives=alternatives, alternatives_note=alt_note,
        availability_intelligence=intel, availability_intelligence_note=intel_note,
        stock_egypt_unverified=unverified)
