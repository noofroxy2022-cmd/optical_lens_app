"""Phase 3 - lens matcher migrated from legacy LensVariant commercial fields to
CURRENT VariantPricing. All test data is built directly with the commercial models.
"""
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database import Base  # noqa: E402
from app import models, schemas, database  # noqa: E402
from app.lens_matcher import lens_matcher  # noqa: E402


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


# ----- builders --------------------------------------------------------------
def _company(db, name="ACME"):
    c = models.Company(name=name)
    db.add(c); db.commit(); db.refresh(c)
    return c


def _model(db, company, name="M1", features=None):
    m = models.LensModel(company_id=company.id, name=name,
                         category=models.LensCategory.SINGLE_VISION, features=features)
    db.add(m); db.commit(); db.refresh(m)
    return m


def _catalog(db, company):
    cat = models.Catalog(company_id=company.id, filename="c.pdf", file_path="/x",
                         status=models.CatalogStatus.CONFIRMED)
    db.add(cat); db.commit(); db.refresh(cat)
    return cat


def _coating(db, code="HMC", name="Hard Multi Coat"):
    c = models.Coating(code=code, name=name)
    db.add(c); db.commit(); db.refresh(c)
    return c


def _variant(db, model, *, material=models.MaterialType.CR39, index=1.5,
             design_type=models.DesignType.SPHERICAL, is_aspherical=False,
             design_variant=None, color_variant=None,
             legacy_price=0.0, legacy_availability=models.LensAvailability.STOCK,
             legacy_currency="USD"):
    v = models.LensVariant(
        lens_model_id=model.id, material=material, index_value=index,
        design_type=design_type, is_aspherical=is_aspherical,
        design_variant=design_variant, color_variant=color_variant,
        availability=legacy_availability, price=legacy_price, currency=legacy_currency,
    )
    db.add(v); db.commit(); db.refresh(v)
    return v


def _pricing(db, variant, catalog, *, availability="stock", price="100.00",
             coating=None, market_scope=None, power_scope=None, current=True,
             age_days=0):
    ef = datetime.utcnow() - timedelta(days=age_days + 1)
    vp = models.VariantPricing(
        variant_id=variant.id,
        coating_id=(coating.id if coating else None),
        availability=models.PricingAvailability(availability),
        price_pair=Decimal(price),
        currency="EGP",
        source_catalog_id=catalog.id,
        source_extraction_id=None,
        effective_from=ef,
        effective_to=(None if current else datetime.utcnow()),
        power_scope=power_scope,
        market_scope=market_scope,
    )
    db.add(vp); db.commit(); db.refresh(vp)
    return vp


def _range(db, pricing, variant, *, sph_min, sph_max, cyl_min=-6.0, cyl_max=0.0):
    pr = models.PowerRange(
        lens_model_id=variant.lens_model_id, variant_id=variant.id,
        pricing_id=pricing.id, sph_min=sph_min, sph_max=sph_max,
        cyl_min=cyl_min, cyl_max=cyl_max,
    )
    db.add(pr); db.commit(); db.refresh(pr)
    return pr


def _rx(db, sph):
    p = models.Prescription(
        od_sph_original=sph, os_sph_original=sph, od_sph=sph, os_sph=sph,
        od_cyl_original=0.0, os_cyl_original=0.0, od_cyl=0.0, os_cyl=0.0,
        od_axis=0, os_axis=0, od_add=0.0, os_add=0.0,
    )
    db.add(p); db.commit(); db.refresh(p)
    return p


def _match(db, rx, filters=None, prefer_stock=True):
    return lens_matcher.match_lenses(db, rx, filters, prefer_stock, True)


# ===========================================================================
def test_A_variant_without_current_pricing_is_excluded(db):
    co = _company(db); cat = _catalog(db, co); m = _model(db, co)
    v = _variant(db, m)
    # only a historical price
    old = _pricing(db, v, cat, availability="stock", price="100.00", current=False)
    _range(db, old, v, sph_min=-6.0, sph_max=0.0)
    results, sc, rc, *_ = _match(db, _rx(db, -3.0))
    assert results == []
    assert (sc, rc) == (0, 0)


