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


# ===========================================================================
# Signed-cylinder PowerRange + convention-aware matching
#   catalog range keeps its sign:  Cyl(-3) -> [-3,0] ,  Cyl(+3) -> [0,+3]
#   an Rx is compared in the representation matching the range's cyl sign,
#   SPH+CYL+AXIS moving together; the catalog range is never transposed.
# ===========================================================================
from app.lens_matcher import TranspositionEngine as _TE, LensMatcherFinal as _LMF

_M = _LMF()


def _stored_rx(db, od, os_=None):
    """Persist a prescription the way crud.create_prescription does: the ENTERED
    (sph,cyl,axis) is transposed to the minus form for storage. od/os_ are
    (sph, cyl, axis) as originally entered (either notation)."""
    os_ = os_ or od
    ot = _TE.transpose(od[0], od[1], od[2])
    st = _TE.transpose(os_[0], os_[1], os_[2])
    p = models.Prescription(
        od_sph_original=od[0], od_cyl_original=od[1], od_axis_original=od[2],
        os_sph_original=os_[0], os_cyl_original=os_[1], os_axis_original=os_[2],
        od_sph=ot[0], od_cyl=ot[1], od_axis=ot[2],
        os_sph=st[0], os_cyl=st[1], os_axis=st[2],
        od_add=0.0, os_add=0.0,
        transposition_applied=(od[1] > 0 or os_[1] > 0),
    )
    db.add(p); db.commit(); db.refresh(p)
    return p


# -- A/B. ORM signed-CYL bounds -------------------------------------------
def test_sc_A_orm_accepts_plus_and_minus_cyl(db):
    co = _company(db); m = _model(db, co); cat = _catalog(db, co)
    v = _variant(db, m); vp = _pricing(db, v, cat, price="100.00")
    for cn, cx in ((-3.0, 0.0), (0.0, 3.0), (0.0, 0.0)):
        pr = models.PowerRange(lens_model_id=m.id, variant_id=v.id, pricing_id=vp.id,
                               sph_min=-2.0, sph_max=2.0, cyl_min=cn, cyl_max=cx)
        db.add(pr); db.commit()
    assert db.query(models.PowerRange).count() == 3


def test_sc_B_orm_rejects_out_of_range_cyl(db):
    co = _company(db); m = _model(db, co); cat = _catalog(db, co)
    v = _variant(db, m); vp = _pricing(db, v, cat, price="100.00")
    for bad in (-10.5, 10.5):
        with pytest.raises(ValueError):
            models.PowerRange(lens_model_id=m.id, variant_id=v.id, pricing_id=vp.id,
                              sph_min=0.0, sph_max=1.0, cyl_min=bad, cyl_max=0.0)


# -- C/D. Pydantic bounds + minus serialization unchanged ---------------
def test_sc_C_pydantic_accepts_positive_cyl():
    ok = schemas.PowerRangeCreate(lens_model_id=1, sph_min=0.0, sph_max=3.0,
                                  cyl_min=0.0, cyl_max=3.0)
    assert ok.cyl_max == 3.0
    with pytest.raises(Exception):
        schemas.PowerRangeCreate(lens_model_id=1, sph_min=0.0, sph_max=1.0,
                                 cyl_min=0.0, cyl_max=11.0)


def test_sc_D_minus_cyl_serialization_unchanged(db):
    co = _company(db); m = _model(db, co); cat = _catalog(db, co)
    v = _variant(db, m); vp = _pricing(db, v, cat, price="100.00")
    pr = _range(db, vp, v, sph_min=-6.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0)
    out = schemas.PowerRangeResponse.model_validate(pr)
    assert (out.cyl_min, out.cyl_max, out.sph_min, out.sph_max) == (-2.0, 0.0, -6.0, 0.0)


# -- E/F. plus-form derivation; SPH moves with CYL ---------------------
def test_sc_E_plus_form_derivation_axis_convention():
    # minus (+1, -2, x170)  ->  plus (-1, +2, x80)
    assert _M._plus_form(1.0, -2.0, 170) == (-1.0, 2.0, 80)
    # axis wrap to 180
    assert _M._plus_form(-1.0, -2.0, 90) == (-3.0, 2.0, 180)
    # cyl 0 -> unchanged (no axis shift)
    assert _M._plus_form(-3.0, 0.0, 45) == (-3.0, 0.0, 45)


