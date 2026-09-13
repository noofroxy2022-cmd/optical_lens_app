"""Permanent regression coverage for the PIXEL catalog-completeness correction
(page 16 RX Single Vision, page 15 STOCK 1.74 multi-band, page 17 Progressive
1.56/1.61/1.67 boundary mislabeling).

Deliberately synthetic, mirroring the real corrected shape directly via the
ORM (no PDF parsing, no dependency on the live optical_lens.db) so this stays
fast, isolated, and durable if the catalog file itself is ever replaced.
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


# --------------------------------------------------------------- fixtures
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
    existing = db.query(models.Coating).filter(models.Coating.code == code).first()
    if existing:
        return existing
    c = models.Coating(code=code, name=code)
    db.add(c); db.commit(); db.refresh(c)
    return c


def _mk_variant(db, model, index_value, design_variant=None, color_variant=None,
                design_type=models.DesignType.SPHERICAL, is_aspherical=False):
    v = models.LensVariant(
        lens_model_id=model.id, material=models.MaterialType.CR39, index_value=index_value,
        design_type=design_type, is_aspherical=is_aspherical,
        design_variant=design_variant, color_variant=color_variant, price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    return v


def _mk_pricing(db, variant, catalog, coating, *, availability, price,
                power_eligibility=models.PowerEligibilityStatus.UNRESTRICTED,
                market_scope=None):
    vp = models.VariantPricing(
        variant_id=variant.id, coating_id=coating.id if coating else None,
        availability=availability, power_eligibility=power_eligibility,
        price_pair=Decimal(str(price)), currency="EGP", source_catalog_id=catalog.id,
        market_scope=market_scope)
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


# ===========================================================================
# Page 16 - RX Single Vision, Out Of Egypt: 18 combos x {Free Form, High
# Definition} = 36 distinct commercial identities, all UNRESOLVED eligibility
# (source prints no power range at all - see the parser's own corruption
# guard in _extract_price for why these were never auto-priced).
# ===========================================================================
PAGE16_ROWS = [
    ("Astro", "Clear", 1.5, 2500, 3500),
    ("Astro", "Transmatic/G/B", 1.5, 6000, 7000),
    ("Astro", "Polz/G/B/G15", 1.5, 5500, 6500),
    ("Astro", "DWEAR/B", 1.5, 13000, 14000),
    ("Astro", "Clear", 1.53, 5500, 6500),
    ("Astro", "Transition/G/B", 1.53, 10000, 12000),
    ("Astro", "Clear", 1.56, 2500, 3500),
    ("Astro+", "Clear", 1.56, 3500, 4500),
    ("Astro", "Clear", 1.61, 4000, 5000),
    ("Astro+", "Clear", 1.61, 5000, 6000),
    ("Astro", "Transmatic/G/B", 1.61, 8000, 9000),
    ("Astro", "Polz/G/B", 1.61, 10000, 11000),
    ("Astro", "Clear", 1.67, 5500, 6500),
    ("Astro+", "Clear", 1.67, 6500, 7500),
    ("Astro", "Transmatic/G/B", 1.67, 9500, 10500),
    ("Astro", "Polz/G/B", 1.67, 12000, 13000),
    ("Astro", "Clear", 1.74, 9000, 10000),
    ("Astro", "Transition/G/B", 1.74, 16000, 17000),
]


@pytest.fixture()
def pixel_sv_setup(db):
    co = _mk_company(db, "Pixel")
    cat = _mk_catalog(db, co)
    model = _mk_model(db, co, "Pixel", models.LensCategory.SINGLE_VISION)
    coatings = {code: _mk_coating(db, code) for code in ("Astro", "Astro+")}
    pricings = {}
    for coating_code, color, idx, price_ff, price_hd in PAGE16_ROWS:
        for design, price in (("Free Form", price_ff), ("High Definition", price_hd)):
            key = (coating_code, color, idx, design)
            variant = (
                db.query(models.LensVariant)
                .filter(models.LensVariant.lens_model_id == model.id,
                        models.LensVariant.index_value == idx,
                        models.LensVariant.design_variant == design,
                        models.LensVariant.color_variant == color)
                .first()
            )
            if variant is None:
                variant = _mk_variant(db, model, idx, design_variant=design, color_variant=color)
            pricing = _mk_pricing(
                db, variant, cat, coatings[coating_code],
                availability=models.PricingAvailability.RX, price=price,
                power_eligibility=models.PowerEligibilityStatus.UNRESOLVED,
                market_scope="Out Of Egypt",
            )
            pricings[key] = (variant, pricing)
    return {"company": co, "catalog": cat, "model": model, "coatings": coatings, "pricings": pricings}


# A. expected commercial row count
def test_A_page16_row_count_is_36(db, pixel_sv_setup):
    model = pixel_sv_setup["model"]
    count = (
        db.query(models.VariantPricing)
        .join(models.LensVariant)
        .filter(models.LensVariant.lens_model_id == model.id,
                models.VariantPricing.effective_to.is_(None))
        .count()
    )
    assert count == 36


# B. every one of the 36 exact price associations
def test_B_page16_all_prices_match_source(db, pixel_sv_setup):
    pricings = pixel_sv_setup["pricings"]
    for coating_code, color, idx, price_ff, price_hd in PAGE16_ROWS:
        _, p_ff = pricings[(coating_code, color, idx, "Free Form")]
        _, p_hd = pricings[(coating_code, color, idx, "High Definition")]
        assert p_ff.price_pair == Decimal(str(price_ff)), (coating_code, color, idx, "Free Form")
        assert p_hd.price_pair == Decimal(str(price_hd)), (coating_code, color, idx, "High Definition")


# C. Free Form and High Definition are distinct commercial identities, never merged
def test_C_free_form_and_high_definition_are_distinct(db, pixel_sv_setup):
    v_ff, p_ff = pixel_sv_setup["pricings"][("Astro", "Clear", 1.5, "Free Form")]
    v_hd, p_hd = pixel_sv_setup["pricings"][("Astro", "Clear", 1.5, "High Definition")]
    assert v_ff.id != v_hd.id
    assert p_ff.id != p_hd.id
    assert p_ff.price_pair != p_hd.price_pair


# D/E/F. category / availability / market on every page-16 row
def test_DEF_category_availability_market(db, pixel_sv_setup):
    model = pixel_sv_setup["model"]
    assert model.category == models.LensCategory.SINGLE_VISION
    rows = (
        db.query(models.VariantPricing)
        .join(models.LensVariant)
        .filter(models.LensVariant.lens_model_id == model.id)
        .all()
    )
    assert len(rows) == 36
    for vp in rows:
        assert vp.availability == models.PricingAvailability.RX
        assert vp.market_scope == "Out Of Egypt"


# G. power eligibility stays UNRESOLVED unless catalog evidence proves a limit -
# an UNRESOLVED page-16 row must never be reported as a PROVEN RX match, for
# any prescription, including a low, ordinary power. A pinned-product search
# is allowed to surface it as "exists but unresolved" (never as a confirmed
# quote); an un-pinned, company/category-scoped search must show nothing
# proven either.
def test_G_unresolved_never_proven_eligible(db, pixel_sv_setup):
    model = pixel_sv_setup["model"]
    for sph in (-2.0, 8.0):
        presc = _mk_presc(db, sph, name=f"g-pinned-{sph}")
        resp = _targeted(db, presc, lens_model_id=model.id, index_value=1.5)
        assert resp.availability_answer.code == "power_eligibility_unknown", sph
        assert resp.eligibility_unknown_count > 0, sph
        for grp in resp.groups:
            if grp.key in ("stock_egypt", "stock_out_of_egypt"):
                assert grp.count == 0, (sph, grp.key, grp.count)

        presc2 = _mk_presc(db, sph, name=f"g-unpinned-{sph}")
        resp2 = _targeted(db, presc2, company_id=model.company_id,
                          category=models.LensCategory.SINGLE_VISION, index_value=1.5)
        assert resp2.exact_total == 0, sph
        assert resp2.availability_answer.code != "stock_egypt", sph


# ===========================================================================
# Page 15 - STOCK Index 1.74 multi-band split (Aspheric vs DAS/Double
# Aspheric, each a distinct commercial identity with several SPH/CYL bands
# sharing one price).
# ===========================================================================
@pytest.fixture()
def pixel_1_74_setup(db):
    co = _mk_company(db, "Pixel")
    cat = _mk_catalog(db, co)
    model = _mk_model(db, co, "Pixel", models.LensCategory.SINGLE_VISION)
    astro = _mk_coating(db, "Astro")

    v_asph = _mk_variant(db, model, 1.74, color_variant="Clear",
                         design_type=models.DesignType.ASPHERICAL, is_aspherical=True)
    p_asph = _mk_pricing(db, v_asph, cat, astro, availability=models.PricingAvailability.STOCK,
                         price=5500, market_scope="Out Of Egypt")
    for sph_min, sph_max, cyl_min, cyl_max in [(-10.0, -3.0, -3.0, 0.0),
                                                (-13.0, -10.0, -2.0, 0.0),
                                                (-15.0, -13.0, 0.0, 0.0)]:
        _mk_range(db, model, v_asph, p_asph, sph_min, sph_max, cyl_min, cyl_max)

    v_das = _mk_variant(db, model, 1.74, color_variant="Clear",
                        design_type=models.DesignType.DOUBLE_ASPHERICAL, is_aspherical=True)
    p_das = _mk_pricing(db, v_das, cat, astro, availability=models.PricingAvailability.STOCK,
                        price=8500, market_scope="Out Of Egypt")
    for sph_min, sph_max, cyl_min, cyl_max in [(-10.0, -3.0, -4.0, 0.0),
                                                (-12.0, -10.0, -2.0, 0.0)]:
        _mk_range(db, model, v_das, p_das, sph_min, sph_max, cyl_min, cyl_max)

    return {"model": model, "v_asph": v_asph, "v_das": v_das}


# H. every printed sub-band is correctly eligible
@pytest.mark.parametrize("sph,cyl", [
    (-5.0, -2.0),    # aspheric band 1
    (-11.0, -1.5),   # aspheric band 2
    (-14.0, 0.0),    # aspheric band 3 (cyl must be exactly 0)
    (-6.0, -3.5),    # DAS band 1
    (-11.0, -1.0),   # DAS band 2
])
def test_H_all_1_74_sub_bands_eligible(db, pixel_1_74_setup, sph, cyl):
    model = pixel_1_74_setup["model"]
    presc = _mk_presc(db, sph, cyl, name=f"h-{sph}-{cyl}")
    resp = _targeted(db, presc, lens_model_id=model.id, index_value=1.74)
    assert resp.exact_total >= 1, (sph, cyl)


# I. just outside every band -> ineligible, never silently widened. Scoped by
# company/category/index (NOT a pinned lens_model_id) so an out-of-band
# candidate is actually excluded from exact_total, rather than surfaced via
# the deliberate "pinned product, show it anyway" per-eye-matrix allowance.
@pytest.mark.parametrize("sph,cyl", [
    (-2.0, 0.0),     # above the highest (least myopic) aspheric/DAS band
    (-16.0, 0.0),    # below the lowest band of either identity
    (-14.0, -0.5),   # aspheric band 3 requires cyl==0 exactly - any cyl must fail
])
def test_I_just_outside_bands_stays_ineligible(db, pixel_1_74_setup, sph, cyl):
    model = pixel_1_74_setup["model"]
    presc = _mk_presc(db, sph, cyl, name=f"i-{sph}-{cyl}")
    resp = _targeted(db, presc, company_id=model.company_id,
                     category=models.LensCategory.SINGLE_VISION, index_value=1.74)
    assert resp.exact_total == 0, (sph, cyl)


# ===========================================================================
# Page 17 - Progressive 1.56/1.61/1.67 Astro/Clear boundary correction
# ===========================================================================
@pytest.fixture()
def pixel_progressive_setup(db):
    co = _mk_company(db, "Pixel")
    cat = _mk_catalog(db, co)
    model = _mk_model(db, co, "Pixel", models.LensCategory.PROGRESSIVE)
    astro = _mk_coating(db, "Astro")

    TRUE = {
        (1.56, "Core"): 4500, (1.56, "Advance"): 6500,
        (1.61, "Core"): 6500, (1.61, "Advance"): 8500, (1.61, "Premium"): 10500,
        (1.67, "Core"): 8500, (1.67, "Advance"): 10500, (1.67, "Premium"): 12500,
    }
    pricings = {}
    for (idx, design), price in TRUE.items():
        v = _mk_variant(db, model, idx, design_variant=design, color_variant="Clear")
        p = _mk_pricing(db, v, cat, astro, availability=models.PricingAvailability.RX,
                        price=price, market_scope="Out Of Egypt")
        pricings[(idx, design)] = (v, p)
    return {"model": model, "pricings": pricings}


# J. every resolved page-17 identity maps to its correct (not the boundary-
# shifted) price
def test_J_page17_prices_are_not_boundary_shifted(db, pixel_progressive_setup):
    pricings = pixel_progressive_setup["pricings"]
    expected = {
        (1.56, "Core"): 4500, (1.56, "Advance"): 6500,
        (1.61, "Core"): 6500, (1.61, "Advance"): 8500, (1.61, "Premium"): 10500,
        (1.67, "Core"): 8500, (1.67, "Advance"): 10500, (1.67, "Premium"): 12500,
    }
    for key, price in expected.items():
        _, p = pricings[key]
        assert p.price_pair == Decimal(str(price)), key
    # the historically-confused values (e.g. 1.61/Core showing 1.67's 8500,
    # or 1.56/Premium existing at all) must never reappear
    assert (1.56, "Premium") not in pricings


# K. no duplicate current commercial identities (same variant+coating+
# availability+market with more than one CURRENT row)
def test_K_no_duplicate_current_identities(db, pixel_progressive_setup, pixel_sv_setup):
    for setup in (pixel_progressive_setup, pixel_sv_setup):
        model = setup["model"]
        rows = (
            db.query(models.VariantPricing)
            .join(models.LensVariant)
            .filter(models.LensVariant.lens_model_id == model.id,
                    models.VariantPricing.effective_to.is_(None))
            .all()
        )
        seen = set()
        for vp in rows:
            key = (vp.variant_id, vp.coating_id, vp.availability, vp.market_scope)
            assert key not in seen, f"duplicate current pricing identity: {key}"
            seen.add(key)


# L. category is a hard boundary for alternatives - no cross-category
# contamination (e.g. Progressive/Bifocal must never show up as an
# "alternative" to a Single Vision search), and no cross-company leakage.
def test_L_no_cross_category_or_cross_company_alternatives(db, pixel_sv_setup, pixel_progressive_setup):
    sv_model = pixel_sv_setup["model"]
    presc = _mk_presc(db, -30.0, name="l-impossible")  # no exact match anywhere -> alternatives run
    f = schemas.LensFilters(company_id=sv_model.company_id, category=models.LensCategory.SINGLE_VISION)
    req = schemas.ProductSearchRequest(mode="targeted", filters=f, include_alternatives=True)
    resp = product_search.search(db, presc, req)
    for alt in (resp.alternatives or []):
        assert alt.result.lens_model.category == models.LensCategory.SINGLE_VISION
        assert alt.result.lens_model.company_id == sv_model.company_id