def test_B_historical_pricing_is_excluded(db):
    co = _company(db); cat = _catalog(db, co); m = _model(db, co)
    v = _variant(db, m)
    hist = _pricing(db, v, cat, availability="stock", price="2500.00", current=False)
    _range(db, hist, v, sph_min=-6.0, sph_max=0.0)
    cur = _pricing(db, v, cat, availability="stock", price="2700.00", current=True)
    _range(db, cur, v, sph_min=-6.0, sph_max=0.0)
    results, *_ = _match(db, _rx(db, -3.0))
    assert len(results) == 1
    assert results[0].price_pair == Decimal("2700.00")
    assert results[0].source_pricing_id == cur.id


def test_C_current_rx_zero_power_ranges_is_returned(db):
    co = _company(db); cat = _catalog(db, co); m = _model(db, co)
    v = _variant(db, m)
    _pricing(db, v, cat, availability="rx", price="400.00", current=True)
    results, sc, rc, *_ = _match(db, _rx(db, -2.0))
    assert len(results) == 1
    assert results[0].availability == "rx"
    assert results[0].power_range is None
    assert results[0].price_pair == Decimal("400.00")
    assert (sc, rc) == (0, 1)


def test_D_rx_without_range_matches_extreme_prescription(db):
    co = _company(db); cat = _catalog(db, co); m = _model(db, co)
    v = _variant(db, m, index=1.74, is_aspherical=True)
    _pricing(db, v, cat, availability="rx", price="900.00", current=True)
    results, *_ = _match(db, _rx(db, -18.0))
    assert len(results) == 1
    assert results[0].availability == "rx"


def test_E_stock_inside_pricing_range_returned_with_exact_price(db):
    co = _company(db); cat = _catalog(db, co); m = _model(db, co)
    v = _variant(db, m)
    p = _pricing(db, v, cat, availability="stock", price="2500.00")
    r = _range(db, p, v, sph_min=-6.0, sph_max=0.0)
    results, *_ = _match(db, _rx(db, -3.0))
    assert len(results) == 1
    res = results[0]
    assert res.availability == "stock"
    assert res.price_pair == Decimal("2500.00")
    assert res.source_pricing_id == p.id
    assert res.power_range is not None and res.power_range.id == r.id


def test_F_stock_outside_pricing_range_excluded(db):
    co = _company(db); cat = _catalog(db, co); m = _model(db, co)
    v = _variant(db, m)
    p = _pricing(db, v, cat, availability="stock", price="2500.00")
    _range(db, p, v, sph_min=-6.0, sph_max=0.0)
    results, *_ = _match(db, _rx(db, 5.0))
    assert results == []


def test_G_stock_priority_over_rx_same_variant_same_coating(db):
    co = _company(db); cat = _catalog(db, co); m = _model(db, co)
    v = _variant(db, m)
    pa = _pricing(db, v, cat, availability="stock", price="100.00")
    _range(db, pa, v, sph_min=-6.0, sph_max=0.0)
    _pricing(db, v, cat, availability="rx", price="300.00")   # no range

    inside = _match(db, _rx(db, -3.0))[0]
    assert [r.availability for r in inside] == ["stock"]      # RX suppressed

    outside = _match(db, _rx(db, 5.0))[0]
    assert [r.availability for r in outside] == ["rx"]        # no stock match -> RX kept