def test_sc_F_sph_changes_together_with_cyl():
    s, c, a = -4.0, -1.5, 10
    ps, pc, pa = _M._plus_form(s, c, a)
    assert pc == -c and ps == round(s + c, 2)      # SPH shifted by C, not just sign flip
    assert ps != s


# -- convention selection ---------------------------------------------
def test_sc_convention_selection():
    def pr(cn, cx):
        return type("PRStub", (), {"cyl_min": cn, "cyl_max": cx})()
    assert _M._range_convention(pr(-3.0, 0.0)) == "minus"
    assert _M._range_convention(pr(0.0, 3.0)) == "plus"
    assert _M._range_convention(pr(0.0, 0.0)) == "minus"      # plano
    assert _M._range_convention(pr(-1.0, 1.0)) == "both"      # zero-spanning


def _setup(db, *, cyl_min, cyl_max, sph_min=-1.0, sph_max=3.0,
           max_cyl_for_high_sph=None, sph_threshold=None):
    co = _company(db); m = _model(db, co); cat = _catalog(db, co)
    v = _variant(db, m); vp = _pricing(db, v, cat, price="1350.00", market_scope="Egypt")
    pr = models.PowerRange(lens_model_id=m.id, variant_id=v.id, pricing_id=vp.id,
                           sph_min=sph_min, sph_max=sph_max,
                           cyl_min=cyl_min, cyl_max=cyl_max,
                           max_cyl_for_high_sph=max_cyl_for_high_sph,
                           sph_threshold=sph_threshold)
    db.add(pr); db.commit(); db.refresh(pr)
    return vp, pr


# -- G. plus PowerRange uses the plus Rx form ------------------------
def test_sc_G_plus_range_uses_plus_form(db):
    vp, _pr = _setup(db, cyl_min=0.0, cyl_max=3.0)          # plus-cyl range [0,+3]
    # entered-minus Rx (+3, -2, x180) whose plus form is (+1, +2, x90)
    rx = _stored_rx(db, (3.0, -2.0, 180))
    res = _match(db, rx)[0]
    assert any(r.source_pricing_id == vp.id for r in res)
    # a Rx whose plus form falls outside must NOT match
    rx2 = _stored_rx(db, (8.0, -2.0, 180))                  # plus form sph +6 -> outside
    assert not any(r.source_pricing_id == vp.id for r in _match(db, rx2)[0])


# -- H. minus PowerRange uses the minus Rx form --------------------
def test_sc_H_minus_range_uses_minus_form(db):
    vp, _pr = _setup(db, cyl_min=-3.0, cyl_max=0.0, sph_min=0.0, sph_max=4.0)
    rx = _stored_rx(db, (3.0, -2.0, 180))                   # minus form in range
    assert any(r.source_pricing_id == vp.id for r in _match(db, rx)[0])
    rx2 = _stored_rx(db, (3.0, -5.0, 180))                  # minus cyl -5 -> outside
    assert not any(r.source_pricing_id == vp.id for r in _match(db, rx2)[0])


# -- I. plano behaviour unchanged --------------------------------
def test_sc_I_plano_range_unchanged(db):
    vp, _pr = _setup(db, cyl_min=0.0, cyl_max=0.0, sph_min=-4.0, sph_max=0.0)
    rx = _stored_rx(db, (-2.0, 0.0, 0))
    assert any(r.source_pricing_id == vp.id for r in _match(db, rx)[0])
    rx2 = _stored_rx(db, (-2.0, -1.0, 90))                  # has cyl -> outside plano
    assert not any(r.source_pricing_id == vp.id for r in _match(db, rx2)[0])


