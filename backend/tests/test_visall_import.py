"""Permanent regression coverage for the VISALL (BRILLENGLAS) one-page stock
catalog import.

Deliberately synthetic, mirroring the corrected shape directly via the ORM
(no PDF parsing, no dependency on the live optical_lens.db), matching the
same pattern as test_divel_import.py / test_maxxee_import.py.

Two commercial market sections under one company (Stock in Egypt / Stock Out
Of Egypt), both STOCK, both Single Vision, RX=0. Unlike DIVEL/BBGR, every
VISALL row prints its own SPH/CYL band, so every pricing row here gets a
PowerRange (one-to-one) - there are no rangeless rows in this catalog.

The catalog prints two price columns (Lap Price / Shop Price). Only Shop
Price is ever used as VariantPricing.price_pair; Lap Price is recorded only
as internal catalog evidence in PowerRange.notes (the only already-existing
evidence field attached to every one of these rows), never exposed as a
customer-facing price and never given new schema.

Known, intentional deviation from a literal cell-by-cell transcription:
"1.56 Photo Gray & Brown" prints the (Shop 1300 EGP / SPH +0.25 to +6.00 /
CYL 0.00 to -2.00) band TWICE, byte-for-byte identical - a source printing
artifact, not two distinct commercial bands. Storing both would collide on
the project's existing `uq_variant_pricing_current` unique index (same
variant_id, coating_id, availability, power_scope, market_scope). Per
explicit user decision, the duplicate is collapsed to ONE stored row rather
than fabricated into two synthetic color-variant identities - so this
product yields 2 pricing rows (not 3), and the Egypt total is 22 (not 23).
Every other product in the catalog transcribes exactly as printed with no
collapsing.

"85%" on the two Sun rows is tint/color density, never diameter - and unlike
DIVEL's Sun/Mirror/Polar rows, VISALL's Sun rows DO print SPH/CYL, so their
stock prescription eligibility is fully governed by those printed ranges,
same as any other STOCK row.
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


def _mk_model(db, company, name, category=models.LensCategory.SINGLE_VISION):
    m = models.LensModel(company_id=company.id, name=name, category=category)
    db.add(m); db.commit(); db.refresh(m)
    return m


def _mk_variant(db, model, index_value, color_variant=None):
    v = models.LensVariant(
        lens_model_id=model.id, material=models.MaterialType.CR39, index_value=index_value,
        design_type=models.DesignType.SPHERICAL, is_aspherical=False,
        color_variant=color_variant, price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    return v


def _mk_pricing(db, variant, catalog, *, price, market_scope, sph_min, sph_max, cyl_min, cyl_max):
    power_scope = crud.build_power_scope(sph_min=sph_min, sph_max=sph_max, cyl_min=cyl_min, cyl_max=cyl_max)
    vp = models.VariantPricing(
        variant_id=variant.id, availability=models.PricingAvailability.STOCK,
        price_pair=Decimal(str(price)), currency="EGP", source_catalog_id=catalog.id,
        market_scope=market_scope, power_scope=power_scope)
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


def _targeted(db, presc, model):
    f = schemas.LensFilters(lens_model_id=model.id)
    req = schemas.ProductSearchRequest(mode="targeted", filters=f)
    return product_search.search(db, presc, req)


EGYPT = "Egypt"
OOE = "Out Of Egypt"


@pytest.fixture()
def visall_setup(db):
    co = _mk_company(db, "VISALL")
    cat = _mk_catalog(db, co)

    def row(model, variant, price, market, sph_min, sph_max, cyl_min, cyl_max, lap=None, tint=None):
        vp = _mk_pricing(db, variant, cat, price=price, market_scope=market,
                         sph_min=sph_min, sph_max=sph_max, cyl_min=cyl_min, cyl_max=cyl_max)
        note = f"Lap Price: {lap} EGP" if lap is not None else None
        if tint:
            note = f"{note} | Tint density: {tint}" if note else f"Tint density: {tint}"
        _mk_range(db, model, variant, vp, sph_min, sph_max, cyl_min, cyl_max, notes=note)
        return vp

    m_holt15 = _mk_model(db, co, "1.5 HOLT")
    v_holt15 = _mk_variant(db, m_holt15, 1.5)
    v_holt15.treatment_band = "HOLT"; db.commit()
    p_holt15_a = row(m_holt15, v_holt15, 850, EGYPT, -4.0, 0.0, -2.0, 0.0, lap=400)
    row(m_holt15, v_holt15, 850, EGYPT, 0.25, 4.0, -2.0, 0.0, lap=400)
    row(m_holt15, v_holt15, 1100, EGYPT, -3.75, -2.25, -3.0, -2.25, lap=500)
    row(m_holt15, v_holt15, 1100, EGYPT, 0.25, 4.0, -3.0, -2.25, lap=500)

    # Plain BlueCut coating, no photochromic/color claim - distinct from the
    # photochromic BlueCut combinations below (Gray BlueCut, Adapta BC B&G).
    m_bluecut15 = _mk_model(db, co, "1.5 BlueCut")
    v_bluecut15 = _mk_variant(db, m_bluecut15, 1.5)
    v_bluecut15.treatment_band = "BlueCut"; db.commit()
    row(m_bluecut15, v_bluecut15, 1300, EGYPT, -4.0, 0.0, -2.0, 0.0, lap=600)
    row(m_bluecut15, v_bluecut15, 1300, EGYPT, 0.25, 4.0, -2.0, 0.0, lap=600)

    m_bluecut16 = _mk_model(db, co, "1.6 BlueCut")
    v_bluecut16 = _mk_variant(db, m_bluecut16, 1.6)
    v_bluecut16.treatment_band = "BlueCut"; db.commit()
    row(m_bluecut16, v_bluecut16, 1800, EGYPT, -8.0, 0.0, 0.0, 0.0, lap=850)
    row(m_bluecut16, v_bluecut16, 1800, EGYPT, -6.0, 0.0, -2.0, 0.0, lap=850)
    row(m_bluecut16, v_bluecut16, 2100, EGYPT, -6.0, 0.0, -4.0, -2.25, lap=1000)
    row(m_bluecut16, v_bluecut16, 1800, EGYPT, 0.25, 6.0, -2.0, 0.0, lap=1000)

    # "BC" = BlueCut (never Base Curve); "B&G" = photochromic Gray + Brown;
    # "Adapta" = product family. All four axes represented via the three
    # existing generic LensVariant text fields.
    m_adapta = _mk_model(db, co, "1.6 Adapta BC B&G")
    v_adapta = _mk_variant(db, m_adapta, 1.6, color_variant="Gray / Brown")
    v_adapta.design_variant = "Adapta"; v_adapta.treatment_band = "Photochromic + BlueCut"; db.commit()
    row(m_adapta, v_adapta, 6000, OOE, -6.0, 0.0, -2.0, 0.0, lap=3000)
    row(m_adapta, v_adapta, 6000, OOE, 0.25, 6.0, -2.0, 0.0, lap=3000)

    m_bluecut167 = _mk_model(db, co, "1.67 BlueCut")
    v_bluecut167 = _mk_variant(db, m_bluecut167, 1.67)
    v_bluecut167.treatment_band = "BlueCut"; db.commit()
    row(m_bluecut167, v_bluecut167, 3000, OOE, -10.0, -2.0, -2.0, 0.0, lap=1500)
    row(m_bluecut167, v_bluecut167, 3000, OOE, 0.25, 6.0, -2.0, 0.0, lap=1500)

    # Photochromic Gray + BlueCut together - distinct from plain BlueCut,
    # plain Photo Gray, and Adapta BC B&G.
    m_graybc = _mk_model(db, co, "1.56 Gray BlueCut")
    v_graybc = _mk_variant(db, m_graybc, 1.56, color_variant="Gray")
    v_graybc.treatment_band = "Photochromic + BlueCut"; db.commit()
    row(m_graybc, v_graybc, 2000, OOE, -6.0, 0.0, -2.0, 0.0, lap=1000)
    row(m_graybc, v_graybc, 2000, OOE, 0.25, 6.0, -2.0, 0.0, lap=1000)

    # "Tr" = Transition (photochromic brand), "B&G" = Gray + Brown colors.
    m_tr15 = _mk_model(db, co, "1.5 Tr B&G")
    v_tr15 = _mk_variant(db, m_tr15, 1.5, color_variant="Gray / Brown")
    v_tr15.design_variant = "Transition"; v_tr15.treatment_band = "Photochromic"; db.commit()
    row(m_tr15, v_tr15, 10000, OOE, -4.0, 0.0, -2.0, 0.0, lap=5000)
    row(m_tr15, v_tr15, 10000, OOE, 0.25, 4.0, -2.0, 0.0, lap=5000)

    m_tr16 = _mk_model(db, co, "1.6 Tr B&G")
    v_tr16 = _mk_variant(db, m_tr16, 1.6, color_variant="Gray / Brown")
    v_tr16.design_variant = "Transition"; v_tr16.treatment_band = "Photochromic"; db.commit()
    row(m_tr16, v_tr16, 13000, OOE, -6.0, 0.0, -2.0, 0.0, lap=6500)
    row(m_tr16, v_tr16, 13000, OOE, 0.25, 4.0, -2.0, 0.0, lap=6500)

    # Same Type "1.6 HOLT", THREE rows share price 1400/1700 but each with a
    # DIFFERENT printed SPH/CYL band - must remain 5 distinct rows (test 12).
    m_holt16 = _mk_model(db, co, "1.6 HOLT")
    v_holt16 = _mk_variant(db, m_holt16, 1.6)
    v_holt16.treatment_band = "HOLT"; db.commit()
    row(m_holt16, v_holt16, 1400, EGYPT, -6.0, -3.0, -2.0, 0.0, lap=650)
    row(m_holt16, v_holt16, 1700, EGYPT, -6.0, -3.0, -3.0, -2.25, lap=650)
    row(m_holt16, v_holt16, 1700, EGYPT, -5.0, -3.0, -3.25, -3.0, lap=650)
    row(m_holt16, v_holt16, 1400, EGYPT, 3.0, 6.0, 0.0, 0.0, lap=800)
    row(m_holt16, v_holt16, 1400, EGYPT, 4.25, 6.0, -2.0, 0.0, lap=800)

    # 1.56 Photo Gray & Brown vs 1.56 Photo Gray - must stay distinct products
    # (test 13). Duplicate band collapsed to 2 rows (see module docstring).
    # Domain rule: "Gray & Brown" = one photochromic product available in two
    # colors, not two priced identities - color_variant carries both colors as
    # one evidence string, treatment_band records the shared photochromic
    # technology. Never split into per-color pricing.
    m_pgb = _mk_model(db, co, "1.56 Photo Gray & Brown")
    v_pgb = _mk_variant(db, m_pgb, 1.56, color_variant="Gray / Brown")
    v_pgb.treatment_band = "Photochromic"; db.commit()
    row(m_pgb, v_pgb, 1300, EGYPT, -6.0, 0.0, -2.0, 0.0, lap=600)
    row(m_pgb, v_pgb, 1300, EGYPT, 0.25, 6.0, -2.0, 0.0, lap=600)

    # Gray-only photochromic sibling - stays a distinct product from the
    # Gray & Brown one above (fewer color options, not a merge candidate).
    m_pg = _mk_model(db, co, "1.56 Photo Gray")
    v_pg = _mk_variant(db, m_pg, 1.56, color_variant="Gray")
    v_pg.treatment_band = "Photochromic"; db.commit()
    row(m_pg, v_pg, 1500, EGYPT, -3.75, 0.0, -4.0, -2.25, lap=700)
    row(m_pg, v_pg, 1500, EGYPT, 0.25, 1.25, -4.0, -2.25, lap=700)

    # 1.67 HOLT (Egypt) vs 1.67 HLOT (Out Of Egypt) vs 1.74 HLOT - printed
    # spelling must never be silently normalized either direction (test 14).
    m_holt167 = _mk_model(db, co, "1.67 HOLT")
    v_holt167 = _mk_variant(db, m_holt167, 1.67)
    v_holt167.treatment_band = "HOLT"; db.commit()
    row(m_holt167, v_holt167, 2100, EGYPT, -10.0, -5.0, -2.0, 0.0, lap=1000)
    row(m_holt167, v_holt167, 2500, EGYPT, -5.0, -5.0, -4.0, -2.25, lap=1200)
    row(m_holt167, v_holt167, 2500, EGYPT, -7.0, -5.25, -4.0, -2.25, lap=1200)

    # Source prints "HLOT" here - the MODEL NAME stays exactly as printed
    # (never renamed), while treatment_band canonicalizes to "HOLT" (the
    # same coating system, per domain-expert confirmation: HOLT == HLOT).
    m_hlot167 = _mk_model(db, co, "1.67 HLOT")
    v_hlot167 = _mk_variant(db, m_hlot167, 1.67)
    v_hlot167.treatment_band = "HOLT"; db.commit()
    row(m_hlot167, v_hlot167, 2100, OOE, 2.0, 6.0, -2.0, 0.0, lap=1050)
    row(m_hlot167, v_hlot167, 2100, OOE, -4.75, 0.0, -2.0, 0.0, lap=1050)
    row(m_hlot167, v_hlot167, 2500, OOE, -4.75, 0.0, -4.0, -2.25, lap=1250)

    m_hlot174 = _mk_model(db, co, "1.74 HLOT")
    v_hlot174 = _mk_variant(db, m_hlot174, 1.74)
    v_hlot174.treatment_band = "HOLT"; db.commit()
    row(m_hlot174, v_hlot174, 7000, OOE, -10.0, -1.0, -2.0, 0.0, lap=3500)
    row(m_hlot174, v_hlot174, 8000, OOE, -10.0, -4.0, -3.0, -2.25, lap=4000)

    # Sun 85% - tint density evidence only, printed SPH/CYL still governs
    # stock eligibility (test 15).
    m_sun15 = _mk_model(db, co, "1.5 Sun 85%")
    v_sun15 = _mk_variant(db, m_sun15, 1.5)
    p_sun_minus = row(m_sun15, v_sun15, 2400, OOE, -6.0, 0.0, -2.0, 0.0, lap=1200, tint="85%")
    row(m_sun15, v_sun15, 2400, OOE, 0.25, 6.0, -2.0, 0.0, lap=1200, tint="85%")
    row(m_sun15, v_sun15, 2800, OOE, -4.0, 0.0, -3.0, -2.25, lap=1400, tint="85%")
    row(m_sun15, v_sun15, 2800, OOE, 0.25, 4.0, -3.0, -2.25, lap=1400, tint="85%")

    m_sun16 = _mk_model(db, co, "1.6 Sun 85%")
    v_sun16 = _mk_variant(db, m_sun16, 1.6)
    row(m_sun16, v_sun16, 4000, OOE, -6.0, 0.0, -2.0, 0.0, lap=2000, tint="85%")
    row(m_sun16, v_sun16, 4000, OOE, -8.0, -6.25, -1.0, 0.0, lap=2000, tint="85%")

    return {
        "company": co, "catalog": cat,
        "m_holt15": m_holt15, "v_holt15": v_holt15, "p_holt15_a": p_holt15_a,
        "m_holt16": m_holt16, "v_holt16": v_holt16,
        "m_pgb": m_pgb, "v_pgb": v_pgb, "m_pg": m_pg, "v_pg": v_pg,
        "m_holt167": m_holt167, "v_holt167": v_holt167,
        "m_hlot167": m_hlot167, "v_hlot167": v_hlot167,
        "m_hlot174": m_hlot174, "v_hlot174": v_hlot174,
        "m_sun15": m_sun15, "v_sun15": v_sun15, "p_sun_minus": p_sun_minus,
        "m_bluecut15": m_bluecut15, "v_bluecut15": v_bluecut15,
        "m_bluecut16": m_bluecut16, "v_bluecut16": v_bluecut16,
        "m_bluecut167": m_bluecut167, "v_bluecut167": v_bluecut167,
        "m_adapta": m_adapta, "v_adapta": v_adapta,
        "m_graybc": m_graybc, "v_graybc": v_graybc,
        "m_tr15": m_tr15, "v_tr15": v_tr15, "m_tr16": m_tr16, "v_tr16": v_tr16,
    }


def _all_vp(db, co):
    return (db.query(models.VariantPricing)
              .join(models.LensVariant).join(models.LensModel)
              .filter(models.LensModel.company_id == co.id).all())


def _all_pr(db, co):
    return (db.query(models.PowerRange)
              .join(models.LensVariant).join(models.LensModel)
              .filter(models.LensModel.company_id == co.id).all())


# 1. VISALL is an independent company.
def test_01_independent_company(db, visall_setup):
    co = visall_setup["company"]
    other = _mk_company(db, "SomeOtherCo")
    assert co.id != other.id
    assert co.name == "VISALL"


# 2. VariantPricing total = 43 (44 literally printed minus the one collapsed
# duplicate - see module docstring).
def test_02_variant_pricing_total(db, visall_setup):
    co = visall_setup["company"]
    assert len(_all_vp(db, co)) == 43


# 3. Stock count = 43 (all rows).
def test_03_stock_count(db, visall_setup):
    co = visall_setup["company"]
    rows = _all_vp(db, co)
    assert all(v.availability == models.PricingAvailability.STOCK for v in rows)
    assert len(rows) == 43


# 4. Egypt count = 22.
def test_04_egypt_count(db, visall_setup):
    co = visall_setup["company"]
    assert sum(1 for v in _all_vp(db, co) if v.market_scope == EGYPT) == 22


# 5. Out Of Egypt count = 21.
def test_05_ooe_count(db, visall_setup):
    co = visall_setup["company"]
    assert sum(1 for v in _all_vp(db, co) if v.market_scope == OOE) == 21


# 6. RX count = 0.
def test_06_rx_count(db, visall_setup):
    co = visall_setup["company"]
    assert sum(1 for v in _all_vp(db, co) if v.availability == models.PricingAvailability.RX) == 0


# 7. Single Vision count = 43 (every VariantPricing row belongs to a
# single_vision LensModel - there is no other category in this catalog).
def test_07_single_vision_count(db, visall_setup):
    co = visall_setup["company"]
    models_ = db.query(models.LensModel).filter(models.LensModel.company_id == co.id).all()
    assert all(m.category == models.LensCategory.SINGLE_VISION for m in models_)
    assert len(_all_vp(db, co)) == 43


# 8/9. Shop Price used as price_pair; Lap Price NEVER used as customer price.
def test_08_09_shop_price_used_lap_price_not(db, visall_setup):
    p = visall_setup["p_holt15_a"]
    assert p.price_pair == Decimal("850.00")   # printed Shop Price
    assert p.price_pair != Decimal("400.00")   # printed Lap Price never substituted
    pr = db.query(models.PowerRange).filter(models.PowerRange.pricing_id == p.id).first()
    assert "Lap Price: 400" in pr.notes        # Lap Price preserved as evidence only


# 10/11. Every pricing band retains its own printed SPH/CYL evidence;
# PowerRange coverage is one-to-one with pricing (43 == 43).
def test_10_11_one_to_one_range_coverage(db, visall_setup):
    co = visall_setup["company"]
    vp_ids = {v.id for v in _all_vp(db, co)}
    pr_pricing_ids = [pr.pricing_id for pr in _all_pr(db, co)]
    assert len(pr_pricing_ids) == 43
    assert set(pr_pricing_ids) == vp_ids
    assert len(pr_pricing_ids) == len(set(pr_pricing_ids))   # truly one-to-one, no doubling


# 12. Equal-price rows with different power ranges remain distinct (1.6 HOLT:
# three rows share prices 1400/1700 but each has its own printed band).
def test_12_equal_price_different_range_stays_distinct(db, visall_setup):
    v = visall_setup["v_holt16"]
    rows = db.query(models.VariantPricing).filter(models.VariantPricing.variant_id == v.id).all()
    assert len(rows) == 5
    scopes = [r.power_scope for r in rows]
    assert len(scopes) == len(set(scopes))   # every band has its own distinct power_scope


# 13. Photo Gray & Brown remains distinct from Photo Gray.
def test_13_photo_gray_brown_distinct_from_photo_gray(db, visall_setup):
    assert visall_setup["m_pgb"].id != visall_setup["m_pg"].id
    assert visall_setup["m_pgb"].name == "1.56 Photo Gray & Brown"
    assert visall_setup["m_pg"].name == "1.56 Photo Gray"
    assert visall_setup["v_pgb"].color_variant == "Gray / Brown"


# 14. HOLT/HLOT source naming preserved (no silent normalization either way).
def test_14_holt_hlot_naming_preserved(db, visall_setup):
    assert visall_setup["m_holt167"].name == "1.67 HOLT"
    assert visall_setup["m_hlot167"].name == "1.67 HLOT"
    assert visall_setup["m_hlot174"].name == "1.74 HLOT"
    names = {visall_setup["m_holt167"].name, visall_setup["m_hlot167"].name, visall_setup["m_hlot174"].name}
    assert names == {"1.67 HOLT", "1.67 HLOT", "1.74 HLOT"}   # all three preserved distinctly


# 15. Sun 85%: tint density evidence, never diameter; printed SPH/CYL still
# controls stock eligibility.
def test_15_sun_85_tint_not_diameter_range_still_controls(db, visall_setup):
    v = visall_setup["v_sun15"]
    assert v.diameter is None                     # never fabricated as diameter
    pr = db.query(models.PowerRange).filter(models.PowerRange.pricing_id == visall_setup["p_sun_minus"].id).first()
    assert "Tint density: 85%" in pr.notes
    assert "diameter" not in pr.notes.lower()
    # Inside the printed minus band (0 to -6 / 0 to -2) -> eligible.
    in_status = product_search._row_eye_status(visall_setup["p_sun_minus"], _mk_presc(db, -3.0, -1.0, "sun-in"), "od")
    assert in_status == "eligible"
    # Outside every printed Sun 85% band -> ineligible (never fabricated as unrestricted).
    out_status = product_search._row_eye_status(visall_setup["p_sun_minus"], _mk_presc(db, -9.0, -1.0, "sun-out"), "od")
    assert out_status == "ineligible"


# 16/17. Egypt rows never become Out Of Egypt and vice versa.
def test_16_17_market_scopes_never_cross(db, visall_setup):
    co = visall_setup["company"]
    egypt_models = {"1.5 HOLT", "1.5 BlueCut", "1.6 HOLT", "1.6 BlueCut", "1.67 HOLT",
                    "1.56 Photo Gray & Brown", "1.56 Photo Gray"}
    ooe_models = {"1.6 Adapta BC B&G", "1.67 BlueCut", "1.74 HLOT", "1.56 Gray BlueCut",
                  "1.67 HLOT", "1.5 Tr B&G", "1.6 Tr B&G", "1.5 Sun 85%", "1.6 Sun 85%"}
    for vp in _all_vp(db, co):
        name = vp.variant.lens_model.name
        if name in egypt_models:
            assert vp.market_scope == EGYPT, name
        if name in ooe_models:
            assert vp.market_scope == OOE, name


# 18. Global RX manufacturing-eligibility rule (RX + zero PowerRange =
# eligible) is untouched by adding a pure-STOCK company like VISALL.
def test_18_global_rx_rule_unaffected(db, visall_setup):
    other = _mk_company(db, "OtherRxCo")
    cat = _mk_catalog(db, other)
    m = _mk_model(db, other, "RX Model")
    v = _mk_variant(db, m, 1.5)
    p_rx = models.VariantPricing(
        variant_id=v.id, availability=models.PricingAvailability.RX,
        price_pair=Decimal("2000.00"), currency="EGP", source_catalog_id=cat.id)
    db.add(p_rx); db.commit(); db.refresh(p_rx)
    status = product_search._row_eye_status(p_rx, _mk_presc(db, -12.0, -1.0, "rx-check"), "od")
    assert status == "eligible"   # zero PowerRange RX row stays eligible, VISALL didn't touch this


# 21. VISALL coexists cleanly alongside another company's rows in the same
# session with no cross-counting (proxy for "all previous manufacturer
# counts unchanged" - the live-DB row counts themselves are verified
# directly against optical_lens.db, not re-asserted here).
def test_21_coexists_without_cross_counting(db, visall_setup):
    other = _mk_company(db, "HOYA")
    cat2 = _mk_catalog(db, other)
    m2 = _mk_model(db, other, "HOYA Model")
    v2 = _mk_variant(db, m2, 1.6)
    p2 = models.VariantPricing(
        variant_id=v2.id, availability=models.PricingAvailability.STOCK,
        price_pair=Decimal("999.00"), currency="EGP", source_catalog_id=cat2.id, market_scope="Egypt")
    db.add(p2); db.commit()
    co = visall_setup["company"]
    assert len(_all_vp(db, co)) == 43          # VISALL count unaffected by HOYA's row
    assert len(_all_vp(db, other)) == 1        # HOYA's row not swallowed into VISALL


# 22. D1 scalar-diameter column stays dormant (real column, never populated) -
# same proxy used by the DIVEL turn for "D1 stash untouched" at the ORM level.
def test_22_d1_column_dormant(db, visall_setup):
    co = visall_setup["company"]
    variants = (db.query(models.LensVariant)
                  .join(models.LensModel)
                  .filter(models.LensModel.company_id == co.id).all())
    assert len(variants) == 16
    assert all(v.diameter is None for v in variants)


# ===== Domain-semantics correction pass (Gray/Brown, Transition, Adapta,
# BlueCut, HOLT/HLOT) - LensVariant metadata only, no pricing rewritten. =====

# 23. 1.56 Photo Gray & Brown: pricing count=2, photochromic, Gray+Brown
# represented as ONE evidence string - never duplicated per color.
def test_23_photo_gray_brown_domain(db, visall_setup):
    v = visall_setup["v_pgb"]
    rows = db.query(models.VariantPricing).filter(models.VariantPricing.variant_id == v.id).all()
    assert len(rows) == 2
    assert v.treatment_band == "Photochromic"
    assert "Gray" in v.color_variant and "Brown" in v.color_variant
    prices = {r.price_pair for r in rows}
    assert prices == {Decimal("1300.00")}   # both bands share one price - never split by color


# 24. 1.56 Photo Gray: photochromic, Gray only, count=2, stays distinct from
# the Gray & Brown sibling (fewer colors, not a merge candidate).
def test_24_photo_gray_domain(db, visall_setup):
    v = visall_setup["v_pg"]
    rows = db.query(models.VariantPricing).filter(models.VariantPricing.variant_id == v.id).all()
    assert len(rows) == 2
    assert v.treatment_band == "Photochromic"
    assert v.color_variant == "Gray"
    assert v.color_variant != visall_setup["v_pgb"].color_variant


# 25. 1.5/1.6 Tr B&G: "Tr" = Transition (photochromic brand), "B&G" = Gray +
# Brown colors; count=2 each.
def test_25_tr_bg_domain(db, visall_setup):
    for key in ("v_tr15", "v_tr16"):
        v = visall_setup[key]
        rows = db.query(models.VariantPricing).filter(models.VariantPricing.variant_id == v.id).all()
        assert len(rows) == 2, key
        assert v.design_variant == "Transition", key
        assert v.treatment_band == "Photochromic", key
        assert "Gray" in v.color_variant and "Brown" in v.color_variant, key


# 26. 1.6 Adapta BC B&G: index 1.60, Adapta family preserved, BlueCut YES,
# photochromic YES, Gray+Brown, "BC" is never interpreted as Base Curve.
def test_26_adapta_bc_bg_domain(db, visall_setup):
    v = visall_setup["v_adapta"]
    rows = db.query(models.VariantPricing).filter(models.VariantPricing.variant_id == v.id).all()
    assert len(rows) == 2
    assert v.index_value == 1.6
    assert v.design_variant == "Adapta"
    assert "BlueCut" in v.treatment_band
    assert "Photochromic" in v.treatment_band
    assert "Gray" in v.color_variant and "Brown" in v.color_variant
    # "BC" never became a base-curve field anywhere on this variant/model.
    assert not hasattr(models.LensVariant, "base_curve")
    assert "base curve" not in (v.treatment_band or "").lower()


# 27. 1.56 Gray BlueCut: index 1.56, BlueCut YES, Photochromic YES, Gray YES
# (single color, unlike Adapta's Gray+Brown) - distinct from plain BlueCut,
# plain Photo Gray, and Adapta BC B&G.
def test_27_gray_bluecut_domain(db, visall_setup):
    v = visall_setup["v_graybc"]
    rows = db.query(models.VariantPricing).filter(models.VariantPricing.variant_id == v.id).all()
    assert len(rows) == 2
    assert v.index_value == 1.56
    assert "BlueCut" in v.treatment_band
    assert "Photochromic" in v.treatment_band
    assert v.color_variant == "Gray"
    assert v.treatment_band != visall_setup["v_bluecut167"].treatment_band       # not plain BlueCut
    assert v.color_variant != visall_setup["v_pg"].color_variant or v.treatment_band != visall_setup["v_pg"].treatment_band
    assert v.treatment_band != visall_setup["v_adapta"].treatment_band or v.color_variant != visall_setup["v_adapta"].color_variant


# 28. HOLT/HLOT: canonical coating is HOLT everywhere; no separate canonical
# HLOT identity is created; HOLT is never treated as design/material; source
# rows printed as "HLOT" keep their printed model name (evidence preserved)
# while their coating classification canonicalizes to HOLT; prices/ranges
# for those rows are untouched.
def test_28_holt_hlot_canonical(db, visall_setup):
    holt_keys = ["v_holt15", "v_holt16", "v_holt167", "v_hlot167", "v_hlot174"]
    for key in holt_keys:
        v = visall_setup[key]
        assert v.treatment_band == "HOLT", key
    # Source-printed spelling survives on the model name, never silently renamed.
    assert visall_setup["m_hlot167"].name == "1.67 HLOT"
    assert visall_setup["m_hlot174"].name == "1.74 HLOT"
    assert visall_setup["m_holt167"].name == "1.67 HOLT"
    # HOLT is not (mis)used as material/index/design_type.
    for key in holt_keys:
        v = visall_setup[key]
        assert v.material == models.MaterialType.CR39
        assert v.design_type == models.DesignType.SPHERICAL
    # 1.67 HLOT pricing/ranges untouched by the canonicalization (3 rows).
    v167 = visall_setup["v_hlot167"]
    rows167 = db.query(models.VariantPricing).filter(models.VariantPricing.variant_id == v167.id).all()
    assert len(rows167) == 3
    assert {r.price_pair for r in rows167} == {Decimal("2100.00"), Decimal("2500.00")}


# 29/30. The exact duplicated Photo Gray & Brown positive band stays
# collapsed to one stored row and is never reinterpreted as two separate
# Gray/Brown prices (no per-color price split exists anywhere for this
# product - both bands apply to both colors identically).
def test_29_30_duplicate_band_stays_collapsed_not_per_color(db, visall_setup):
    v = visall_setup["v_pgb"]
    rows = db.query(models.VariantPricing).filter(models.VariantPricing.variant_id == v.id).all()
    assert len(rows) == 2   # not 3 (the literal print count) and not 4 (2 bands x 2 colors)
    power_scopes = [r.power_scope for r in rows]
    assert len(power_scopes) == len(set(power_scopes))   # each of the 2 remaining bands still distinct
    # No coating/color-keyed split of the +0.25..+6.00 band into a "Gray" row
    # and a separate "Brown" row - only one variant, one color_variant string.
    assert db.query(models.LensVariant).filter(models.LensVariant.lens_model_id == visall_setup["m_pgb"].id).count() == 1