def test_H_different_coating_rx_not_suppressed(db):
    co = _company(db); cat = _catalog(db, co); m = _model(db, co)
    v = _variant(db, m)
    hmc = _coating(db, code="HMC")
    pa = _pricing(db, v, cat, availability="stock", price="100.00", coating=None)
    _range(db, pa, v, sph_min=-6.0, sph_max=0.0)
    _pricing(db, v, cat, availability="rx", price="200.00", coating=hmc)  # no range

    results, *_ = _match(db, _rx(db, -3.0))
    avail_by_coating = {(r.availability, r.coating_code) for r in results}
    assert ("stock", None) in avail_by_coating
    assert ("rx", "HMC") in avail_by_coating
    assert len(results) == 2


def test_I_two_stock_power_scopes_route_to_correct_price(db):
    co = _company(db); cat = _catalog(db, co); m = _model(db, co)
    v = _variant(db, m)
    pa = _pricing(db, v, cat, availability="stock", price="2500.00", power_scope="A")
    _range(db, pa, v, sph_min=-6.0, sph_max=0.0)
    pb = _pricing(db, v, cat, availability="stock", price="5500.00", power_scope="B")
    _range(db, pb, v, sph_min=0.0, sph_max=4.0)

    low = _match(db, _rx(db, -3.0))[0]
    assert len(low) == 1 and low[0].price_pair == Decimal("2500.00")
    assert low[0].source_pricing_id == pa.id

    high = _match(db, _rx(db, 2.0))[0]
    assert len(high) == 1 and high[0].price_pair == Decimal("5500.00")
    assert high[0].source_pricing_id == pb.id


def test_J_two_market_scopes_stay_distinct_unless_filtered(db):
    co = _company(db); cat = _catalog(db, co); m = _model(db, co)
    v = _variant(db, m)
    pe = _pricing(db, v, cat, availability="stock", price="100.00", market_scope="egypt")
    _range(db, pe, v, sph_min=-6.0, sph_max=0.0)
    po = _pricing(db, v, cat, availability="stock", price="130.00", market_scope="out_of_egypt")
    _range(db, po, v, sph_min=-6.0, sph_max=0.0)

    both = _match(db, _rx(db, -3.0))[0]
    assert {r.market_scope for r in both} == {"egypt", "out_of_egypt"}
    assert len(both) == 2

    only_eg = _match(db, _rx(db, -3.0), filters=schemas.LensFilters(market_scope="egypt"))[0]
    assert len(only_eg) == 1 and only_eg[0].market_scope == "egypt"


def test_K_color_variants_stay_distinct(db):
    co = _company(db); cat = _catalog(db, co); m = _model(db, co)
    for cv in ("Clear", "Transmatic/G/B"):
        v = _variant(db, m, color_variant=cv)
        p = _pricing(db, v, cat, availability="stock", price="100.00")
        _range(db, p, v, sph_min=-6.0, sph_max=0.0)
    results, *_ = _match(db, _rx(db, -3.0))
    assert {r.color_variant for r in results} == {"Clear", "Transmatic/G/B"}
    assert len({r.variant.id for r in results}) == 2


def test_L_design_variants_stay_distinct(db):
    co = _company(db); cat = _catalog(db, co); m = _model(db, co)
    for dv in ("Free Form", "High Definition"):
        v = _variant(db, m, design_variant=dv)
        p = _pricing(db, v, cat, availability="stock", price="100.00")
        _range(db, p, v, sph_min=-6.0, sph_max=0.0)
    results, *_ = _match(db, _rx(db, -3.0))
    assert {r.design_variant for r in results} == {"Free Form", "High Definition"}


def test_M_max_price_uses_price_pair_not_legacy(db):
    co = _company(db); cat = _catalog(db, co); m = _model(db, co)
    cheap = _variant(db, m, design_variant="Cheap", legacy_price=9999.0)
    pc = _pricing(db, cheap, cat, availability="stock", price="100.00")
    _range(db, pc, cheap, sph_min=-6.0, sph_max=0.0)
    dear = _variant(db, m, design_variant="Dear", legacy_price=1.0)
    pd = _pricing(db, dear, cat, availability="stock", price="500.00")
    _range(db, pd, dear, sph_min=-6.0, sph_max=0.0)

    results, *_ = _match(db, _rx(db, -3.0), filters=schemas.LensFilters(max_price=200.0))
    assert [r.price_pair for r in results] == [Decimal("100.00")]
    assert results[0].design_variant == "Cheap"


