"""Permanent regression coverage for the Synchrony By ZEISS Phase 3 import.

Deliberately synthetic, mirroring the corrected shape directly via the ORM
(no PDF parsing, no dependency on the live optical_lens.db), matching the
same pattern as test_pixel_page16_page17_reconciliation.py.
"""
import os
import sys
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database import Base  # noqa: E402
from app import models, database, schemas, product_search  # noqa: E402


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    event.listen(engine, "connect", database._set_sqlite_pragma)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _mk_company(db, name):
    co = models.Company(name=name, country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    return co


def _mk_catalog(db, company):
    cat = models.Catalog(company_id=company.id, filename="synthetic.pdf",
                         file_path="synthetic.pdf", status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)
    return cat


def _mk_model(db, company, name, category):
    m = models.LensModel(company_id=company.id, name=name, category=category)
    db.add(m); db.commit(); db.refresh(m)
    return m


def _mk_variant(db, model, index_value, design_variant=None, treatment_band=None,
                design_type=models.DesignType.SPHERICAL, is_aspherical=False):
    v = models.LensVariant(
        lens_model_id=model.id, material=models.MaterialType.CR39, index_value=index_value,
        design_type=design_type, is_aspherical=is_aspherical,
        design_variant=design_variant, treatment_band=treatment_band, price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    return v


def _mk_pricing(db, variant, catalog, *, availability, price,
                power_eligibility=models.PowerEligibilityStatus.UNRESTRICTED,
                market_scope=None):
    vp = models.VariantPricing(
        variant_id=variant.id, coating_id=None, availability=availability,
        power_eligibility=power_eligibility, price_pair=Decimal(str(price)),
        currency="EGP", source_catalog_id=catalog.id, market_scope=market_scope)
    db.add(vp); db.commit(); db.refresh(vp)
    return vp


def _mk_range(db, model, variant, pricing, sph_min, sph_max, cyl_min, cyl_max):
    pr = models.PowerRange(lens_model_id=model.id, variant_id=variant.id, pricing_id=pricing.id,
                           sph_min=sph_min, sph_max=sph_max, cyl_min=cyl_min, cyl_max=cyl_max)
    db.add(pr); db.commit()
    return pr


def _mk_presc(db, sph, cyl=0.0, name="p"):
    p = models.Prescription(
        customer_name=name, od_sph_original=sph, od_cyl_original=cyl, od_axis_original=0,
        od_sph=sph, od_cyl=cyl, od_axis=0, os_sph_original=sph, os_cyl_original=cyl,
        os_axis_original=0, os_sph=sph, os_cyl=cyl, os_axis=0, pd=63)
    db.add(p); db.commit(); db.refresh(p)
    return p


def _targeted(db, presc, **filters):
    f = schemas.LensFilters(**filters)
    req = schemas.ProductSearchRequest(mode="targeted", filters=f, include_alternatives=True)
    return product_search.search(db, presc, req)


@pytest.fixture()
def synchrony_setup(db):
    co = _mk_company(db, "Synchrony")
    cat = _mk_catalog(db, co)
    sv = _mk_model(db, co, "Synchrony", models.LensCategory.SINGLE_VISION)
    prog = _mk_model(db, co, "Synchrony", models.LensCategory.PROGRESSIVE)

    # STOCK 1.56 AS - 2 stepped bands (minus + plus), unrestricted eligibility
    # (real PowerRanges make the flag irrelevant, matching the live import).
    v_as = _mk_variant(db, sv, 1.56, design_type=models.DesignType.ASPHERICAL, is_aspherical=True)
    p_as = _mk_pricing(db, v_as, cat, availability=models.PricingAvailability.STOCK, price=850)
    _mk_range(db, sv, v_as, p_as, -4.00, 0.00, -4.00, 0.00)
    _mk_range(db, sv, v_as, p_as, 0.25, 4.00, -2.00, 0.00)

    # STOCK 1.67 AS -Power, Out Of Egypt - 9 stepped bands, no plus side at all.
    v_167 = _mk_variant(db, sv, 1.67, design_type=models.DesignType.ASPHERICAL, is_aspherical=True)
    p_167 = _mk_pricing(db, v_167, cat, availability=models.PricingAvailability.STOCK, price=2800,
                        market_scope="Out Of Egypt")
    bands_167 = [
        (-8.00, -2.00, -2.00, 0.00), (-8.25, -8.25, -1.75, 0.00), (-8.50, -8.50, -1.50, 0.00),
        (-8.75, -8.75, -1.25, 0.00), (-9.00, -9.00, -1.00, 0.00), (-9.25, -9.25, -0.75, 0.00),
        (-9.50, -9.50, -0.50, 0.00), (-9.75, -9.75, -0.25, 0.00), (-12.00, -10.00, 0.00, 0.00),
    ]
    for sph_min, sph_max, cyl_min, cyl_max in bands_167:
        _mk_range(db, sv, v_167, p_167, sph_min, sph_max, cyl_min, cyl_max)

    # RX Single Vision Free Form 1.50 - no range at all -> UNRESOLVED
    v_ff = _mk_variant(db, sv, 1.50, design_variant="Free Form")
    p_ff = _mk_pricing(db, v_ff, cat, availability=models.PricingAvailability.RX, price=3960,
                       power_eligibility=models.PowerEligibilityStatus.UNRESOLVED)

    # RX Progressive Easy 1.50 - no ADD range at all -> UNRESOLVED
    v_easy = _mk_variant(db, prog, 1.50, design_variant="Easy")
    p_easy = _mk_pricing(db, v_easy, cat, availability=models.PricingAvailability.RX, price=4250,
                         power_eligibility=models.PowerEligibilityStatus.UNRESOLVED)

    return {"company": co, "sv": sv, "prog": prog,
            "v_as": v_as, "p_as": p_as, "v_167": v_167, "p_167": p_167,
            "v_ff": v_ff, "p_ff": p_ff, "v_easy": v_easy, "p_easy": p_easy}


# A. Synchrony is its own company - never HOYA/ZEISS/PIXEL's id, and no
# parent-brand relationship exists anywhere on the model.
def test_A_synchrony_is_independent_company(db, synchrony_setup):
    co = synchrony_setup["company"]
    assert co.name == "Synchrony"
    assert not hasattr(models.Company, "parent_company_id")


# B. Category mapping: single_vision and progressive, two distinct LensModel
# rows under the same company/name.
def test_B_category_mapping(db, synchrony_setup):
    sv, prog = synchrony_setup["sv"], synchrony_setup["prog"]
    assert sv.category == models.LensCategory.SINGLE_VISION
    assert prog.category == models.LensCategory.PROGRESSIVE
    assert sv.id != prog.id
    assert sv.company_id == prog.company_id


# C. Proven STOCK bands are all eligible; a prescription inside any printed
# band returns a proven match, never approximated to one rectangle.
def test_C_1_56_AS_stepped_bands(db, synchrony_setup):
    sv = synchrony_setup["sv"]
    for sph, cyl, expect in [(-2.0, -2.0, True), (2.0, -1.0, True), (-5.0, 0.0, False)]:
        presc = _mk_presc(db, sph, cyl, name=f"c-{sph}-{cyl}")
        resp = _targeted(db, presc, company_id=sv.company_id,
                         category=models.LensCategory.SINGLE_VISION, index_value=1.56)
        assert (resp.exact_total > 0) == expect, (sph, cyl)


# D. 1.67 AS -Power's tight stepped tail is honored exactly - a power just
# past the printed step is ineligible, never silently widened.
def test_D_1_67_AS_stepped_tail_exact(db, synchrony_setup):
    sv = synchrony_setup["sv"]
    for sph, cyl, expect in [
        (-8.30, -1.75, True),    # inside the -8.25 row's own cyl width
        (-8.30, -2.50, False),   # clearly past that row's cyl width (beyond the 0.25D tolerance too)
        (-11.0, 0.0, True),      # inside the flat cyl=0-only tail
        (-11.0, -0.75, False),   # clearly past the tail's cyl=0-only width
    ]:
        presc = _mk_presc(db, sph, cyl, name=f"d-{sph}-{cyl}")
        resp = _targeted(db, presc, company_id=sv.company_id,
                         category=models.LensCategory.SINGLE_VISION, index_value=1.67)
        assert (resp.exact_total > 0) == expect, (sph, cyl)


# E. RX Single Vision with no range: per the permanent domain rule (RX
# manufacturing eligibility is NOT dependent on a printed range by default),
# a made-to-order RX row with zero PowerRange is now ALWAYS eligible and its
# catalog price is shown directly - never "unresolved", regardless of the
# power_eligibility flag on the row.
def test_E_rx_single_vision_unresolved(db, synchrony_setup):
    sv = synchrony_setup["sv"]
    v_ff = synchrony_setup["v_ff"]
    p_ff = synchrony_setup["p_ff"]
    presc = _mk_presc(db, -2.0, name="e-pinned")
    resp = _targeted(db, presc, lens_model_id=sv.id, index_value=1.50, design_variant="Free Form")
    assert resp.availability_answer.code == "rx_only"
    assert resp.best_match.pair_fulfillment.status == "rx"
    assert resp.best_match.pair_fulfillment.price_pair == p_ff.price_pair

    presc2 = _mk_presc(db, -2.0, name="e-unpinned")
    resp2 = _targeted(db, presc2, company_id=sv.company_id,
                      category=models.LensCategory.SINGLE_VISION, index_value=1.50)
    assert resp2.exact_total > 0


# F. Progressive with no ADD range: same made-to-order RX rule - eligible,
# priced directly, never a fabricated ADD range and never "unresolved".
def test_F_progressive_unresolved(db, synchrony_setup):
    prog = synchrony_setup["prog"]
    presc = _mk_presc(db, -2.0, cyl=0.0, name="f-pinned")
    resp = _targeted(db, presc, lens_model_id=prog.id, index_value=1.50, design_variant="Easy")
    assert resp.availability_answer.code == "rx_only"
    assert resp.best_match.pair_fulfillment.status == "rx"
    assert resp.best_match.pair_fulfillment.price_pair is not None


# G. Category is a hard boundary for Synchrony too - a single_vision search
# never shows a progressive Synchrony row as an alternative.
def test_G_category_hard_boundary(db, synchrony_setup):
    sv = synchrony_setup["sv"]
    presc = _mk_presc(db, -30.0, name="g-impossible")
    f = schemas.LensFilters(company_id=sv.company_id, category=models.LensCategory.SINGLE_VISION)
    req = schemas.ProductSearchRequest(mode="targeted", filters=f, include_alternatives=True)
    resp = product_search.search(db, presc, req)
    for alt in (resp.alternatives or []):
        assert alt.result.lens_model.category == models.LensCategory.SINGLE_VISION


# H. No cross-company contamination: a Synchrony-scoped search never returns
# a different company's row, and vice versa.
def test_H_no_cross_company_contamination(db, synchrony_setup):
    sv = synchrony_setup["sv"]
    other_co = _mk_company(db, "OtherCo")
    other_cat = _mk_catalog(db, other_co)
    other_model = _mk_model(db, other_co, "OtherCo", models.LensCategory.SINGLE_VISION)
    v_other = _mk_variant(db, other_model, 1.56, design_type=models.DesignType.ASPHERICAL, is_aspherical=True)
    p_other = _mk_pricing(db, v_other, other_cat, availability=models.PricingAvailability.STOCK, price=500)
    _mk_range(db, other_model, v_other, p_other, -4.00, 0.00, -4.00, 0.00)

    presc = _mk_presc(db, -2.0, name="h")
    f = schemas.LensFilters(company_id=sv.company_id, category=models.LensCategory.SINGLE_VISION, index_value=1.56)
    req = schemas.ProductSearchRequest(mode="targeted", filters=f, include_alternatives=True)
    resp = product_search.search(db, presc, req)
    for grp in resp.groups:
        for r in grp.results:
            assert r.company_id == sv.company_id


# ---------------------------------------------------------------------------
# Phase 3C - GENERIC UNKNOWN MARKET FIX regression tests (Section 5, A-F).
#
# market_is_egypt(None) already returned None ("unspecified") per its own
# docstring, but every consumer used to collapse "not True" (including None)
# into "stock_outside" - silently claiming a proven Out Of Egypt market for a
# STOCK row whose catalog simply never states a market. These 6 tests lock in
# the fix: a NULL market_scope STOCK row is now its own honest tier,
# "stock_market_unknown" - never stock_egypt, never stock_outside, and never
# discarded as ineligible just because its market is unstated. The fix lives
# entirely in product_search.py's generic route/tier machinery - nothing here
# is Synchrony-specific; a synthetic non-Synchrony company (test N) proves
# that.
# ---------------------------------------------------------------------------

# I. STOCK + explicit Egypt market_scope -> stock_egypt, unchanged by the fix.
def test_I_stock_egypt_market_unchanged(db, synchrony_setup):
    sv = synchrony_setup["sv"]
    v_eg = _mk_variant(db, sv, 1.60, design_variant="EgyptStock")
    cat = db.query(models.Catalog).filter_by(company_id=sv.company_id).first()
    p_eg = _mk_pricing(db, v_eg, cat, availability=models.PricingAvailability.STOCK, price=900,
                       market_scope="Egypt")
    _mk_range(db, sv, v_eg, p_eg, -4.00, 0.00, -4.00, 0.00)

    presc = _mk_presc(db, -2.0, -2.0, name="i-egypt")
    resp = _targeted(db, presc, lens_model_id=sv.id, index_value=1.60, design_variant="EgyptStock")
    assert resp.exact_total > 0
    assert resp.best_match.pair_fulfillment.status == "stock_egypt"
    assert resp.availability_answer.code == "stock_egypt"
    assert resp.stock_egypt_count > 0
    assert resp.stock_market_unknown_count == 0


# J. STOCK + explicit "Out Of Egypt" market_scope -> stock_outside, unchanged.
def test_J_stock_outside_market_unchanged(db, synchrony_setup):
    sv, v_167 = synchrony_setup["sv"], synchrony_setup["v_167"]
    presc = _mk_presc(db, -3.0, 0.0, name="j-outside")
    resp = _targeted(db, presc, lens_model_id=sv.id, index_value=1.67)
    assert resp.exact_total > 0
    assert resp.best_match.pair_fulfillment.status == "stock_outside"
    assert resp.availability_answer.code == "stock_out_of_egypt"
    assert resp.stock_out_of_egypt_count > 0
    assert resp.stock_market_unknown_count == 0


# K. STOCK + NULL market_scope -> the new honest "stock_market_unknown" tier -
# NEVER "stock_outside", and the answer NEVER claims the pair is unavailable
# inside Egypt or confirmed outside it.
def test_K_stock_null_market_is_unknown_not_outside(db, synchrony_setup):
    sv = synchrony_setup["sv"]
    assert synchrony_setup["p_as"].market_scope is None   # fixture precondition
    presc = _mk_presc(db, -2.0, -2.0, name="k-null-market")
    resp = _targeted(db, presc, lens_model_id=sv.id, index_value=1.56)
    assert resp.exact_total > 0
    pf = resp.best_match.pair_fulfillment
    assert pf.status == "stock_market_unknown"
    assert pf.status != "stock_outside"
    assert resp.availability_answer.code == "stock_market_unknown"
    # must never assert the confirmed-Out-Of-Egypt wording, nor claim the pair
    # is unavailable inside Egypt - neither claim is proven for a NULL market.
    assert resp.availability_answer.code != "stock_out_of_egypt"
    assert "غير متوفر داخل مصر" not in resp.availability_answer.title
    assert resp.stock_market_unknown_count > 0
    assert resp.stock_out_of_egypt_count == 0


# L. Synchrony 1.56 AS inside its proven PowerRange remains optically
# eligible with market_scope=NULL - a proven-eligible unknown-market STOCK
# row must still be an actionable Best Choice (price_pair set, both-eyes
# proven), not discarded merely because the market is unspecified.
def test_L_1_56_AS_null_market_still_optically_eligible(db, synchrony_setup):
    sv = synchrony_setup["sv"]
    presc = _mk_presc(db, -2.0, -2.0, name="l-actionable")
    resp = _targeted(db, presc, lens_model_id=sv.id, index_value=1.56)
    best = resp.best_match
    assert best is not None
    assert best.od.stock_market_unknown is True
    assert best.os.stock_market_unknown is True
    assert best.od.stock_outside is False and best.os.stock_outside is False
    assert best.pair_fulfillment.status == "stock_market_unknown"
    assert best.pair_fulfillment.price_pair is not None   # proven, priced, actionable


# M. A STOCK row with a confirmed price but ZERO PowerRange rows (the Blue
# HMC+ shape) stays a NON-actionable, unproven optical match regardless of
# market_scope - the Phase 3C fix must never turn "no range" into a false
# eligibility just because the market is also unknown.
def test_M_stock_no_range_still_not_actionable(db, synchrony_setup):
    sv = synchrony_setup["sv"]
    cat = db.query(models.Catalog).filter_by(company_id=sv.company_id).first()
    v_blue = _mk_variant(db, sv, 1.60, design_variant="BlueHMCPlus")
    _mk_pricing(db, v_blue, cat, availability=models.PricingAvailability.STOCK, price=2300,
               market_scope=None)   # confirmed price, no range - like Blue HMC+

    presc = _mk_presc(db, -2.0, 0.0, name="m-no-range")
    resp = _targeted(db, presc, lens_model_id=sv.id, index_value=1.60, design_variant="BlueHMCPlus")
    assert resp.best_match.pair_fulfillment.status not in ("stock_market_unknown", "stock_egypt", "stock_outside", "rx")
    assert resp.best_match.pair_fulfillment.price_pair is None

    presc2 = _mk_presc(db, -2.0, 0.0, name="m-no-range-unpinned")
    resp2 = _targeted(db, presc2, company_id=sv.company_id,
                      category=models.LensCategory.SINGLE_VISION, index_value=1.60,
                      design_variant="BlueHMCPlus")
    assert resp2.exact_total == 0   # never a proven automatic/exact match


# N. HOYA/ZEISS/PIXEL behavior unchanged: this is a GENERIC fix, not
# Synchrony-specific - a synthetic non-Synchrony company's NULL-market STOCK
# row gets the SAME honest "stock_market_unknown" tier (proving no
# manufacturer-specific branch exists), while its explicit Egypt / Out Of
# Egypt rows behave exactly as before.
def test_N_generic_fix_not_synchrony_specific(db):
    co = _mk_company(db, "HOYA-Like")
    cat = _mk_catalog(db, co)
    m = _mk_model(db, co, "HOYA-Like Model", models.LensCategory.SINGLE_VISION)

    v_null = _mk_variant(db, m, 1.56, design_variant="NullMarket")
    p_null = _mk_pricing(db, v_null, cat, availability=models.PricingAvailability.STOCK, price=700,
                         market_scope=None)
    _mk_range(db, m, v_null, p_null, -4.00, 0.00, -4.00, 0.00)

    v_eg = _mk_variant(db, m, 1.56, design_variant="EgyptMarket")
    p_eg = _mk_pricing(db, v_eg, cat, availability=models.PricingAvailability.STOCK, price=700,
                       market_scope="Egypt")
    _mk_range(db, m, v_eg, p_eg, -4.00, 0.00, -4.00, 0.00)

    presc_null = _mk_presc(db, -2.0, -2.0, name="n-null")
    resp_null = _targeted(db, presc_null, lens_model_id=m.id, index_value=1.56, design_variant="NullMarket")
    assert resp_null.best_match.pair_fulfillment.status == "stock_market_unknown"

    presc_eg = _mk_presc(db, -2.0, -2.0, name="n-egypt")
    resp_eg = _targeted(db, presc_eg, lens_model_id=m.id, index_value=1.56, design_variant="EgyptMarket")
    assert resp_eg.best_match.pair_fulfillment.status == "stock_egypt"
