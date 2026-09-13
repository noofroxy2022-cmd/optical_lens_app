"""Permanent regression coverage for the PIXEL "Hi Power" price-confirmation
safety correction.

Domain fact: PIXEL's catalog prints a "Hi Power" add-on (+1000 EGP) with NO
stated numeric trigger (no SPH/CYL/Total-Power/index threshold) - the lab/
company decides at order review whether it applies. This is deliberately
kept SEPARATE from two other, already-settled concerns:

  * RX manufacturing eligibility - governed entirely by the permanent RX
    domain rule (a made-to-order RX row with zero PowerRange is always
    eligible; see test_rx_manufacturing_eligibility_rule.py). Hi Power's
    unresolved trigger does NOT reopen or weaken this - PIXEL RX rows stay
    fully eligible.
  * Proven-pair provenance (`needs_review` / "unproven_mixed" /
    "eligibility_unknown") - about whether a SINGLE catalog offer covers
    both eyes, nothing to do with a possible later surcharge.

The generic mechanism: `VariantPricing.price_confirmation_note` (nullable,
manufacturer-agnostic) carries a catalog-proven caveat string, propagated
verbatim into `PairFulfillment.price_confirmation_note` whenever that row
proves a "single_route" pair. NULL (every other company, and PIXEL's own
STOCK rows) means no caveat. No numeric Hi Power trigger is ever invented;
no automatic +1000 is ever added to any price.
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
from app.pixel_addons_evidence import HI_POWER_CONFIRMATION_NOTE, ADDITIONS  # noqa: E402


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


def _mk_pricing(db, variant, catalog, *, availability, price, market_scope=None,
                price_confirmation_note=None):
    vp = models.VariantPricing(
        variant_id=variant.id, availability=availability, price_pair=Decimal(str(price)),
        currency="EGP", source_catalog_id=catalog.id, market_scope=market_scope,
        price_confirmation_note=price_confirmation_note)
    db.add(vp); db.commit(); db.refresh(vp)
    return vp


def _mk_presc(db, sph=0.0, cyl=0.0, name="p"):
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


@pytest.fixture()
def pixel_setup(db):
    co = _mk_company(db, "Pixel")
    cat = _mk_catalog(db, co)
    model = _mk_model(db, co, "Pixel", models.LensCategory.SINGLE_VISION)
    v = _mk_variant(db, model)
    p_rx = _mk_pricing(db, v, cat, availability=models.PricingAvailability.RX, price=6000,
                       price_confirmation_note=HI_POWER_CONFIRMATION_NOTE)

    stock_model = _mk_model(db, co, "PixelStock", models.LensCategory.SINGLE_VISION)
    v_stock = _mk_variant(db, stock_model, index_value=1.6)
    p_stock = _mk_pricing(db, v_stock, cat, availability=models.PricingAvailability.STOCK,
                          price=2000, market_scope="Egypt")   # no Hi Power note - stock unaffected

    return {"company": co, "model": model, "v": v, "p_rx": p_rx,
            "stock_model": stock_model, "v_stock": v_stock, "p_stock": p_stock}


# A. PIXEL RX + no PowerRange -> manufacturing eligible.
def test_A_pixel_rx_no_range_eligible(db, pixel_setup):
    model = pixel_setup["model"]
    for sph in (-2.0, -25.0, 9.0):
        presc = _mk_presc(db, sph, name=f"a-{sph}")
        resp = _targeted(db, presc, model)
        assert resp.best_match.pair_fulfillment.status == "rx", sph


# B. PIXEL base price remains visible (never hidden by the caveat).
def test_B_pixel_base_price_visible(db, pixel_setup):
    model = pixel_setup["model"]
    presc = _mk_presc(db, -2.0, name="b")
    resp = _targeted(db, presc, model)
    pf = resp.best_match.pair_fulfillment
    assert pf.price_pair == Decimal("6000.00")
    assert pf.currency == "EGP"


# C. Hi Power +1000 is NOT auto-added to the price.
def test_C_hi_power_not_auto_added(db, pixel_setup):
    model = pixel_setup["model"]
    presc = _mk_presc(db, -2.0, name="c")
    resp = _targeted(db, presc, model)
    pf = resp.best_match.pair_fulfillment
    assert pf.price_pair == Decimal("6000.00")
    assert pf.price_pair != Decimal("7000.00")
    assert ADDITIONS["Hi Power"] == 1000   # evidence only, never composed into price_pair


# D. PIXEL final-price caveat / manual-confirmation note is surfaced,
# verbatim, alongside the (still fully visible) proven price.
def test_D_final_price_caveat_surfaced(db, pixel_setup):
    model = pixel_setup["model"]
    presc = _mk_presc(db, -2.0, name="d")
    resp = _targeted(db, presc, model)
    pf = resp.best_match.pair_fulfillment
    assert pf.price_confirmation_note == HI_POWER_CONFIRMATION_NOTE
    assert "Hi Power" in pf.price_confirmation_note
    assert pf.status == "rx"                 # eligibility untouched
    assert pf.price_pair is not None          # price never hidden
    assert pf.needs_review is False           # distinct from provenance "needs review"


# E. No numeric Hi Power threshold is invented anywhere in the eligibility path.
def test_E_no_numeric_threshold_invented(db, pixel_setup):
    v = pixel_setup["v"]
    assert list(v.power_ranges) == []
    for sph, cyl in [(-2.0, -1.0), (-30.0, -12.0), (30.0, 0.0)]:
        presc = _mk_presc(db, sph, cyl, name=f"e-{sph}-{cyl}")
        status = product_search._row_eye_status(pixel_setup["p_rx"], presc, "od")
        assert status == "eligible", (sph, cyl)   # no SPH/CYL cutoff was ever added


# F. BBGR RX price remains directly usable without any PIXEL caveat.
def test_F_bbgr_unaffected_by_pixel_caveat(db):
    co = _mk_company(db, "BBGR")
    cat = _mk_catalog(db, co)
    model = _mk_model(db, co, "BBGR", models.LensCategory.SINGLE_VISION)
    v = _mk_variant(db, model, index_value=1.59)
    _mk_pricing(db, v, cat, availability=models.PricingAvailability.RX, price=2250)
    presc = _mk_presc(db, -2.0, name="f")
    resp = _targeted(db, presc, model)
    pf = resp.best_match.pair_fulfillment
    assert pf.status == "rx"
    assert pf.price_pair == Decimal("2250.00")
    assert pf.price_confirmation_note is None


# G. HOYA/ZEISS/Synchrony/Maxxee/SEIKO unaffected - the caveat is data-driven
# (only present where explicitly set), never company-code-driven.
def test_G_other_manufacturers_unaffected(db):
    for name in ("HOYA", "ZEISS", "Synchrony", "Maxxee", "SEIKO"):
        co = _mk_company(db, name)
        cat = _mk_catalog(db, co)
        model = _mk_model(db, co, name, models.LensCategory.SINGLE_VISION)
        v = _mk_variant(db, model)
        _mk_pricing(db, v, cat, availability=models.PricingAvailability.RX, price=3000)
        presc = _mk_presc(db, -2.0, name=f"g-{name}")
        resp = _targeted(db, presc, model)
        pf = resp.best_match.pair_fulfillment
        assert pf.status == "rx", name
        assert pf.price_confirmation_note is None, name


# H. Stock semantics unchanged: PIXEL's own STOCK row (no Hi Power note) is
# still not claimed prescription-proven with zero PowerRange.
def test_H_stock_semantics_unchanged(db, pixel_setup):
    p_stock = pixel_setup["p_stock"]
    assert p_stock.price_confirmation_note is None
    presc = _mk_presc(db, -2.0, -1.0, name="h")
    status = product_search._row_eye_status(p_stock, presc, "od")
    assert status == "ineligible"