# -- J. defensive zero-spanning range tests both forms ----------
def test_sc_J_zero_spanning_range_tries_both(db):
    vp, pr = _setup(db, cyl_min=-1.0, cyl_max=1.0, sph_min=-4.0, sph_max=4.0)
    assert _M._range_convention(pr) == "both"
    # covered via the minus form (small minus cyl in [-1,+1])
    assert _M.check_power_range(pr, _stored_rx(db, (-2.0, -0.5, 90)), "od")[0] is True
    # a large minus cyl fails the minus form; the plus form (large +cyl) also
    # fails -> genuinely outside both, so overall False (both branches exercised)
    assert _M.check_power_range(pr, _stored_rx(db, (2.0, -3.0, 90)), "od")[0] is False
    # SPH out of window fails regardless of form
    assert _M.check_power_range(pr, _stored_rx(db, (9.0, -0.5, 90)), "od")[0] is False


# -- K. mixed plus/minus OR ranges under one pricing -----------
def test_sc_K_mixed_or_ranges(db):
    co = _company(db); m = _model(db, co); cat = _catalog(db, co)
    v = _variant(db, m); vp = _pricing(db, v, cat, price="1350.00", market_scope="Egypt")
    db.add(models.PowerRange(lens_model_id=m.id, variant_id=v.id, pricing_id=vp.id,
                             sph_min=-4.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0))
    db.add(models.PowerRange(lens_model_id=m.id, variant_id=v.id, pricing_id=vp.id,
                             sph_min=-1.0, sph_max=3.0, cyl_min=0.0, cyl_max=3.0))
    db.commit()
    # covered by the minus range only
    assert any(r.source_pricing_id == vp.id
               for r in _match(db, _stored_rx(db, (-2.0, -1.0, 90)))[0])
    # covered by the plus range only (minus (+3,-2) -> plus (+1,+2))
    assert any(r.source_pricing_id == vp.id
               for r in _match(db, _stored_rx(db, (3.0, -2.0, 180)))[0])
    # covered by neither
    assert not any(r.source_pricing_id == vp.id
                   for r in _match(db, _stored_rx(db, (9.0, -1.0, 90)))[0])


# -- L. _best_matching_range picks per-range SPH representation ---
def test_sc_L_best_range_uses_correct_form_sph(db):
    co = _company(db); m = _model(db, co); cat = _catalog(db, co)
    v = _variant(db, m); vp = _pricing(db, v, cat, price="1350.00", market_scope="Egypt")
    near = models.PowerRange(lens_model_id=m.id, variant_id=v.id, pricing_id=vp.id,
                             sph_min=0.0, sph_max=2.0, cyl_min=0.0, cyl_max=3.0)   # centre +1
    far = models.PowerRange(lens_model_id=m.id, variant_id=v.id, pricing_id=vp.id,
                            sph_min=-3.0, sph_max=3.0, cyl_min=0.0, cyl_max=3.0)   # centre 0
    db.add(near); db.add(far); db.commit(); db.refresh(near)
    rx = _stored_rx(db, (3.0, -2.0, 180))               # plus form sph +1 -> closest to 'near'
    best = _M._best_matching_range([far, near], rx)
    assert best is not None and best.id == near.id


# -- M. high-SPH cylinder cap evaluated with the chosen form -----
def test_sc_M_high_sph_cap_uses_chosen_form(db):
    # plus range; cap: if |sph| >= 1.0 then |cyl| must be <= 1.0
    vp, pr = _setup(db, cyl_min=0.0, cyl_max=3.0, sph_min=-3.0, sph_max=3.0,
                    max_cyl_for_high_sph=1.0, sph_threshold=1.0)
    # plus form (+1, +2): |sph|=1 triggers cap, |cyl|=2 > 1 -> blocked
    assert _M.check_power_range(pr, _stored_rx(db, (3.0, -2.0, 180)), "od")[0] is False
    # plus form (+0.5, +2): |sph|=0.5 < threshold -> cap not triggered -> ok
    assert _M.check_power_range(pr, _stored_rx(db, (2.5, -2.0, 180)), "od")[0] is True


