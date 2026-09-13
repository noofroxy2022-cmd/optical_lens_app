"""Permanent regression coverage for the Seiko 2025 Retail Pricelist import.

Deliberately synthetic, mirroring the corrected shape directly via the ORM
(no PDF parsing, no dependency on the live optical_lens.db), matching the
same pattern as test_maxxee_import.py / test_synchrony_import.py.

Seiko's pricelist prints NO PowerRange/SPH/CYL/ADD data anywhere for any
lens (it is a pure price list) - every row in this catalog is priced but
optically unresolved: STOCK rows have zero PowerRange (the existing
matcher already reports "ineligible" for a STOCK row with no range - never
fabricated as prescription-proven), and every RX row is explicitly written
with power_eligibility=UNRESOLVED (never left at the UNRESTRICTED default,
which would have silently made it "eligible" via the RX made-to-order
fallback).

Page 2's "STOCK OUT OF EGYPT" table prints several coatings and several
prices in ONE row, mapped POSITIONALLY (Nth coating -> Nth price) - these
are coating-specific commercial identities, never PowerRange price bands
(that shape belongs to Maxxee's page 2, a different catalog with a
genuinely different printed structure - conflating the two would be a
real modeling error).

A "TRIBRID SCC" row is repeated in all three Freeform matrices (pages 2,
3, 4) with no printed index value anywhere on any page - initially excluded
from the import entirely rather than guessing a number, per this project's
standing never-fabricate rule. The user/domain expert subsequently
confirmed Seiko Tribrid's index is 1.60 (a fact the pricelist itself never
states), so all 10 TRIBRID SCC cells (2 Freeform SV + 4 Progressive + 4
Lifestyle) were added in a follow-up correction using that confirmed
index - the full live import now totals the catalog's raw printed cell
count exactly: page 2 = 79, page 3 = 81, page 4 = 47, total = 207. This
synthetic fixture predates that correction and does not model TRIBRID at
all; its own fixed 14-row subset (see test_L) is unaffected either way.
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
                design_type=models.DesignType.SPHERICAL, is_aspherical=False,
                material=models.MaterialType.CR39):
    v = models.LensVariant(
        lens_model_id=model.id, material=material, index_value=index_value,
        design_type=design_type, is_aspherical=is_aspherical,
        design_variant=design_variant, treatment_band=treatment_band, price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    return v


def _mk_pricing(db, variant, catalog, *, availability, price, coating=None, market_scope=None,
                power_eligibility=models.PowerEligibilityStatus.UNRESTRICTED):
    vp = models.VariantPricing(
        variant_id=variant.id, coating_id=(coating.id if coating else None),
        availability=availability, power_eligibility=power_eligibility,
        price_pair=Decimal(str(price)), currency="EGP", source_catalog_id=catalog.id,
        market_scope=market_scope)
    db.add(vp); db.commit(); db.refresh(vp)
    return vp


def _mk_presc(db, sph=0.0, cyl=0.0, name="p"):
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
def seiko_setup(db):
    co = _mk_company(db, "SEIKO")
    cat = _mk_catalog(db, co)
    sv = _mk_model(db, co, "SEIKO", models.LensCategory.SINGLE_VISION)
    prog = _mk_model(db, co, "SEIKO", models.LensCategory.PROGRESSIVE)
    src_one = _mk_coating(db, "SRC - ONE")
    src_screen = _mk_coating(db, "SRC - SCREEN")
    scc = _mk_coating(db, "SCC")
    src_ultra = _mk_coating(db, "SRC ULTRA")

    # --- Page 2A: STOCK IN EGYPT ---
    v_150_sph = _mk_variant(db, sv, 1.50)
    p_egypt_one = _mk_pricing(db, v_150_sph, cat, availability=models.PricingAvailability.STOCK,
                              price=2025, coating=src_one, market_scope="Egypt")
    p_egypt_screen = _mk_pricing(db, v_150_sph, cat, availability=models.PricingAvailability.STOCK,
                                 price=3037, coating=src_screen, market_scope="Egypt")

    # --- Page 2B: STOCK OUT OF EGYPT - positional coating->price mapping ---
    p_ooe_scc = _mk_pricing(db, v_150_sph, cat, availability=models.PricingAvailability.STOCK,
                            price=2250, coating=scc, market_scope="Out Of Egypt")
    p_ooe_one = _mk_pricing(db, v_150_sph, cat, availability=models.PricingAvailability.STOCK,
                            price=2925, coating=src_one, market_scope="Out Of Egypt")
    p_ooe_screen = _mk_pricing(db, v_150_sph, cat, availability=models.PricingAvailability.STOCK,
                               price=3825, coating=src_screen, market_scope="Out Of Egypt")

    v_160_as = _mk_variant(db, sv, 1.60, design_type=models.DesignType.ASPHERICAL, is_aspherical=True)
    p_160_scc = _mk_pricing(db, v_160_as, cat, availability=models.PricingAvailability.STOCK,
                            price=4950, coating=scc, market_scope="Out Of Egypt")
    p_160_one = _mk_pricing(db, v_160_as, cat, availability=models.PricingAvailability.STOCK,
                            price=5400, coating=src_one, market_scope="Out Of Egypt")
    p_160_screen = _mk_pricing(db, v_160_as, cat, availability=models.PricingAvailability.STOCK,
                               price=6750, coating=src_screen, market_scope="Out Of Egypt")
    p_160_ultra = _mk_pricing(db, v_160_as, cat, availability=models.PricingAvailability.STOCK,
                              price=6750, coating=src_ultra, market_scope="Out Of Egypt")

    # --- Page 2C: FREEFORM SINGLE VISION (RX) - a few representative cells ---
    v_150_scc_sph = v_150_sph  # same identity as the stock 1.50 SPH row (shared on purpose)
    p_freeform_150_sph = _mk_pricing(db, v_150_scc_sph, cat, availability=models.PricingAvailability.RX,
                                     price=6480, coating=scc,
                                     power_eligibility=models.PowerEligibilityStatus.UNRESOLVED)
    v_160_scc_azone = _mk_variant(db, sv, 1.60, design_variant="A-Zone",
                                  design_type=models.DesignType.ASPHERICAL, is_aspherical=True)
    p_azone = _mk_pricing(db, v_160_scc_azone, cat, availability=models.PricingAvailability.RX,
                          price=15660, coating=scc,
                          power_eligibility=models.PowerEligibilityStatus.UNRESOLVED)
    # dash cell: 1.5 SCC has NO A-Zone price printed - no variant/pricing created for it.

    # --- Page 3: FREEFORM PROGRESSIVE (RX) - low/middle/high rows, several designs ---
    v_150_prog_visionx = _mk_variant(db, prog, 1.50, design_variant="Vision X")
    p_prog_low = _mk_pricing(db, v_150_prog_visionx, cat, availability=models.PricingAvailability.RX,
                             price=9000, coating=scc,
                             power_eligibility=models.PowerEligibilityStatus.UNRESOLVED)
    v_174_prog_brilliance = _mk_variant(db, prog, 1.74, design_variant="Brilliance")
    p_prog_high = _mk_pricing(db, v_174_prog_brilliance, cat, availability=models.PricingAvailability.RX,
                              price=43200, coating=scc,
                              power_eligibility=models.PowerEligibilityStatus.UNRESOLVED)
    # 1.74 SCC has NO Vision X price printed (dash) - no row for that combo.

    # --- Page 4: FREEFORM LIFESTYLE (RX) - Indoor-only 1.74 behavior ---
    v_174_indoor = _mk_variant(db, sv, 1.74, design_variant="Indoor")
    p_indoor = _mk_pricing(db, v_174_indoor, cat, availability=models.PricingAvailability.RX,
                           price=21150, coating=scc,
                           power_eligibility=models.PowerEligibilityStatus.UNRESOLVED)
    # 1.74 SCC has NO Drive/Drive X/Curved price printed on page 4 (all dash)
    # - Indoor is the ONLY non-dash cell in that row.

    return {"company": co, "sv": sv, "prog": prog,
            "v_150_sph": v_150_sph, "v_160_as": v_160_as, "v_174_indoor": v_174_indoor}


# A. Stock Egypt exact coating-price mapping. Verified directly against the
# DB (like B/C) rather than through the full per-eye search pipeline: this
# catalog prints NO PowerRange for any STOCK row, so - per this import's own
# safety rule (test I) - a STOCK-without-range row is ALWAYS "unavailable"
# in the per-eye/pair pipeline (never a false "stock_egypt" match); the
# catalog-proven price/coating mapping itself lives on the row, not on a
# search result.
def test_A_stock_egypt_coating_price_mapping(db, seiko_setup):
    v = seiko_setup["v_150_sph"]
    rows = db.query(models.VariantPricing).filter(
        models.VariantPricing.variant_id == v.id, models.VariantPricing.market_scope == "Egypt",
    ).all()
    by_coating = {p.coating.code: float(p.price_pair) for p in rows}
    assert by_coating == {"SRC - ONE": 2025.0, "SRC - SCREEN": 3037.0}


# B. Stock Out Of Egypt positional mapping: 1.5 SPH SCC=2250, SRC ONE=2925, SRC SCREEN=3825.
def test_B_stock_ooe_positional_mapping(db, seiko_setup):
    v = seiko_setup["v_150_sph"]
    rows = db.query(models.VariantPricing).filter(
        models.VariantPricing.variant_id == v.id,
        models.VariantPricing.market_scope == "Out Of Egypt",
        models.VariantPricing.availability == models.PricingAvailability.STOCK,
    ).all()
    by_coating = {p.coating.code: float(p.price_pair) for p in rows}
    assert by_coating == {"SCC": 2250.0, "SRC - ONE": 2925.0, "SRC - SCREEN": 3825.0}


# C. 1.60 OOE multi-coating row maps correctly (4 coatings, 4 prices, positional).
def test_C_1_60_ooe_multi_coating(db, seiko_setup):
    v = seiko_setup["v_160_as"]
    rows = db.query(models.VariantPricing).filter(
        models.VariantPricing.variant_id == v.id,
        models.VariantPricing.market_scope == "Out Of Egypt",
    ).all()
    by_coating = {p.coating.code: float(p.price_pair) for p in rows}
    assert by_coating == {"SCC": 4950.0, "SRC - ONE": 5400.0, "SRC - SCREEN": 6750.0, "SRC ULTRA": 6750.0}


# D. Freeform SV matrix: selected non-dash cells map to the correct row+design+
# price. Per the permanent domain rule, an RX row with zero PowerRange is
# ALWAYS eligible - status is "rx" and the catalog price is shown directly.
def test_D_freeform_sv_matrix_mapping(db, seiko_setup):
    sv = seiko_setup["sv"]
    presc = _mk_presc(db, name="d")
    resp = _targeted(db, presc, lens_model_id=sv.id, index_value=1.60, design_variant="A-Zone")
    assert resp.best_match is not None
    assert resp.best_match.pair_fulfillment.status == "rx"
    assert resp.best_match.pair_fulfillment.price_pair == Decimal("15660.00")


# E. Matrix dashes generate no commercial identity.
def test_E_dash_cells_create_no_identity(db, seiko_setup):
    sv = seiko_setup["sv"]
    # 1.5 SCC x A-Zone is a printed dash on page 2 - no variant/pricing exists.
    v = db.query(models.LensVariant).filter(
        models.LensVariant.lens_model_id == sv.id, models.LensVariant.index_value == 1.50,
        models.LensVariant.design_variant == "A-Zone").first()
    assert v is None


# F. Progressive: low and high rows across the design column range. Per the
# permanent domain rule, an RX row with zero PowerRange/ADD-range is ALWAYS
# eligible - status is "rx" and the catalog price is shown directly.
def test_F_progressive_low_and_high_rows(db, seiko_setup):
    prog = seiko_setup["prog"]
    presc = _mk_presc(db, name="f")
    resp_low = _targeted(db, presc, lens_model_id=prog.id, index_value=1.50, design_variant="Vision X")
    assert resp_low.best_match.pair_fulfillment.status == "rx"
    assert resp_low.best_match.pair_fulfillment.price_pair == Decimal("9000.00")

    resp_high = _targeted(db, presc, lens_model_id=prog.id, index_value=1.74, design_variant="Brilliance")
    assert resp_high.best_match.pair_fulfillment.status == "rx"
    assert resp_high.best_match.pair_fulfillment.price_pair == Decimal("43200.00")

    # 1.74 x Vision X is a printed dash - no row.
    v_dash = db.query(models.LensVariant).filter(
        models.LensVariant.lens_model_id == prog.id, models.LensVariant.index_value == 1.74,
        models.LensVariant.design_variant == "Vision X").first()
    assert v_dash is None


# G. Lifestyle: Indoor-only 1.74 behavior - Indoor priced, other Lifestyle
# designs for 1.74 are dashes (no row), never fabricated.
def test_G_lifestyle_indoor_only_1_74(db, seiko_setup):
    sv = seiko_setup["sv"]
    presc = _mk_presc(db, name="g")
    resp = _targeted(db, presc, lens_model_id=sv.id, index_value=1.74, design_variant="Indoor")
    assert resp.best_match.pair_fulfillment.status == "rx"
    assert resp.best_match.pair_fulfillment.price_pair == Decimal("21150.00")
    for dv in ("Drive (RCC)", "Drive X (RCC)", "Curved / Curved X"):
        v_dash = db.query(models.LensVariant).filter(
            models.LensVariant.lens_model_id == sv.id, models.LensVariant.index_value == 1.74,
            models.LensVariant.design_variant == dv).first()
        assert v_dash is None, dv


# H. Category/company boundary.
def test_H_category_and_company_boundary(db, seiko_setup):
    co = seiko_setup["company"]
    hoya = _mk_company(db, "HOYA")
    hoya_cat = _mk_catalog(db, hoya)
    hoya_model = _mk_model(db, hoya, "HOYA", models.LensCategory.SINGLE_VISION)
    v_hoya = _mk_variant(db, hoya_model, 1.50)
    _mk_pricing(db, v_hoya, hoya_cat, availability=models.PricingAvailability.STOCK,
               price=500, market_scope="Egypt")

    presc = _mk_presc(db, name="h")
    f = schemas.LensFilters(company_id=co.id, index_value=1.50)
    req = schemas.ProductSearchRequest(mode="targeted", filters=f, include_alternatives=True)
    resp = product_search.search(db, presc, req)
    for grp in resp.groups:
        for r in grp.results:
            assert r.company_id == co.id

    # progressive/single_vision never mixed for SEIKO itself
    f2 = schemas.LensFilters(company_id=co.id, category=models.LensCategory.SINGLE_VISION)
    req2 = schemas.ProductSearchRequest(mode="targeted", filters=f2, include_alternatives=True)
    resp2 = product_search.search(db, _mk_presc(db, sph=-30.0, name="h2"), req2)
    for alt in (resp2.alternatives or []):
        assert alt.result.lens_model.category == models.LensCategory.SINGLE_VISION


# I. Stock-without-PowerRange is not fabricated as prescription-proven.
def test_I_stock_without_range_not_fabricated_proven(db, seiko_setup):
    v = seiko_setup["v_150_sph"]
    p = db.query(models.VariantPricing).filter(
        models.VariantPricing.variant_id == v.id, models.VariantPricing.market_scope == "Egypt",
        models.VariantPricing.coating_id.isnot(None),
    ).first()
    presc = _mk_presc(db, sph=-2.0, cyl=-1.0, name="i")
    status = product_search._row_eye_status(p, presc, "od")
    assert status == "ineligible"
    assert list(p.power_ranges) == []


# J. RX-without-range is ALWAYS eligible (permanent domain rule: a
# manufacturing lens is made to order; absence of a printed range means "no
# restriction supplied", never "unknown"), regardless of the row's
# power_eligibility flag value.
def test_J_rx_without_range_always_eligible(db, seiko_setup):
    # find the Freeform A-Zone RX row created in the fixture
    prog_or_sv_rows = db.query(models.VariantPricing).filter(
        models.VariantPricing.availability == models.PricingAvailability.RX,
    ).all()
    az = [p for p in prog_or_sv_rows if p.price_pair == Decimal("15660.00")][0]
    assert az.power_eligibility == models.PowerEligibilityStatus.UNRESOLVED
    assert list(az.power_ranges) == []
    presc = _mk_presc(db, sph=-2.0, cyl=-1.0, name="j")
    status = product_search._row_eye_status(az, presc, "od")
    assert status == "eligible"


# K. Coatings/add-ons are not duplicated as base lenses - no VariantPricing
# row exists whose price matches a page-5 add-on value in isolation with no
# real lens identity behind it (the add-on evidence lives only in
# seiko_addons_evidence.py, never in VariantPricing).
def test_K_addons_not_duplicated_as_base_lenses(db, seiko_setup):
    co = seiko_setup["company"]
    addon_prices = {1125, 1350, 2475}
    rows = (db.query(models.VariantPricing).join(models.LensVariant).join(models.LensModel)
            .filter(models.LensModel.company_id == co.id).all())
    for p in rows:
        assert float(p.price_pair) not in addon_prices, (
            f"pricing {p.id} accidentally matches an add-on surcharge value {p.price_pair} - "
            "add-ons must never be written as base VariantPricing rows")


# L. Expected page pricing counts after the TRIBRID SCC exclusion (no printed
# index for that row in any of the three Freeform tables): the real import
# totals 77 + 77 + 43 = 197 (the catalog's raw, pre-exclusion cell count is
# 79 + 81 + 47 = 207). This synthetic fixture seeds a known, fixed 14-row
# representative subset (2 Stock Egypt + 3 Stock OOE 1.5SPH + 4 Stock OOE
# 1.60AS + 1 Freeform SV + 1 Progressive-low + 1 Progressive-high... see
# seiko_setup) - this test locks in that the company-scoped, current-rows-
# only counting method itself is correct and stable; the full 197 total is
# verified directly against the live DB in the import's own acceptance
# report, not re-derived here.
def test_L_page_pricing_counts(db, seiko_setup):
    co = seiko_setup["company"]
    n = (db.query(models.VariantPricing).join(models.LensVariant).join(models.LensModel)
         .filter(models.LensModel.company_id == co.id, models.VariantPricing.effective_to.is_(None))
         .count())
    assert n == 14
