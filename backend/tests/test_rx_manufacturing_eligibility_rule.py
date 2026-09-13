"""Permanent regression coverage for the global RX/STOCK manufacturing-
eligibility domain rule (BBGR import phase).

Authoritative rule: a manufacturing (RX) lens is made to order and is NOT
dependent on a manufacturer-printed PowerRange by default. Absence of a
printed range means "no restriction supplied", never "unknown" and never
"incompatible" - so an RX row with zero PowerRange is ALWAYS eligible and
its catalog price is usable directly. ONLY an explicit manufacturer-printed
range (SPH/CYL limits, Total Sph+Cyl, Max Cyl, ADD range, diameter-dependent
limits) narrows an RX row's eligibility.

STOCK is different and unaffected: a STOCK row still requires a proven Stock
PowerRange to be reported as prescription-compatible - a STOCK row with zero
PowerRange proves only that the lens is commercially priced and stocked,
never that a specific prescription's power is physically in inventory.

This file is deliberately generic (no manufacturer-specific fixtures) -
company-agnostic coverage of `_row_eye_status` and the full /search path.
Manufacturer-specific consequences of this same rule are covered separately
in each catalog's own test file (test_synchrony_import.py,
test_seiko_import.py, test_pixel_page16_page17_reconciliation.py,
test_bbgr_import.py, ...) and in test_phase5_eligibility_safety.py /
test_phase4i_zeiss_svrx_closure.py (rewritten in place for this same rule).
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


def _mk_variant(db, model, index_value=1.5):
    v = models.LensVariant(
        lens_model_id=model.id, material=models.MaterialType.CR39, index_value=index_value,
        design_type=models.DesignType.SPHERICAL, is_aspherical=False, price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    return v


def _mk_pricing(db, variant, catalog, *, availability, price,
                power_eligibility=models.PowerEligibilityStatus.UNRESTRICTED, market_scope=None):
    vp = models.VariantPricing(
        variant_id=variant.id, availability=availability, power_eligibility=power_eligibility,
        price_pair=Decimal(str(price)), currency="EGP", source_catalog_id=catalog.id,
        market_scope=market_scope)
    db.add(vp); db.commit(); db.refresh(vp)
    return vp


def _mk_range(db, model, variant, pricing, sph_min, sph_max, cyl_min=-4.0, cyl_max=0.0):
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


def _targeted(db, presc, model, **extra):
    f = schemas.LensFilters(lens_model_id=model.id, **extra)
    req = schemas.ProductSearchRequest(mode="targeted", filters=f)
    return product_search.search(db, presc, req)


# 1. RX + zero PowerRange -> Manufacturing eligible (both power_eligibility
# values, since the flag no longer drives this decision at all).
@pytest.mark.parametrize("flag", [
    models.PowerEligibilityStatus.UNRESTRICTED,
    models.PowerEligibilityStatus.UNRESOLVED,
])
def test_1_rx_zero_range_always_eligible(db, flag):
    co = _mk_company(db, "GenericMfr")
    cat = _mk_catalog(db, co)
    model = _mk_model(db, co, "GenericMfr", models.LensCategory.SINGLE_VISION)
    v = _mk_variant(db, model)
    p = _mk_pricing(db, v, cat, availability=models.PricingAvailability.RX,
                    price=5000, power_eligibility=flag)
    for sph in (-2.0, -25.0, 9.0):   # normal and extreme - never rejected
        presc = _mk_presc(db, sph, name=f"n-{sph}")
        status = product_search._row_eye_status(p, presc, "od")
        assert status == "eligible", (flag, sph)
    resp = _targeted(db, _mk_presc(db, -2.0, name="search"), model)
    assert resp.best_match.pair_fulfillment.status == "rx"
    assert resp.best_match.pair_fulfillment.price_pair == Decimal("5000.00")


# 2. RX + explicit PowerRange -> limits are enforced exactly (inside proven,
# outside rejected) - unaffected by this rule, still the ONLY thing that
# narrows an RX row's eligibility.
def test_2_rx_explicit_range_still_enforced(db):
    co = _mk_company(db, "GenericMfr2")
    cat = _mk_catalog(db, co)
    model = _mk_model(db, co, "GenericMfr2", models.LensCategory.SINGLE_VISION)
    v = _mk_variant(db, model)
    p = _mk_pricing(db, v, cat, availability=models.PricingAvailability.RX, price=6000)
    _mk_range(db, model, v, p, -6.0, 0.0, -2.0, 0.0)
    assert product_search._row_eye_status(p, _mk_presc(db, -3.0, -1.0, name="in"), "od") == "eligible"
    assert product_search._row_eye_status(p, _mk_presc(db, -10.0, -1.0, name="out"), "od") == "ineligible"


# 3. STOCK + zero PowerRange -> NOT claimed prescription-proven.
def test_3_stock_zero_range_not_proven(db):
    co = _mk_company(db, "GenericMfr3")
    cat = _mk_catalog(db, co)
    model = _mk_model(db, co, "GenericMfr3", models.LensCategory.SINGLE_VISION)
    v = _mk_variant(db, model)
    p = _mk_pricing(db, v, cat, availability=models.PricingAvailability.STOCK,
                    price=2000, market_scope="Egypt")
    for sph in (-2.0, 0.0, 2.0):
        status = product_search._row_eye_status(p, _mk_presc(db, sph, name=f"s-{sph}"), "od")
        assert status == "ineligible", sph
    resp = _targeted(db, _mk_presc(db, -2.0, name="search"), model)
    assert resp.best_match.pair_fulfillment.status != "stock_egypt"


# 4. STOCK + proven PowerRange -> existing stock behavior unchanged.
def test_4_stock_proven_range_unchanged(db):
    co = _mk_company(db, "GenericMfr4")
    cat = _mk_catalog(db, co)
    model = _mk_model(db, co, "GenericMfr4", models.LensCategory.SINGLE_VISION)
    v = _mk_variant(db, model)
    p = _mk_pricing(db, v, cat, availability=models.PricingAvailability.STOCK,
                    price=1800, market_scope="Egypt")
    _mk_range(db, model, v, p, -4.0, 0.0, -2.0, 0.0)
    resp_in = _targeted(db, _mk_presc(db, -2.0, -1.0, name="in"), model)
    assert resp_in.best_match.pair_fulfillment.status == "stock_egypt"
    assert resp_in.best_match.pair_fulfillment.price_pair == Decimal("1800.00")
    resp_out = _targeted(db, _mk_presc(db, -8.0, -1.0, name="out"), model)
    assert resp_out.best_match.pair_fulfillment.status != "stock_egypt"


# 5. No numeric fake/unlimited PowerRange is ever created for a no-range RX
# row - eligibility comes from the ABSENCE of a range, never from a
# fabricated wide-open one.
def test_5_no_fake_unlimited_range_created(db):
    co = _mk_company(db, "GenericMfr5")
    cat = _mk_catalog(db, co)
    model = _mk_model(db, co, "GenericMfr5", models.LensCategory.SINGLE_VISION)
    v = _mk_variant(db, model)
    p = _mk_pricing(db, v, cat, availability=models.PricingAvailability.RX, price=4000)
    _targeted(db, _mk_presc(db, -2.0, name="x"), model)   # exercise the search path
    assert list(p.power_ranges) == []


# 6. Company/category boundaries remain hard under the new rule too - a
# no-range RX row from one company never leaks into another company's
# results, and category is still a hard boundary.
def test_6_company_category_boundaries_hard(db):
    co_a = _mk_company(db, "MfrA")
    cat_a = _mk_catalog(db, co_a)
    model_a = _mk_model(db, co_a, "MfrA", models.LensCategory.SINGLE_VISION)
    v_a = _mk_variant(db, model_a)
    _mk_pricing(db, v_a, cat_a, availability=models.PricingAvailability.RX, price=3000)

    co_b = _mk_company(db, "MfrB")
    cat_b = _mk_catalog(db, co_b)
    model_b_prog = _mk_model(db, co_b, "MfrB", models.LensCategory.PROGRESSIVE)
    v_b = _mk_variant(db, model_b_prog)
    _mk_pricing(db, v_b, cat_b, availability=models.PricingAvailability.RX, price=9000)

    presc = _mk_presc(db, -2.0, name="boundary")
    f = schemas.LensFilters(company_id=co_a.id, category=models.LensCategory.SINGLE_VISION)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(
        mode="targeted", filters=f, include_alternatives=True))
    for grp in resp.groups:
        for r in grp.results:
            assert r.company_id == co_a.id
    for alt in (resp.alternatives or []):
        assert alt.result.lens_model.category == models.LensCategory.SINGLE_VISION