# -- N. result independent of entered notation -------------------
def test_sc_N_entry_notation_independent(db):
    vp_plus, _ = _setup(db, cyl_min=0.0, cyl_max=3.0, sph_min=-1.0, sph_max=3.0)
    # SAME optical Rx, entered two ways:
    rx_minus_entry = _stored_rx(db, (3.0, -2.0, 180))          # minus notation
    rx_plus_entry = _stored_rx(db, (1.0, 2.0, 90))             # plus notation (equivalent)
    # stored normalized forms are identical
    assert (rx_minus_entry.od_sph, rx_minus_entry.od_cyl) == (rx_plus_entry.od_sph, rx_plus_entry.od_cyl)
    a = {r.source_pricing_id for r in _match(db, rx_minus_entry)[0]}
    b = {r.source_pricing_id for r in _match(db, rx_plus_entry)[0]}
    assert vp_plus.id in a and a == b
    # also against an equivalent MINUS-cyl catalog range
    co = _company(db, "ACME2"); m2 = _model(db, co, "M2"); cat2 = _catalog(db, co)
    v2 = _variant(db, m2); vpm = _pricing(db, v2, cat2, price="1400.00", market_scope="Egypt")
    db.add(models.PowerRange(lens_model_id=m2.id, variant_id=v2.id, pricing_id=vpm.id,
                             sph_min=0.0, sph_max=4.0, cyl_min=-3.0, cyl_max=0.0)); db.commit()
    a2 = {r.source_pricing_id for r in _match(db, rx_minus_entry)[0]}
    b2 = {r.source_pricing_id for r in _match(db, rx_plus_entry)[0]}
    assert vpm.id in a2 and a2 == b2


# -- O. existing minus-cylinder matcher path unchanged ----------
def test_sc_O_existing_minus_behaviour_unchanged(db):
    vp, _pr = _setup(db, cyl_min=-2.0, cyl_max=0.0, sph_min=-6.0, sph_max=0.0)
    rx = _stored_rx(db, (-3.0, -1.0, 90))
    res = _match(db, rx)[0]
    assert any(r.source_pricing_id == vp.id for r in res)
    # plus-form derivation never consulted for a minus range: an Rx whose plus
    # form would coincidentally fit must still be judged on its minus form
    rx2 = _stored_rx(db, (-3.0, -5.0, 90))                 # minus cyl -5 -> outside
    assert not any(r.source_pricing_id == vp.id for r in _match(db, rx2)[0])


# ===========================================================================
# Commercial candidate deduplication (matcher-time, structure B).
# One customer option persisted as several CURRENT VariantPricing rows (one per
# power_scope) because the catalog states it with multiple OR PowerRange
# clauses. A prescription covered by >1 clause must yield ONE result.
# Dedupe key: (LensModel.id, LensVariant.id, coating_id, availability,
# norm(market_scope), price_pair, currency). Runs AFTER STOCK-over-RX
# suppression, BEFORE result construction / sort.
# ===========================================================================
def _usd_pricing(db, variant, catalog, *, price="100.00", coating=None,
                 market_scope=None, power_scope=None, availability="stock"):
    vp = models.VariantPricing(
        variant_id=variant.id, coating_id=(coating.id if coating else None),
        availability=models.PricingAvailability(availability), price_pair=Decimal(price),
        currency="USD", source_catalog_id=catalog.id, source_extraction_id=None,
        effective_from=datetime.utcnow() - timedelta(days=1), effective_to=None,
        power_scope=power_scope, market_scope=market_scope,
    )
    db.add(vp); db.commit(); db.refresh(vp)
    return vp


_DD_SEQ = [0]


def _dd_base(db):
    _DD_SEQ[0] += 1
    n = _DD_SEQ[0]
    co = _company(db, f"ACME{n}"); m = _model(db, co, f"M{n}")
    cat = _catalog(db, co); v = _variant(db, m)
    ct = _coating(db, code=f"CT{n}", name=f"Coat {n}")
    return co, m, cat, v, ct


