"""Permanent regression coverage for the BBGR (French) canonical import.

Deliberately synthetic, mirroring the corrected shape directly via the ORM
(no PDF parsing, no dependency on the live optical_lens.db), matching the
same pattern as test_maxxee_import.py / test_seiko_import.py.

This catalog is the first import to exercise the NEW permanent RX
manufacturing-eligibility domain rule end to end on a real manufacturer: a
manufacturing (RX) lens is made to order and is NOT dependent on a printed
PowerRange by default - EVERY BBGR RX row (127 of 134 total) has zero
PowerRange and is proven eligible purely by that rule, never by a
power_eligibility flag and never by a fabricated range. BBGR's 7 STOCK rows
also print no market (Egypt vs Out Of Egypt) and no Stock PowerRange at all
- market_scope stays NULL (the generic stock_market_unknown representation),
and stock compatibility is never claimed proven for any specific
prescription.
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


def _mk_coating(db, code):
    c = models.Coating(code=code, name=code)
    db.add(c); db.commit(); db.refresh(c)
    return c


def _mk_variant(db, model, index_value, material=models.MaterialType.CR39, design_variant=None,
                treatment_band=None, design_tier=None):
    v = models.LensVariant(
        lens_model_id=model.id, material=material, index_value=index_value,
        design_type=models.DesignType.SPHERICAL, is_aspherical=False,
        design_variant=design_variant, treatment_band=treatment_band, design_tier=design_tier,
        price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    return v


def _mk_pricing(db, variant, catalog, *, availability, price, coating=None, market_scope=None):
    vp = models.VariantPricing(
        variant_id=variant.id, coating_id=(coating.id if coating else None),
        availability=availability, price_pair=Decimal(str(price)), currency="EGP",
        source_catalog_id=catalog.id, market_scope=market_scope)
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
def bbgr_setup(db):
    co = _mk_company(db, "BBGR")
    cat = _mk_catalog(db, co)
    sv = _mk_model(db, co, "BBGR", models.LensCategory.SINGLE_VISION)
    prog = _mk_model(db, co, "BBGR", models.LensCategory.PROGRESSIVE)
    bifocal = _mk_model(db, co, "BBGR", models.LensCategory.BIFOCAL)
    diams = _mk_coating(db, "Diam's")

    # --- Page 2A: STOCK, no market stated, no Stock PowerRange ---
    v_156_diams = _mk_variant(db, sv, 1.56)
    p_stock = _mk_pricing(db, v_156_diams, cat, availability=models.PricingAvailability.STOCK,
                          price=1050, coating=diams, market_scope=None)

    # --- Page 2B: RX S.V. - plain 1.59 / 1.59 Polarized / 1.59 TR7 (identity safety) ---
    v_159 = _mk_variant(db, sv, 1.59)
    p_159 = _mk_pricing(db, v_159, cat, availability=models.PricingAvailability.RX, price=2250)
    v_159_pol = _mk_variant(db, sv, 1.59, treatment_band="Polarized")
    p_159_pol = _mk_pricing(db, v_159_pol, cat, availability=models.PricingAvailability.RX, price=4500)
    v_159_tr7 = _mk_variant(db, sv, 1.59, treatment_band="TR7")
    p_159_tr7 = _mk_pricing(db, v_159_tr7, cat, availability=models.PricingAvailability.RX, price=6200)

    # 1.50 (75) / (80) diameter-like identity dimensions
    v_150_75 = _mk_variant(db, sv, 1.50, design_tier="75")
    p_150_75 = _mk_pricing(db, v_150_75, cat, availability=models.PricingAvailability.RX, price=1800)
    v_150_80 = _mk_variant(db, sv, 1.50, design_tier="80")
    p_150_80 = _mk_pricing(db, v_150_80, cat, availability=models.PricingAvailability.RX, price=1900)

    # --- Page 3: Aspheo vs plain RX S.V. at the SAME index - never collapsed ---
    v_aspheo_159 = _mk_variant(db, sv, 1.59, design_variant="Aspheo")
    p_aspheo_159 = _mk_pricing(db, v_aspheo_159, cat, availability=models.PricingAvailability.RX, price=3350)

    # Anti-Fatigue / Extenso - single_vision, never progressive
    v_af_150 = _mk_variant(db, sv, 1.50, design_variant="Anti-Fatigue")
    p_af_150 = _mk_pricing(db, v_af_150, cat, availability=models.PricingAvailability.RX, price=2600)
    v_ext_150 = _mk_variant(db, sv, 1.50, design_variant="Extenso")
    p_ext_150 = _mk_pricing(db, v_ext_150, cat, availability=models.PricingAvailability.RX, price=2700)

    # --- Page 4: Quadro (progressive), Digital BI FOCAL / Bi-Focal (bifocal) ---
    v_quadro_150 = _mk_variant(db, prog, 1.50, design_variant="Quadro")
    p_quadro_150 = _mk_pricing(db, v_quadro_150, cat, availability=models.PricingAvailability.RX, price=2600)
    v_dbf_150 = _mk_variant(db, bifocal, 1.50, design_variant="Digital BI FOCAL")
    p_dbf_150 = _mk_pricing(db, v_dbf_150, cat, availability=models.PricingAvailability.RX, price=2800)
    v_bf_150 = _mk_variant(db, bifocal, 1.50, design_variant="Bi-Focal")
    p_bf_150 = _mk_pricing(db, v_bf_150, cat, availability=models.PricingAvailability.RX, price=1750)

    # --- Page 5: Sirus+ / Yeso (progressive) ---
    v_sirus_150 = _mk_variant(db, prog, 1.50, design_variant="Sirus+")
    p_sirus_150 = _mk_pricing(db, v_sirus_150, cat, availability=models.PricingAvailability.RX, price=3950)
    v_yeso_150 = _mk_variant(db, prog, 1.50, design_variant="Yeso")
    p_yeso_150 = _mk_pricing(db, v_yeso_150, cat, availability=models.PricingAvailability.RX, price=8950)

    return {"company": co, "sv": sv, "prog": prog, "bifocal": bifocal,
            "v_156_diams": v_156_diams, "p_stock": p_stock,
            "v_159": v_159, "v_159_pol": v_159_pol, "v_159_tr7": v_159_tr7,
            "v_150_75": v_150_75, "v_150_80": v_150_80,
            "v_aspheo_159": v_aspheo_159, "p_aspheo_159": p_aspheo_159,
            "v_af_150": v_af_150, "v_ext_150": v_ext_150,
            "v_quadro_150": v_quadro_150, "v_dbf_150": v_dbf_150, "v_bf_150": v_bf_150,
            "v_sirus_150": v_sirus_150, "v_yeso_150": v_yeso_150}


# 1. RX + zero PowerRange -> Manufacturing eligible, no range fabricated.
def test_1_bbgr_rx_no_range_eligible(db, bbgr_setup):
    sv = bbgr_setup["sv"]
    for sph in (-2.0, -20.0, 8.0):
        presc = _mk_presc(db, sph, name=f"t1-{sph}")
        resp = _targeted(db, presc, lens_model_id=sv.id, index_value=1.59,
                         design_variant=None, treatment_band=None)
        assert resp.best_match.pair_fulfillment.status == "rx", sph
        assert resp.best_match.pair_fulfillment.price_pair == Decimal("2250.00"), sph


# 2. BBGR RX row returns its printed pair price without requiring a StockRange.
def test_2_bbgr_rx_row_returns_printed_price(db, bbgr_setup):
    v = bbgr_setup["v_159_tr7"]
    assert list(v.power_ranges) == []
    presc = _mk_presc(db, -2.0, name="t2")
    resp = _targeted(db, presc, lens_model_id=bbgr_setup["sv"].id, index_value=1.59, treatment_band="TR7")
    assert resp.best_match.pair_fulfillment.status == "rx"
    assert resp.best_match.pair_fulfillment.price_pair == Decimal("6200.00")


# 3. Stock + zero PowerRange is not claimed prescription-proven.
def test_3_bbgr_stock_no_range_not_proven(db, bbgr_setup):
    p = bbgr_setup["p_stock"]
    assert list(p.power_ranges) == []
    presc = _mk_presc(db, -2.0, -1.0, name="t3")
    status = product_search._row_eye_status(p, presc, "od")
    assert status == "ineligible"


# 9. BBGR Stock row can display price/catalog product but does not falsely
# claim prescription stock compatibility.
def test_9_bbgr_stock_row_discoverable_not_falsely_proven(db, bbgr_setup):
    sv = bbgr_setup["sv"]
    presc = _mk_presc(db, -2.0, -1.0, name="t9")
    resp = _targeted(db, presc, lens_model_id=sv.id, index_value=1.56, coating="Diam's")
    assert resp.exact_total > 0   # discoverable
    found = [r for g in resp.groups for r in g.results if r.coating_code == "Diam's"]
    assert found
    r = found[0]
    assert r.pair_fulfillment.status != "stock_egypt"
    assert r.pair_fulfillment.status != "stock_out_of_egypt"
    assert r.pair_fulfillment.price_pair is None   # never a falsely-proven pair price
    # the row's OWN catalog price is intact in the DB, never lost or zeroed
    p = db.query(models.VariantPricing).filter(
        models.VariantPricing.variant_id == bbgr_setup["v_156_diams"].id).first()
    assert p.price_pair == Decimal("1050.00")


# BBGR stock market representation: NULL market_scope, never Egypt/Out Of Egypt.
def test_bbgr_stock_market_unknown_never_egypt_or_ooe(db, bbgr_setup):
    p = bbgr_setup["p_stock"]
    assert p.market_scope is None
    presc = _mk_presc(db, -2.0, -1.0, name="market")
    resp = _targeted(db, presc, lens_model_id=bbgr_setup["sv"].id, index_value=1.56, coating="Diam's")
    assert resp.availability_answer.code not in ("stock_egypt", "stock_out_of_egypt")


# 6/L. Identity safety: 1.59 / 1.59 Polarized / 1.59 TR7 are three distinct
# commercial identities, never collapsed, each with its own printed price.
def test_L_identity_safety_1_59_variants_distinct(db, bbgr_setup):
    v1, v2, v3 = bbgr_setup["v_159"], bbgr_setup["v_159_pol"], bbgr_setup["v_159_tr7"]
    assert len({v1.id, v2.id, v3.id}) == 3
    prices = {}
    for v, expected in ((v1, "2250.00"), (v2, "4500.00"), (v3, "6200.00")):
        p = db.query(models.VariantPricing).filter(models.VariantPricing.variant_id == v.id).first()
        assert p.price_pair == Decimal(expected)


# Diameter-like 1.50 (75) / (80) distinctions remain identity-driving.
def test_diameter_like_1_50_variants_distinct(db, bbgr_setup):
    v75, v80 = bbgr_setup["v_150_75"], bbgr_setup["v_150_80"]
    assert v75.id != v80.id
    p75 = db.query(models.VariantPricing).filter(models.VariantPricing.variant_id == v75.id).first()
    p80 = db.query(models.VariantPricing).filter(models.VariantPricing.variant_id == v80.id).first()
    assert p75.price_pair == Decimal("1800.00")
    assert p80.price_pair == Decimal("1900.00")


# Aspheo (design_variant) vs plain RX S.V. at the SAME index never collapse
# into one commercial identity, even though both are single_vision/RX/1.59.
def test_aspheo_vs_plain_rx_sv_never_collapse(db, bbgr_setup):
    plain, aspheo = bbgr_setup["v_159"], bbgr_setup["v_aspheo_159"]
    assert plain.id != aspheo.id
    p_plain = db.query(models.VariantPricing).filter(models.VariantPricing.variant_id == plain.id).first()
    p_aspheo = db.query(models.VariantPricing).filter(models.VariantPricing.variant_id == aspheo.id).first()
    assert p_plain.price_pair == Decimal("2250.00")
    assert p_aspheo.price_pair == Decimal("3350.00")


# 8. Bifocal and Progressive stay RX (permanent project rule).
def test_8_bifocal_and_progressive_stay_rx(db, bbgr_setup):
    for key in ("v_quadro_150", "v_sirus_150", "v_yeso_150", "v_dbf_150", "v_bf_150"):
        v = bbgr_setup[key]
        p = db.query(models.VariantPricing).filter(models.VariantPricing.variant_id == v.id).first()
        assert p.availability == models.PricingAvailability.RX, key


# Anti-Fatigue / Extenso stay single_vision, never progressive.
def test_anti_fatigue_extenso_stay_single_vision(db, bbgr_setup):
    for key in ("v_af_150", "v_ext_150"):
        v = bbgr_setup[key]
        assert v.lens_model.category == models.LensCategory.SINGLE_VISION, key


# Company/category boundary.
def test_company_category_boundary(db, bbgr_setup):
    co = bbgr_setup["company"]
    hoya = _mk_company(db, "HOYA")
    hoya_cat = _mk_catalog(db, hoya)
    hoya_model = _mk_model(db, hoya, "HOYA", models.LensCategory.SINGLE_VISION)
    v_hoya = _mk_variant(db, hoya_model, 1.50)
    _mk_pricing(db, v_hoya, hoya_cat, availability=models.PricingAvailability.RX, price=500)

    presc = _mk_presc(db, -2.0, name="boundary")
    f = schemas.LensFilters(company_id=co.id, index_value=1.50)
    req = schemas.ProductSearchRequest(mode="targeted", filters=f, include_alternatives=True)
    resp = product_search.search(db, presc, req)
    for grp in resp.groups:
        for r in grp.results:
            assert r.company_id == co.id


# 10. PIXEL's separately-unresolved "Hi Power" surcharge issue is untouched
# by this rule: this change only affects _row_eye_status (eligibility), it
# never reads or writes VariantPricing.price_pair, never attaches a
# PowerRange, and never composes/derives a price from add-on evidence.
def test_10_rule_never_touches_price_or_surcharge_composition(db, bbgr_setup):
    v = bbgr_setup["v_159_tr7"]
    p = db.query(models.VariantPricing).filter(models.VariantPricing.variant_id == v.id).first()
    price_before = p.price_pair
    presc = _mk_presc(db, -2.0, -1.0, name="t10")
    product_search._row_eye_status(p, presc, "od")   # exercise the eligibility path
    db.refresh(p)
    assert p.price_pair == price_before   # untouched
    assert list(p.power_ranges) == []     # nothing fabricated
