"""Permanent regression coverage for the Maxxee By Hoya canonical import.

Deliberately synthetic, mirroring the corrected shape directly via the ORM
(no PDF parsing, no dependency on the live optical_lens.db), matching the
same pattern as test_synchrony_import.py / test_pixel_page16_page17_reconciliation.py.

Maxxee's catalog structurally requires something no prior manufacturer's
import needed: the SAME commercial identity (product + index + coating)
printed with TWO DIFFERENT prices, one per PowerRange price band (a dotted
line on the printed page separates them - never two products, never an
Egypt-vs-Outside split). The architecture already supports this via
VariantPricing.power_scope (a partial-unique index lets several
simultaneously-CURRENT rows share one identity as long as their power_scope
differs) - these tests lock that in, including the "overlapping bands must
never resolve to an arbitrary price" fix this import surfaced in
_pair_fulfillment (product_search.py): when more than one proven
single-route price band covers the SAME prescription, the cheapest one must
always win, deterministically - never whichever row a DB query happened to
return first.
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
from app import models, database, schemas, product_search, crud  # noqa: E402


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


def _mk_coating(db, code):
    c = models.Coating(code=code, name=code)
    db.add(c); db.commit(); db.refresh(c)
    return c


def _mk_variant(db, model, index_value, design_variant=None, treatment_band=None,
                color_variant=None, design_tier=None,
                design_type=models.DesignType.SPHERICAL, is_aspherical=False,
                material=models.MaterialType.CR39):
    v = models.LensVariant(
        lens_model_id=model.id, material=material, index_value=index_value,
        design_type=design_type, is_aspherical=is_aspherical,
        design_variant=design_variant, treatment_band=treatment_band,
        color_variant=color_variant, design_tier=design_tier, price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    return v


def _mk_pricing(db, variant, catalog, *, availability, price, coating=None, market_scope=None,
                power_scope_bounds=None):
    """power_scope_bounds: (sph_min, sph_max, cyl_min, cyl_max, add_min, add_max,
    total_power_min, total_power_max, max_cyl_abs) - the SAME tuple shape
    build_power_scope takes, so two price bands of one identity naturally get
    two different power_scope values and can coexist as separate current rows."""
    power_scope = crud.build_power_scope(*power_scope_bounds) if power_scope_bounds else None
    vp = models.VariantPricing(
        variant_id=variant.id, coating_id=(coating.id if coating else None),
        availability=availability, price_pair=Decimal(str(price)),
        currency="EGP", source_catalog_id=catalog.id, market_scope=market_scope,
        power_scope=power_scope)
    db.add(vp); db.commit(); db.refresh(vp)
    return vp


def _mk_range(db, model, variant, pricing, sph_min=0.0, sph_max=0.0, cyl_min=-10.0, cyl_max=0.0,
             add_min=None, add_max=None, total_power_min=None, total_power_max=None,
             max_cyl_abs=None):
    pr = models.PowerRange(lens_model_id=model.id, variant_id=variant.id, pricing_id=pricing.id,
                           sph_min=sph_min, sph_max=sph_max, cyl_min=cyl_min, cyl_max=cyl_max,
                           add_min=add_min, add_max=add_max,
                           total_power_min=total_power_min, total_power_max=total_power_max,
                           max_cyl_abs=max_cyl_abs)
    db.add(pr); db.commit()
    return pr


def _mk_presc(db, sph, cyl=0.0, add=None, name="p"):
    p = models.Prescription(
        customer_name=name, od_sph_original=sph, od_cyl_original=cyl, od_axis_original=0,
        od_sph=sph, od_cyl=cyl, od_axis=0, od_add=add, os_sph_original=sph, os_cyl_original=cyl,
        os_axis_original=0, os_sph=sph, os_cyl=cyl, os_axis=0, os_add=add, pd=63)
    db.add(p); db.commit(); db.refresh(p)
    return p


def _targeted(db, presc, **filters):
    f = schemas.LensFilters(**filters)
    req = schemas.ProductSearchRequest(mode="targeted", filters=f, include_alternatives=True)
    return product_search.search(db, presc, req)


@pytest.fixture()
def maxxee_setup(db):
    co = _mk_company(db, "Maxxee")
    cat = _mk_catalog(db, co)
    sv = _mk_model(db, co, "Maxxee", models.LensCategory.SINGLE_VISION)
    prog = _mk_model(db, co, "Maxxee", models.LensCategory.PROGRESSIVE)
    hmc = _mk_coating(db, "H.M.C")
    hmc_plus = _mk_coating(db, "H.M.C+")
    blue_uv = _mk_coating(db, "Blue U.V")

    # --- Maxxee SPH 1.5 H.M.C - 2 STOCK Egypt price bands (page 2 pattern) ---
    # Band A (700): sph 0..-4, cyl 0..-2.  Band B (800): sph 0..-3, cyl 0..-4.
    # These OVERLAP for a low-cyl prescription inside both sph windows.
    v_hmc = _mk_variant(db, sv, 1.50)
    pA = _mk_pricing(db, v_hmc, cat, availability=models.PricingAvailability.STOCK, price=700,
                     coating=hmc, market_scope="Egypt",
                     power_scope_bounds=(-4.0, 0.0, -2.0, 0.0, None, None, None, None, None))
    _mk_range(db, sv, v_hmc, pA, -4.0, 0.0, -2.0, 0.0)
    pB = _mk_pricing(db, v_hmc, cat, availability=models.PricingAvailability.STOCK, price=800,
                     coating=hmc, market_scope="Egypt",
                     power_scope_bounds=(-3.0, 0.0, -4.0, 0.0, None, None, None, None, None))
    _mk_range(db, sv, v_hmc, pB, -3.0, 0.0, -4.0, 0.0)

    # --- Maxxee SPH 1.5 Blue U.V - 2 STOCK Egypt price bands (own coating) ---
    v_uv = v_hmc  # same LensVariant identity - coating differs at the pricing level only
    pC = _mk_pricing(db, v_uv, cat, availability=models.PricingAvailability.STOCK, price=1250,
                     coating=blue_uv, market_scope="Egypt",
                     power_scope_bounds=(-3.0, 0.0, -2.0, 0.0, None, None, None, None, None))
    _mk_range(db, sv, v_uv, pC, -3.0, 0.0, -2.0, 0.0)
    pD = _mk_pricing(db, v_uv, cat, availability=models.PricingAvailability.STOCK, price=1350,
                     coating=blue_uv, market_scope="Egypt",
                     power_scope_bounds=(-2.0, 0.0, -4.0, 0.0, None, None, None, None, None))
    _mk_range(db, sv, v_uv, pD, -2.0, 0.0, -4.0, 0.0)

    # --- Maxxee ASPH 1.6 (+) H.M.C+ - 2 STOCK Egypt price bands, one plain
    # plus-cyl box (2450) and one G3 total-power/max-cyl clause (2550) ---
    v_asph = _mk_variant(db, sv, 1.60, design_type=models.DesignType.ASPHERICAL, is_aspherical=True)
    pE = _mk_pricing(db, v_asph, cat, availability=models.PricingAvailability.STOCK, price=2450,
                     coating=hmc_plus, market_scope="Egypt",
                     power_scope_bounds=(0.0, 4.0, 0.0, 2.0, None, None, None, None, None))
    _mk_range(db, sv, v_asph, pE, 0.0, 4.0, 0.0, 2.0)
    pF = _mk_pricing(db, v_asph, cat, availability=models.PricingAvailability.STOCK, price=2550,
                     coating=hmc_plus, market_scope="Egypt",
                     power_scope_bounds=(None, None, None, None, None, None, None, 6.0, 3.0))
    _mk_range(db, sv, v_asph, pF, 0.0, 9.0, -3.0, 0.0, total_power_max=6.0, max_cyl_abs=3.0)

    # --- Maxxee SPH 1.5 H.M.C - RX Out Of Egypt (page 3 pattern), G3 only ---
    v_rx = _mk_variant(db, sv, 1.50, design_variant="RX-SPH150")
    p_rx = _mk_pricing(db, v_rx, cat, availability=models.PricingAvailability.RX, price=3400,
                       coating=hmc, market_scope="Out Of Egypt",
                       power_scope_bounds=(None, None, None, None, None, None, -12.0, 8.0, 4.0))
    _mk_range(db, sv, v_rx, p_rx, -12.0, 12.0, -4.0, 0.0, total_power_min=-12.0,
             total_power_max=8.0, max_cyl_abs=4.0)

    # --- Maxxee Basic 1.5 H.M.C - Progressive RX (pages 5-8 pattern), G3 + ADD ---
    v_basic = _mk_variant(db, prog, 1.50, design_variant="Basic")
    p_basic = _mk_pricing(db, v_basic, cat, availability=models.PricingAvailability.RX, price=6100,
                          coating=hmc, market_scope=None,
                          power_scope_bounds=(None, None, None, None, 0.75, 3.50, -8.0, 6.0, 4.0))
    _mk_range(db, prog, v_basic, p_basic, -8.0, 10.0, -4.0, 0.0, add_min=0.75, add_max=3.50,
             total_power_min=-8.0, total_power_max=6.0, max_cyl_abs=4.0)

    return {"company": co, "sv": sv, "prog": prog,
            "v_hmc": v_hmc, "pA": pA, "pB": pB, "pC": pC, "pD": pD,
            "v_asph": v_asph, "pE": pE, "pF": pF,
            "v_rx": v_rx, "p_rx": p_rx, "v_basic": v_basic, "p_basic": p_basic}


# A/E. Maxxee SPH 1.5 H.M.C: same product, same index, same coating, two
# printed price BANDS -> two different prices depending on which band the
# prescription's power falls into, never collapsed to one price.
def test_A_1_5_hmc_price_band_A(db, maxxee_setup):
    sv = maxxee_setup["sv"]
    presc = _mk_presc(db, -3.5, -1.0, name="a-band-a-only")  # sph past band B's -3 limit
    resp = _targeted(db, presc, lens_model_id=sv.id, index_value=1.5, coating="H.M.C")
    assert resp.best_match.pair_fulfillment.status == "stock_egypt"
    assert resp.best_match.pair_fulfillment.price_pair == Decimal("700.00")


def test_A2_1_5_hmc_price_band_B(db, maxxee_setup):
    sv = maxxee_setup["sv"]
    presc = _mk_presc(db, -2.0, -3.0, name="a-band-b-only")  # cyl past band A's -2 limit
    resp = _targeted(db, presc, lens_model_id=sv.id, index_value=1.5, coating="H.M.C")
    assert resp.best_match.pair_fulfillment.status == "stock_egypt"
    assert resp.best_match.pair_fulfillment.price_pair == Decimal("800.00")


# B. Same pattern for Blue U.V.
def test_B_blue_uv_price_bands(db, maxxee_setup):
    sv = maxxee_setup["sv"]
    presc_b = _mk_presc(db, -2.0, -3.5, name="b-band-b")   # cyl past band C's -2 limit, within D's -4
    resp_b = _targeted(db, presc_b, lens_model_id=sv.id, index_value=1.5, coating="Blue U.V")
    assert resp_b.best_match.pair_fulfillment.price_pair == Decimal("1350.00")
    presc_a2 = _mk_presc(db, -2.8, -1.5, name="b-band-a-only")  # sph past D's -2 limit, within C's -3
    resp_a = _targeted(db, presc_a2, lens_model_id=sv.id, index_value=1.5, coating="Blue U.V")
    assert resp_a.best_match.pair_fulfillment.price_pair == Decimal("1250.00")


# C/D. Maxxee ASPH 1.6(+) H.M.C+: plain-box band vs G3 total-power band.
def test_C_asph_1_6_plus_plain_box_band(db, maxxee_setup):
    sv = maxxee_setup["sv"]
    presc = _mk_presc(db, 5.5, -0.4, name="c-total-only")  # sph past plain box's +4, within G3 total<=6
    resp = _targeted(db, presc, lens_model_id=sv.id, index_value=1.6,
                     design_type=models.DesignType.ASPHERICAL, coating="H.M.C+")
    assert resp.best_match.pair_fulfillment.price_pair == Decimal("2550.00")


def test_D_asph_1_6_plus_total_power_band(db, maxxee_setup):
    sv = maxxee_setup["sv"]
    presc = _mk_presc(db, 7.0, 0.0, name="d-outside-both")  # past both bands entirely
    resp = _targeted(db, presc, lens_model_id=sv.id, index_value=1.6,
                     design_type=models.DesignType.ASPHERICAL, coating="H.M.C+")
    assert resp.best_match.pair_fulfillment.status != "stock_egypt"


# E. Prescription exactly on a boundary -> correct price (boundary inclusive).
def test_E_boundary_exact_inclusive(db, maxxee_setup):
    sv = maxxee_setup["sv"]
    presc = _mk_presc(db, -4.0, -2.0, name="e-exact-corner")  # exact corner of band A's box
    resp = _targeted(db, presc, lens_model_id=sv.id, index_value=1.5, coating="H.M.C")
    assert resp.best_match.pair_fulfillment.price_pair == Decimal("700.00")


# F. Just outside every printed band -> not quoted as STOCK at all (falls to
# whatever the generic fallback is - never silently reusing a band's price).
def test_F_outside_every_band_not_quoted(db, maxxee_setup):
    sv = maxxee_setup["sv"]
    presc = _mk_presc(db, -30.0, 0.0, name="f-impossible")
    resp = _targeted(db, presc, lens_model_id=sv.id, index_value=1.5, coating="H.M.C")
    assert resp.best_match.pair_fulfillment.status != "stock_egypt"


# G. Overlapping/adjacent bands must NEVER produce an arbitrary price choice -
# the cheapest proven band always wins, deterministically (this is the fix
# _pair_fulfillment needed: previously "whichever row came first" won).
def test_G_overlapping_bands_always_pick_cheapest(db, maxxee_setup):
    sv = maxxee_setup["sv"]
    # sph=-2, cyl=-1 is inside BOTH band A (sph 0..-4, cyl 0..-2) and band B
    # (sph 0..-3, cyl 0..-4) - genuine catalog overlap.
    presc = _mk_presc(db, -2.0, -1.0, name="g-overlap")
    resp = _targeted(db, presc, lens_model_id=sv.id, index_value=1.5, coating="H.M.C")
    assert resp.best_match.pair_fulfillment.price_pair == Decimal("700.00")
    assert resp.best_match.pair_fulfillment.source_pricing_ids == [maxxee_setup["pA"].id]
    # run it again the other way round (band B built AFTER band A in the
    # fixture, but the result must be identical regardless of row order)
    presc2 = _mk_presc(db, -2.5, -1.5, name="g-overlap-2")
    resp2 = _targeted(db, presc2, lens_model_id=sv.id, index_value=1.5, coating="H.M.C")
    assert resp2.best_match.pair_fulfillment.price_pair == Decimal("700.00")


# G2. The cheapest-wins tie-break must NEVER cross commercial identities - it
# may only pick among price bands of the SAME variant + SAME coating + SAME
# route. A different, much cheaper, unrelated STOCK row (different variant
# entirely) that is ALSO eligible for the same prescription must never steal
# the SPH 1.5 H.M.C group's own result out from under it, and the H.M.C
# group's own price bands (700/800) must never leak into the cheap variant's
# result either.
def test_G2_cheapest_wins_never_crosses_identity(db, maxxee_setup):
    sv = maxxee_setup["sv"]
    cat = db.query(models.Catalog).filter_by(company_id=maxxee_setup["company"].id).first()
    coat_cheap = _mk_coating(db, "CheapLine")
    v_cheap = _mk_variant(db, sv, 1.50, design_variant="CheapLine")
    p_cheap = _mk_pricing(db, v_cheap, cat, availability=models.PricingAvailability.STOCK,
                          price=100, coating=coat_cheap, market_scope="Egypt",
                          power_scope_bounds=(-4.0, 0.0, -2.0, 0.0, None, None, None, None, None))
    _mk_range(db, sv, v_cheap, p_cheap, -4.0, 0.0, -2.0, 0.0)

    # same prescription that overlaps SPH 1.5 H.M.C's own bands AND matches
    # the unrelated 100 EGP CheapLine row.
    presc = _mk_presc(db, -2.0, -1.0, name="g2-cross-identity")
    f = schemas.LensFilters(company_id=maxxee_setup["company"].id, lens_model_id=sv.id, index_value=1.5)
    req = schemas.ProductSearchRequest(mode="targeted", filters=f, include_alternatives=False)
    resp = product_search.search(db, presc, req)

    seen_prices = set()
    for grp in resp.groups:
        for r in grp.results:
            seen_prices.add(r.pair_fulfillment.price_pair)
            # coating_code alone is not identity here - this fixture also has an
            # unrelated RX row that happens to share coating "H.M.C" (proving
            # coating_code is NOT what scopes the tie-break; variant identity is).
            if r.coating_code == "H.M.C" and r.pair_fulfillment.status == "stock_egypt":
                assert r.pair_fulfillment.price_pair == Decimal("700.00"), (
                    "H.M.C's own cheapest STOCK band (700) must win within its "
                    "own identity, never overridden by an unrelated variant's price")
            elif r.coating_code == "CheapLine":
                assert r.pair_fulfillment.price_pair == Decimal("100.00"), (
                    "the unrelated cheap variant must keep its own proven price, "
                    "never inherit H.M.C's price bands either")
    assert Decimal("700.00") in seen_prices and Decimal("100.00") in seen_prices, (
        "both distinct commercial identities must surface with their OWN price - "
        "neither may collapse into the other via the cheapest-wins tie-break")


# H. Total Sph+Cyl + Max Cyl (G3) RX logic: proven inside, proven outside.
def test_H_g3_total_power_rx(db, maxxee_setup):
    sv = maxxee_setup["sv"]
    presc_in = _mk_presc(db, -6.0, -2.0, name="h-inside")   # low meridian -8, high -6: within [-12,8]
    resp_in = _targeted(db, presc_in, lens_model_id=sv.id, index_value=1.5, design_variant="RX-SPH150")
    assert resp_in.best_match.pair_fulfillment.status == "rx"
    assert resp_in.best_match.pair_fulfillment.price_pair == Decimal("3400.00")
    presc_out = _mk_presc(db, -6.0, -5.0, name="h-outside")  # cyl magnitude 5 > max_cyl_abs 4
    resp_out = _targeted(db, presc_out, lens_model_id=sv.id, index_value=1.5, design_variant="RX-SPH150")
    assert resp_out.best_match.pair_fulfillment.status != "rx"


# I. Progressive ADD: +0.75 accepted, +3.50 accepted, outside printed ADD
# range rejected/not proven (existing 0.25D tolerance applies, same as every
# other manufacturer's ADD/CYL/SPH checks in this matcher).
def test_I_progressive_add_boundaries(db, maxxee_setup):
    prog = maxxee_setup["prog"]
    for add, expect_ok in [(0.75, True), (3.50, True), (4.25, False), (0.25, False)]:
        presc = _mk_presc(db, -2.0, -1.0, add=add, name=f"i-add-{add}")
        resp = _targeted(db, presc, lens_model_id=prog.id, index_value=1.5, design_variant="Basic")
        ok = resp.best_match.pair_fulfillment.status == "rx"
        assert ok == expect_ok, (add, resp.best_match.pair_fulfillment.status)


# J. Company isolation: Maxxee results never contaminate HOYA Main (and vice
# versa) - a company-scoped search never returns a different company's row.
def test_J_company_isolation(db, maxxee_setup):
    sv = maxxee_setup["sv"]
    hoya = _mk_company(db, "HOYA")
    hoya_cat = _mk_catalog(db, hoya)
    hoya_model = _mk_model(db, hoya, "HOYA", models.LensCategory.SINGLE_VISION)
    v_hoya = _mk_variant(db, hoya_model, 1.50)
    p_hoya = _mk_pricing(db, v_hoya, hoya_cat, availability=models.PricingAvailability.STOCK,
                         price=500, market_scope="Egypt",
                         power_scope_bounds=(-4.0, 0.0, -2.0, 0.0, None, None, None, None, None))
    _mk_range(db, hoya_model, v_hoya, p_hoya, -4.0, 0.0, -2.0, 0.0)

    presc = _mk_presc(db, -2.0, -1.0, name="j-isolation")
    f = schemas.LensFilters(company_id=maxxee_setup["company"].id, index_value=1.5)
    req = schemas.ProductSearchRequest(mode="targeted", filters=f, include_alternatives=True)
    resp = product_search.search(db, presc, req)
    for grp in resp.groups:
        for r in grp.results:
            assert r.company_id == maxxee_setup["company"].id


# K. Category is a hard boundary: Maxxee single_vision search never returns a
# Maxxee progressive row (Basic/Plus/Premium/Individual Premium) as an
# alternative, and vice versa.
def test_K_category_hard_boundary(db, maxxee_setup):
    co = maxxee_setup["company"]
    presc = _mk_presc(db, -30.0, 0.0, name="k-impossible")
    f = schemas.LensFilters(company_id=co.id, category=models.LensCategory.SINGLE_VISION)
    req = schemas.ProductSearchRequest(mode="targeted", filters=f, include_alternatives=True)
    resp = product_search.search(db, presc, req)
    for alt in (resp.alternatives or []):
        assert alt.result.lens_model.category == models.LensCategory.SINGLE_VISION