def test_dd_overlapping_clauses_one_result(db):
    _co, _m, cat, v, ct = _dd_base(db)
    vp1 = _pricing(db, v, cat, price="700.00", coating=ct, power_scope="s1")
    _range(db, vp1, v, sph_min=-1.0, sph_max=1.0, cyl_min=-6.0, cyl_max=0.0)
    vp2 = _pricing(db, v, cat, price="700.00", coating=ct, power_scope="s2")
    _range(db, vp2, v, sph_min=-10.0, sph_max=10.0, cyl_min=-6.0, cyl_max=0.0)
    res = _match(db, _rx(db, 0.0))[0]
    assert len(res) == 1
    assert res[0].source_pricing_id == vp1.id            # tighter fit -> higher match_score
    assert res[0].power_range is not None


def test_dd_non_overlap_no_candidate_lost(db):
    _co, _m, cat, v, ct = _dd_base(db)
    vp1 = _pricing(db, v, cat, price="700.00", coating=ct, power_scope="lo")
    _range(db, vp1, v, sph_min=-8.0, sph_max=-4.0)
    vp2 = _pricing(db, v, cat, price="700.00", coating=ct, power_scope="hi")
    _range(db, vp2, v, sph_min=2.0, sph_max=6.0)
    r_lo = _match(db, _rx(db, -6.0))[0]
    r_hi = _match(db, _rx(db, 4.0))[0]
    assert len(r_lo) == 1 and r_lo[0].source_pricing_id == vp1.id
    assert len(r_hi) == 1 and r_hi[0].source_pricing_id == vp2.id


def test_dd_different_price_two_results(db):
    _co, _m, cat, v, ct = _dd_base(db)
    a = _pricing(db, v, cat, price="700.00", coating=ct, power_scope="a")
    _range(db, a, v, sph_min=-6.0, sph_max=6.0)
    b = _pricing(db, v, cat, price="800.00", coating=ct, power_scope="b")
    _range(db, b, v, sph_min=-6.0, sph_max=6.0)
    assert {r.source_pricing_id for r in _match(db, _rx(db, 0.0))[0]} == {a.id, b.id}


def test_dd_different_coating_two_results(db):
    _co, _m, cat, v, ct = _dd_base(db)
    ct2 = _coating(db, code="SHV", name="Super Hi Vision")
    a = _pricing(db, v, cat, price="700.00", coating=ct, power_scope="a")
    _range(db, a, v, sph_min=-6.0, sph_max=6.0)
    b = _pricing(db, v, cat, price="700.00", coating=ct2, power_scope="b")
    _range(db, b, v, sph_min=-6.0, sph_max=6.0)
    assert {r.source_pricing_id for r in _match(db, _rx(db, 0.0))[0]} == {a.id, b.id}


def test_dd_different_market_two_results(db):
    _co, _m, cat, v, ct = _dd_base(db)
    a = _pricing(db, v, cat, price="700.00", coating=ct, market_scope="Egypt", power_scope="a")
    _range(db, a, v, sph_min=-6.0, sph_max=6.0)
    b = _pricing(db, v, cat, price="700.00", coating=ct, market_scope="Out Of Egypt", power_scope="b")
    _range(db, b, v, sph_min=-6.0, sph_max=6.0)
    assert {r.source_pricing_id for r in _match(db, _rx(db, 0.0))[0]} == {a.id, b.id}


def test_dd_different_variant_two_results(db):
    _co, m, cat, v, ct = _dd_base(db)
    v2 = _variant(db, m, index=1.6)
    a = _pricing(db, v, cat, price="700.00", coating=ct, power_scope="a")
    _range(db, a, v, sph_min=-6.0, sph_max=6.0)
    b = _pricing(db, v2, cat, price="700.00", coating=ct, power_scope="b")
    _range(db, b, v2, sph_min=-6.0, sph_max=6.0)
    assert {r.source_pricing_id for r in _match(db, _rx(db, 0.0))[0]} == {a.id, b.id}


def test_dd_different_currency_two_results(db):
    _co, _m, cat, v, ct = _dd_base(db)
    a = _pricing(db, v, cat, price="700.00", coating=ct, power_scope="a")       # EGP
    _range(db, a, v, sph_min=-6.0, sph_max=6.0)
    b = _usd_pricing(db, v, cat, price="700.00", coating=ct, power_scope="b")   # USD
    _range(db, b, v, sph_min=-6.0, sph_max=6.0)
    assert {r.source_pricing_id for r in _match(db, _rx(db, 0.0))[0]} == {a.id, b.id}


