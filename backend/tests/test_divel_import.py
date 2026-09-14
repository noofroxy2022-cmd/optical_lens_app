"""Permanent regression coverage for the DIVEL ITALIA canonical import.

Deliberately synthetic, mirroring the corrected shape directly via the ORM
(no PDF parsing, no dependency on the live optical_lens.db), matching the
same pattern as test_maxxee_import.py / test_bbgr_import.py.

This is a pure STOCK catalog (Stock in Egypt / Finished Single Vision) - the
first import in this project where EVERY row is STOCK with a REAL printed
Stock PowerRange (27 of 33 rows). The remaining 6 rows (1.50 Sun/Mirror/
Polar) print no PowerRange at all - proven commercially (price/product/
Egypt-stock), but prescription-level stock compatibility is never claimed
(the existing, unchanged STOCK-without-range rule). "70%" printed there is
tint/color density, never diameter and never a PowerRange - recorded via
the already-existing generic `Coating.description` field, no schema change.
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


def _mk_coating(db, code, description=None):
    c = models.Coating(code=code, name=code, description=description)
    db.add(c); db.commit(); db.refresh(c)
    return c


def _mk_variant(db, model, index_value, design_type=models.DesignType.SPHERICAL,
                is_aspherical=False, design_variant=None, color_variant=None):
    v = models.LensVariant(
        lens_model_id=model.id, material=models.MaterialType.CR39, index_value=index_value,
        design_type=design_type, is_aspherical=is_aspherical,
        design_variant=design_variant, color_variant=color_variant, price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    return v


def _mk_pricing(db, variant, catalog, coating, *, price, power_scope_bounds=None):
    power_scope = crud.build_power_scope(*power_scope_bounds) if power_scope_bounds else None
    vp = models.VariantPricing(
        variant_id=variant.id, coating_id=(coating.id if coating else None),
        availability=models.PricingAvailability.STOCK, price_pair=Decimal(str(price)),
        currency="EGP", source_catalog_id=catalog.id, market_scope="Egypt",
        power_scope=power_scope)
    db.add(vp); db.commit(); db.refresh(vp)
    return vp


def _mk_range(db, model, variant, pricing, sph_min, sph_max, cyl_min, cyl_max, notes=None):
    pr = models.PowerRange(lens_model_id=model.id, variant_id=variant.id, pricing_id=pricing.id,
                           sph_min=sph_min, sph_max=sph_max, cyl_min=cyl_min, cyl_max=cyl_max,
                           notes=notes)
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
def divel_setup(db):
    co = _mk_company(db, "DIVEL ITALIA")
    cat = _mk_catalog(db, co)
    sv = _mk_model(db, co, "DIVEL ITALIA", models.LensCategory.SINGLE_VISION)
    performance = _mk_coating(db, "Performance")
    blue_natural_156 = _mk_coating(db, "Blue Natural")
    silken = _mk_coating(db, "Silken")
    sun_lenses = _mk_coating(db, "Sun Lenses", description="Tint density: 70%")

    # --- 1.56 Performance: representative overlapping bands, diameters as
    # printed (Ø65 / Ø70 / Ø55) - Band A (950/Ø65) and Band B (1000/Ø55)
    # reproduce the real catalog's diameter-ambiguous overlap exactly. ---
    v_156 = _mk_variant(db, sv, 1.56)
    p_mixed = _mk_pricing(db, v_156, cat, performance, price=850,
                          power_scope_bounds=(-4.0, 4.0, -2.0, 2.0, None, None, None, None, None))
    _mk_range(db, sv, v_156, p_mixed, -4.0, 4.0, -2.0, 2.0, notes="Ø65")
    p_minus = _mk_pricing(db, v_156, cat, performance, price=850,
                         power_scope_bounds=(-4.0, 0.0, -2.0, 0.0, None, None, None, None, None))
    _mk_range(db, sv, v_156, p_minus, -4.0, 0.0, -2.0, 0.0, notes="Ø70")
    p_wide_cyl = _mk_pricing(db, v_156, cat, performance, price=950,
                            power_scope_bounds=(-4.0, 4.0, -4.0, 4.0, None, None, None, None, None))
    _mk_range(db, sv, v_156, p_wide_cyl, -4.0, 4.0, -4.0, 4.0, notes="Ø65")   # Band A
    p_high_cyl_plus = _mk_pricing(db, v_156, cat, performance, price=1000,
                                  power_scope_bounds=(0.0, 4.0, 2.25, 4.0, None, None, None, None, None))
    _mk_range(db, sv, v_156, p_high_cyl_plus, 0.0, 4.0, 2.25, 4.0, notes="Ø55")   # Band B

    # --- 1.60 non-AS vs 1.60 AS - same coating name, must stay distinct ---
    v_160 = _mk_variant(db, sv, 1.60, design_type=models.DesignType.SPHERICAL, is_aspherical=False)
    p_160 = _mk_pricing(db, v_160, cat, blue_natural_156, price=1400,
                        power_scope_bounds=(-8.0, 0.0, -2.0, 0.0, None, None, None, None, None))
    _mk_range(db, sv, v_160, p_160, -8.0, 0.0, -2.0, 0.0)
    v_160_as = _mk_variant(db, sv, 1.60, design_type=models.DesignType.ASPHERICAL, is_aspherical=True)
    p_160_as = _mk_pricing(db, v_160_as, cat, blue_natural_156, price=1850,
                          power_scope_bounds=(-8.0, 0.0, -2.0, 0.0, None, None, None, None, None))
    _mk_range(db, sv, v_160_as, p_160_as, -8.0, 0.0, -2.0, 0.0)

    # --- 1.67 AS Silken: 2 bands ---
    v_167 = _mk_variant(db, sv, 1.67, design_type=models.DesignType.ASPHERICAL, is_aspherical=True)
    p_silken_1 = _mk_pricing(db, v_167, cat, silken, price=2150,
                            power_scope_bounds=(-12.0, -5.0, -2.0, 0.0, None, None, None, None, None))
    _mk_range(db, sv, v_167, p_silken_1, -12.0, -5.0, -2.0, 0.0)
    p_silken_2 = _mk_pricing(db, v_167, cat, silken, price=2300,
                            power_scope_bounds=(-8.0, -5.0, -4.0, 0.0, None, None, None, None, None))
    _mk_range(db, sv, v_167, p_silken_2, -8.0, -5.0, -4.0, 0.0)

    # --- 1.50 Sun Lenses: no PowerRange, colors preserved, tint density on Coating ---
    v_cr_solid = _mk_variant(db, sv, 1.50, design_variant="CR Solid", color_variant="Gray/Brown/G15/Blue")
    p_cr_solid = _mk_pricing(db, v_cr_solid, cat, sun_lenses, price=900)
    v_cr_gradient = _mk_variant(db, sv, 1.50, design_variant="CR Gradient", color_variant="Gray/Brown/G15")
    p_cr_gradient = _mk_pricing(db, v_cr_gradient, cat, sun_lenses, price=1100)

    return {"company": co, "sv": sv, "performance": performance, "silken": silken,
            "sun_lenses": sun_lenses, "v_156": v_156, "p_mixed": p_mixed, "p_minus": p_minus,
            "p_wide_cyl": p_wide_cyl, "p_high_cyl_plus": p_high_cyl_plus,
            "v_160": v_160, "v_160_as": v_160_as,
            "v_167": v_167, "p_silken_1": p_silken_1, "p_silken_2": p_silken_2,
            "v_cr_solid": v_cr_solid, "p_cr_solid": p_cr_solid,
            "v_cr_gradient": v_cr_gradient, "p_cr_gradient": p_cr_gradient}


# 1. Company independent.
def test_1_company_independent(db, divel_setup):
    co = divel_setup["company"]
    assert co.name == "DIVEL ITALIA"
    assert not hasattr(models.Company, "parent_company_id")


# 4/5/6. Stock Egypt single_vision, RX=0 (checked on the fixture's own rows).
def test_456_stock_egypt_single_vision_no_rx(db, divel_setup):
    sv = divel_setup["sv"]
    rows = db.query(models.VariantPricing).join(models.LensVariant).filter(
        models.LensVariant.lens_model_id == sv.id).all()
    assert len(rows) > 0
    for p in rows:
        assert p.availability == models.PricingAvailability.STOCK
        assert p.market_scope == "Egypt"
        assert p.variant.lens_model.category == models.LensCategory.SINGLE_VISION


# 7/8. Printed PowerRanges attach correctly; different power-band prices stay distinct.
def test_78_power_bands_attached_and_distinct(db, divel_setup):
    v = divel_setup["v_156"]
    presc_overlap = _mk_presc(db, -2.0, -1.0, name="overlap")
    st_mixed = product_search._row_eye_status(divel_setup["p_mixed"], presc_overlap, "od")
    st_minus = product_search._row_eye_status(divel_setup["p_minus"], presc_overlap, "od")
    assert st_mixed == "eligible" and st_minus == "eligible"   # genuine overlap
    resp = _targeted(db, presc_overlap, lens_model_id=v.lens_model_id, index_value=1.56, coating="Performance")
    assert resp.best_match.pair_fulfillment.price_pair == Decimal("850.00")   # cheapest of the two

    presc_wide_only = _mk_presc(db, -2.0, -3.0, name="wide-cyl-only")
    resp2 = _targeted(db, presc_wide_only, lens_model_id=v.lens_model_id, index_value=1.56, coating="Performance")
    assert resp2.best_match.pair_fulfillment.price_pair == Decimal("950.00")   # only the wider-cyl band covers this


# 9. 1.60 AS remains distinct from 1.60 non-AS (same coating name, different price).
def test_9_1_60_as_distinct_from_non_as(db, divel_setup):
    v, v_as = divel_setup["v_160"], divel_setup["v_160_as"]
    assert v.id != v_as.id
    p = db.query(models.VariantPricing).filter(models.VariantPricing.variant_id == v.id).first()
    p_as = db.query(models.VariantPricing).filter(models.VariantPricing.variant_id == v_as.id).first()
    assert p.price_pair == Decimal("1400.00")
    assert p_as.price_pair == Decimal("1850.00")
    assert v.is_aspherical is False and v_as.is_aspherical is True


# 10. 1.67 AS Silken ranges correct (inside proven, outside rejected, per band).
def test_10_1_67_silken_ranges(db, divel_setup):
    p1, p2 = divel_setup["p_silken_1"], divel_setup["p_silken_2"]
    presc_band1 = _mk_presc(db, -9.0, -1.0, name="band1")   # within (-12,-5) cyl(-2,0)
    presc_band2 = _mk_presc(db, -7.0, -3.0, name="band2")   # within (-8,-5) cyl(-4,0), outside band1's cyl
    presc_outside = _mk_presc(db, -3.0, -1.0, name="outside")   # sph outside both (-12,-5)/(-8,-5)
    assert product_search._row_eye_status(p1, presc_band1, "od") == "eligible"
    assert product_search._row_eye_status(p2, presc_band1, "od") == "ineligible"
    assert product_search._row_eye_status(p2, presc_band2, "od") == "eligible"
    assert product_search._row_eye_status(p1, presc_outside, "od") == "ineligible"
    assert product_search._row_eye_status(p2, presc_outside, "od") == "ineligible"


# 11. Sun/Mirror/Polar: tint density = 70% as catalog evidence (Coating.description),
# never diameter = 70. `LensVariant.diameter` is a real but DORMANT column
# reserved for the separately-deferred D1 scalar-diameter work (D1 stash) -
# this import must never populate it (that would reopen D1's own job outside
# its dedicated phase); optical diameters (65/70/55mm) are recorded the same
# way ZEISS's own multi-diameter evidence already does, in PowerRange.notes.
def test_11_tint_density_never_diameter(db, divel_setup):
    c = divel_setup["sun_lenses"]
    assert c.description == "Tint density: 70%"
    for v in (divel_setup["v_156"], divel_setup["v_160"], divel_setup["v_167"]):
        assert v.diameter is None   # D1's column, never touched by this import
    for p in (divel_setup["p_mixed"], divel_setup["p_minus"], divel_setup["p_wide_cyl"]):
        assert p.price_pair != 70   # sanity: tint % never mistaken for a numeric column value


# 12. Sun/Mirror/Polar rows have no fabricated PowerRange.
def test_12_no_fabricated_powerrange_for_sun_rows(db, divel_setup):
    for key in ("p_cr_solid", "p_cr_gradient"):
        p = divel_setup[key]
        assert list(p.power_ranges) == []
        presc = _mk_presc(db, -2.0, -1.0, name=f"t12-{key}")
        assert product_search._row_eye_status(p, presc, "od") == "ineligible"


# 13. Color lists do not multiply pricing-row count (one price per design_variant,
# regardless of how many colors are listed).
def test_13_colors_do_not_multiply_pricing(db, divel_setup):
    v = divel_setup["v_cr_solid"]
    assert v.color_variant == "Gray/Brown/G15/Blue"   # 4 colors, ONE variant
    rows = db.query(models.VariantPricing).filter(models.VariantPricing.variant_id == v.id).all()
    assert len(rows) == 1


# 14. Solid/Gradient identities remain distinct (different design_variant, different price).
def test_14_solid_gradient_distinct(db, divel_setup):
    v_solid, v_gradient = divel_setup["v_cr_solid"], divel_setup["v_cr_gradient"]
    assert v_solid.id != v_gradient.id
    p_solid = db.query(models.VariantPricing).filter(models.VariantPricing.variant_id == v_solid.id).first()
    p_gradient = db.query(models.VariantPricing).filter(models.VariantPricing.variant_id == v_gradient.id).first()
    assert p_solid.price_pair == Decimal("900.00")
    assert p_gradient.price_pair == Decimal("1100.00")


# 15. No other manufacturer count changes (company isolation).
def test_15_company_isolation(db, divel_setup):
    sv = divel_setup["sv"]
    hoya = _mk_company(db, "HOYA")
    hoya_cat = _mk_catalog(db, hoya)
    hoya_model = _mk_model(db, hoya, "HOYA", models.LensCategory.SINGLE_VISION)
    v_hoya = _mk_variant(db, hoya_model, 1.50)
    _mk_pricing(db, v_hoya, hoya_cat, None, price=500)

    presc = _mk_presc(db, -2.0, name="isolation")
    f = schemas.LensFilters(company_id=divel_setup["company"].id, index_value=1.56)
    req = schemas.ProductSearchRequest(mode="targeted", filters=f, include_alternatives=True)
    resp = product_search.search(db, presc, req)
    for grp in resp.groups:
        for r in grp.results:
            assert r.company_id == divel_setup["company"].id


# 16/17. Global RX rule unchanged; STOCK + no PowerRange remains not prescription-proven.
def test_1617_global_rx_rule_and_stock_safety_unchanged(db, divel_setup):
    # STOCK + no range (DIVEL's own Sun row) -> ineligible, matches the
    # permanent STOCK rule exactly as it already was before this import.
    p_stock_no_range = divel_setup["p_cr_solid"]
    presc = _mk_presc(db, -2.0, -1.0, name="stock-check")
    assert product_search._row_eye_status(p_stock_no_range, presc, "od") == "ineligible"

    # RX + no range (unaffected by this import) -> still eligible, per the
    # permanent domain rule established in the BBGR/global-RX-rule phase.
    co2 = _mk_company(db, "GenericRxCo")
    cat2 = _mk_catalog(db, co2)
    model2 = _mk_model(db, co2, "GenericRxCo", models.LensCategory.SINGLE_VISION)
    v2 = _mk_variant(db, model2, 1.50)
    vp2 = models.VariantPricing(variant_id=v2.id, availability=models.PricingAvailability.RX,
                                price_pair=Decimal("3000.00"), currency="EGP", source_catalog_id=cat2.id)
    db.add(vp2); db.commit(); db.refresh(vp2)
    assert product_search._row_eye_status(vp2, presc, "od") == "eligible"


# ===========================================================================
# Overlapping Stock band safety (diameter-ambiguous overlap correction).
#
# 1.56 Performance's Band A (950 EGP, printed diameter 65mm, mixed box
# sph[-4,4]/cyl[-4,4]) and Band B (1000 EGP, printed diameter 55mm, box
# sph[0,4]/cyl[2.25,4] - a subset of Band A's box) are both genuine printed
# catalog rows. For a prescription inside Band B's box (therefore also
# inside Band A's, since B subset A), the existing generic cheapest-wins
# tie-break would silently return 950 - but the REAL final price depends on
# which diameter (55mm or 65mm) the order actually needs, a fact this
# matcher cannot evaluate. The fix: `_pair_fulfillment` now detects this
# specific shape (2+ same-identity/same-tier candidates, different prices,
# different catalog-proven diameters) and attaches a
# `price_confirmation_note` caveat - never changes the shown price, status,
# or availability.
# ===========================================================================
def _presc_in_band_b(db, name="band-b"):
    # plus-form (sph=+2.0, cyl=+3.0) -> minus-form storage (sph=5.0, cyl=-3.0);
    # inside Band B's box (sph[0,4]/cyl[2.25,4]) AND Band A's (sph[-4,4]/cyl[-4,4]).
    return _mk_presc(db, 5.0, -3.0, name=name)


# A. A DIVEL Rx covered by both the 950 and 1000 bands does NOT silently
# return 950 as an unquestionably final price - a confirmation caveat rides
# along with it.
def test_A_ambiguous_overlap_not_silently_final(db, divel_setup):
    sv = divel_setup["sv"]
    presc = _presc_in_band_b(db)
    resp = _targeted(db, presc, lens_model_id=sv.id, index_value=1.56, coating="Performance")
    pf = resp.best_match.pair_fulfillment
    assert pf.price_confirmation_note is not None
    assert "قطر" in pf.price_confirmation_note


# B. The result remains Stock-compatible where the printed PowerRange supports it.
def test_B_result_remains_stock_compatible(db, divel_setup):
    sv = divel_setup["sv"]
    presc = _presc_in_band_b(db)
    resp = _targeted(db, presc, lens_model_id=sv.id, index_value=1.56, coating="Performance")
    pf = resp.best_match.pair_fulfillment
    assert pf.status == "stock_egypt"


# C. A diameter/price confirmation caveat is surfaced, naming both printed
# diameters (55 and 65).
def test_C_diameter_caveat_names_both_diameters(db, divel_setup):
    sv = divel_setup["sv"]
    presc = _presc_in_band_b(db)
    resp = _targeted(db, presc, lens_model_id=sv.id, index_value=1.56, coating="Performance")
    note = resp.best_match.pair_fulfillment.price_confirmation_note
    assert "55" in note and "65" in note


# D. Both printed prices (950 and 1000) remain preserved in the catalog -
# neither was merged, deleted, or altered by this safety fix.
def test_D_both_prices_preserved_in_catalog(db, divel_setup):
    assert divel_setup["p_wide_cyl"].price_pair == Decimal("950.00")
    assert divel_setup["p_high_cyl_plus"].price_pair == Decimal("1000.00")


# E. No diameter is fabricated - the caveat is built only from printed
# PowerRange.notes evidence, and the row-level data is untouched.
def test_E_no_diameter_fabricated(db, divel_setup):
    for v in (divel_setup["v_156"],):
        assert v.diameter is None   # D1's dormant column, never populated
    for p in (divel_setup["p_wide_cyl"], divel_setup["p_high_cyl_plus"]):
        for pr in p.power_ranges:
            assert pr.notes in ("Ø65", "Ø55")   # exactly what was printed, nothing invented


# F. Non-overlapping DIVEL bands still resolve normally, with no caveat.
def test_F_non_overlapping_bands_resolve_normally(db, divel_setup):
    sv = divel_setup["sv"]
    presc = _mk_presc(db, -2.0, -3.0, name="wide-cyl-minus-only")
    resp = _targeted(db, presc, lens_model_id=sv.id, index_value=1.56, coating="Performance")
    pf = resp.best_match.pair_fulfillment
    assert pf.price_pair == Decimal("950.00")
    assert pf.price_confirmation_note is None


# G. Maxxee's legitimate overlapping price-band shape remains unchanged -
# when the competing bands share the SAME printed diameter (Maxxee's real
# catalog data, reproduced synthetically here), the cheapest price wins with
# NO caveat, exactly as test_maxxee_import.py's own dedicated overlap test
# already proves end to end (re-verified together with this file in the
# same targeted run - see the acceptance report).
def test_G_same_diameter_overlap_no_caveat(db):
    co = _mk_company(db, "MaxxeeLike")
    cat = _mk_catalog(db, co)
    model = _mk_model(db, co, "MaxxeeLike", models.LensCategory.SINGLE_VISION)
    v = _mk_variant(db, model, 1.50)
    p_a = _mk_pricing(db, v, cat, None, price=700,
                      power_scope_bounds=(-4.0, 0.0, -2.0, 0.0, None, None, None, None, None))
    _mk_range(db, model, v, p_a, -4.0, 0.0, -2.0, 0.0, notes="Ø70")
    p_b = _mk_pricing(db, v, cat, None, price=800,
                      power_scope_bounds=(-3.0, 0.0, -4.0, 0.0, None, None, None, None, None))
    _mk_range(db, model, v, p_b, -3.0, 0.0, -4.0, 0.0, notes="Ø70")   # SAME diameter as p_a

    presc = _mk_presc(db, -2.0, -1.0, name="maxxee-like-overlap")   # inside BOTH boxes
    f = schemas.LensFilters(lens_model_id=model.id, index_value=1.50)
    req = schemas.ProductSearchRequest(mode="targeted", filters=f)
    resp = product_search.search(db, presc, req)
    pf = resp.best_match.pair_fulfillment
    assert pf.price_pair == Decimal("700.00")   # cheapest still wins
    assert pf.price_confirmation_note is None   # no ambiguity - same diameter throughout


# H. HOYA/ZEISS/PIXEL/Synchrony/SEIKO/BBGR unchanged - none of their
# overlapping/eligible rows carry differing diameter evidence, so none of
# them can trigger this new caveat.
def test_H_other_manufacturers_unaffected(db):
    co = _mk_company(db, "HOYA")
    cat = _mk_catalog(db, co)
    model = _mk_model(db, co, "HOYA", models.LensCategory.SINGLE_VISION)
    v = _mk_variant(db, model, 1.50)
    p = _mk_pricing(db, v, cat, None, price=3000)
    _mk_range(db, model, v, p, -4.0, 0.0, -2.0, 0.0)   # no diameter note at all
    presc = _mk_presc(db, -2.0, -1.0, name="hoya-check")
    f = schemas.LensFilters(lens_model_id=model.id, index_value=1.50)
    req = schemas.ProductSearchRequest(mode="targeted", filters=f)
    resp = product_search.search(db, presc, req)
    assert resp.best_match.pair_fulfillment.price_confirmation_note is None


# I. D1 stash untouched - the dormant scalar diameter column stays NULL and
# this fix never reads or writes it.
def test_I_d1_stash_untouched(db, divel_setup):
    for v in (divel_setup["v_156"], divel_setup["v_160"], divel_setup["v_160_as"], divel_setup["v_167"]):
        assert v.diameter is None