def test_N_availability_filter_uses_pricing_not_legacy(db):
    co = _company(db); cat = _catalog(db, co); m = _model(db, co)
    v = _variant(db, m, legacy_availability=models.LensAvailability.RX)  # contradictory legacy
    ps = _pricing(db, v, cat, availability="stock", price="100.00")
    _range(db, ps, v, sph_min=-6.0, sph_max=0.0)
    _pricing(db, v, cat, availability="rx", price="200.00")  # no range

    only_stock = _match(db, _rx(db, -3.0),
                        filters=schemas.LensFilters(availability=schemas.LensAvailability.STOCK))[0]
    assert [r.availability for r in only_stock] == ["stock"]

    only_rx = _match(db, _rx(db, -3.0),
                     filters=schemas.LensFilters(availability=schemas.LensAvailability.RX))[0]
    assert [r.availability for r in only_rx] == ["rx"]


def test_O_response_exposes_commercial_dimensions(db):
    co = _company(db); cat = _catalog(db, co); m = _model(db, co)
    hmc = _coating(db, code="HMC", name="Hard Multi Coat")
    v = _variant(db, m, design_variant="Free Form", color_variant="Clear")
    p = _pricing(db, v, cat, availability="stock", price="2500.00",
                 coating=hmc, market_scope="egypt", power_scope="A")
    _range(db, p, v, sph_min=-6.0, sph_max=0.0)
    res = _match(db, _rx(db, -3.0))[0][0]
    assert res.design_variant == "Free Form"
    assert res.color_variant == "Clear"
    assert res.coating_code == "HMC" and res.coating_name == "Hard Multi Coat"
    assert res.coating_id == hmc.id
    assert res.availability == "stock"
    assert res.market_scope == "egypt"
    assert res.power_scope == "A"
    assert res.price_pair == Decimal("2500.00")
    assert res.currency == "EGP"
    assert res.source_pricing_id == p.id
    assert res.source_catalog_id == cat.id


def test_P_contradictory_legacy_fields_have_no_effect(db):
    co = _company(db); cat = _catalog(db, co); m = _model(db, co)
    v = _variant(db, m, legacy_price=999999.0,
                 legacy_availability=models.LensAvailability.RX, legacy_currency="ZZZ")
    p = _pricing(db, v, cat, availability="stock", price="100.00")
    _range(db, p, v, sph_min=-6.0, sph_max=0.0)
    res = _match(db, _rx(db, -3.0))[0][0]
    assert res.availability == "stock"
    assert res.price_pair == Decimal("100.00")
    assert res.currency == "EGP"
    assert "999999" not in res.reason and "ZZZ" not in res.reason


def test_Q_decimal_price_exact_in_result(db):
    co = _company(db); cat = _catalog(db, co); m = _model(db, co)
    v = _variant(db, m)
    p = _pricing(db, v, cat, availability="stock", price="1234.56")
    _range(db, p, v, sph_min=-6.0, sph_max=0.0)
    res = _match(db, _rx(db, -3.0))[0][0]
    assert isinstance(res.price_pair, Decimal)
    assert res.price_pair == Decimal("1234.56")
    assert str(res.price_pair) == "1234.56"


def test_reason_text_has_no_legacy_commercial_reads(db):
    co = _company(db); cat = _catalog(db, co); m = _model(db, co)
    v = _variant(db, m, legacy_availability=models.LensAvailability.BOTH, legacy_price=42.0)
    p = _pricing(db, v, cat, availability="rx", price="777.00")
    res = _match(db, _rx(db, -2.0))[0][0]
    assert "RX" in res.reason
    assert "777" in res.reason and "EGP" in res.reason