def test_dd_stock_rx_suppression_unchanged(db):
    _co, _m, cat, v, ct = _dd_base(db)
    st = _pricing(db, v, cat, availability="stock", price="700.00", coating=ct, power_scope="st")
    _range(db, st, v, sph_min=-6.0, sph_max=6.0)
    rxp = _pricing(db, v, cat, availability="rx", price="700.00", coating=ct, power_scope="rx")
    _range(db, rxp, v, sph_min=-6.0, sph_max=6.0)
    res = _match(db, _rx(db, 0.0))[0]
    assert len(res) == 1 and res[0].source_pricing_id == st.id     # RX suppressed by STOCK, unchanged
    _co2, _m2, cat2, v2, ct2 = _dd_base(db)
    only_rx = _pricing(db, v2, cat2, availability="rx", price="900.00", coating=ct2, power_scope="rx")
    _range(db, only_rx, v2, sph_min=-6.0, sph_max=6.0)
    assert any(r.source_pricing_id == only_rx.id and r.availability == "rx"
               for r in _match(db, _rx(db, 0.0))[0])


def test_dd_highest_score_survives(db):
    _co, _m, cat, v, ct = _dd_base(db)
    tight = _pricing(db, v, cat, price="700.00", coating=ct, power_scope="tight")
    _range(db, tight, v, sph_min=2.0, sph_max=4.0)            # centre 3 == Rx
    wide = _pricing(db, v, cat, price="700.00", coating=ct, power_scope="wide")
    _range(db, wide, v, sph_min=-10.0, sph_max=10.0)
    res = _match(db, _rx(db, 3.0))[0]
    assert len(res) == 1 and res[0].source_pricing_id == tight.id


def test_dd_tie_prefers_range_bearing(db):
    # RX no-range power_score == 18.0 ; a range with avg_dist == 0.4*(span/2)
    # also scores 18.0 -> exact tie -> range-bearing wins despite HIGHER id.
    _co, _m, cat, v, ct = _dd_base(db)
    _no_range = _pricing(db, v, cat, availability="rx", price="700.00", coating=ct, power_scope="nr")
    with_range = _pricing(db, v, cat, availability="rx", price="700.00", coating=ct, power_scope="wr")
    _range(db, with_range, v, sph_min=-5.0, sph_max=5.0)     # centre 0, span 10
    res = _match(db, _rx(db, 2.0))[0]                        # avg_dist 2 == 0.4*5
    assert len(res) == 1
    assert res[0].source_pricing_id == with_range.id
    assert res[0].power_range is not None


def test_dd_pricing_id_final_tiebreak_deterministic(db):
    _co, _m, cat, v, ct = _dd_base(db)
    a = _pricing(db, v, cat, availability="rx", price="700.00", coating=ct, power_scope="a")
    b = _pricing(db, v, cat, availability="rx", price="700.00", coating=ct, power_scope="b")
    r1 = _match(db, _rx(db, 0.0))[0]
    r2 = _match(db, _rx(db, 0.0))[0]
    assert len(r1) == 1 and r1[0].source_pricing_id == min(a.id, b.id)
    assert [x.source_pricing_id for x in r1] == [x.source_pricing_id for x in r2]


def test_dd_sorting_unchanged(db):
    _co, _m, cat, v, ct = _dd_base(db)
    cheap = _pricing(db, v, cat, price="500.00", coating=ct, power_scope="c")
    _range(db, cheap, v, sph_min=-6.0, sph_max=6.0)
    pricey = _pricing(db, v, cat, price="900.00", coating=ct, power_scope="p")
    _range(db, pricey, v, sph_min=-6.0, sph_max=6.0)
    res = _match(db, _rx(db, 0.0))[0]
    assert [r.source_pricing_id for r in res] == [cheap.id, pricey.id]   # equal score -> cheaper first
