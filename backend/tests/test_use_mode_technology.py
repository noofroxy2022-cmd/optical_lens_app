"""Permanent regression coverage for V1.2 core-workflow: prescription use_mode
(distance/reading/bifocal/progressive) and canonical technology_intent
(blue_light/photo_gray/photo_brown/blue_photo_gray/blue_photo_brown).

Deliberately synthetic, mirroring the same in-memory ORM pattern already used
by test_maxxee_import.py / test_synchrony_import.py - no PDF parsing, no
dependency on the live optical_lens.db/v12_dev.db. Company names below reuse
real manufacturer names only where doing so exercises the SAME evidence this
project's technology_evidence.py registry was built from (Phase 4 catalog
audit); the PowerRange numbers themselves are synthetic.
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
    existing = db.query(models.Coating).filter(models.Coating.code == code).first()
    if existing:
        return existing
    c = models.Coating(code=code, name=code)
    db.add(c); db.commit(); db.refresh(c)
    return c


def _mk_variant(db, model, index_value=1.50, design_variant=None, treatment_band=None,
                color_variant=None, design_tier=None, material=models.MaterialType.CR39):
    v = models.LensVariant(
        lens_model_id=model.id, material=material, index_value=index_value,
        design_type=models.DesignType.SPHERICAL, is_aspherical=False,
        design_variant=design_variant, treatment_band=treatment_band,
        color_variant=color_variant, design_tier=design_tier, price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    return v


def _mk_pricing(db, variant, catalog, *, availability, price, coating=None, market_scope=None):
    vp = models.VariantPricing(
        variant_id=variant.id, coating_id=(coating.id if coating else None),
        availability=availability, price_pair=Decimal(str(price)),
        currency="EGP", source_catalog_id=catalog.id, market_scope=market_scope)
    db.add(vp); db.commit(); db.refresh(vp)
    return vp


def _mk_range(db, model, variant, pricing, sph_min, sph_max, cyl_min=-10.0, cyl_max=0.0,
             add_min=None, add_max=None):
    pr = models.PowerRange(lens_model_id=model.id, variant_id=variant.id, pricing_id=pricing.id,
                           sph_min=sph_min, sph_max=sph_max, cyl_min=cyl_min, cyl_max=cyl_max,
                           add_min=add_min, add_max=add_max)
    db.add(pr); db.commit()
    return pr


def _mk_presc(db, od_sph, os_sph, od_cyl=-1.0, os_cyl=-1.0, od_axis=90, os_axis=90,
             od_add=None, os_add=None, name="p"):
    p = models.Prescription(
        customer_name=name,
        od_sph_original=od_sph, od_cyl_original=od_cyl, od_axis_original=od_axis,
        od_sph=od_sph, od_cyl=od_cyl, od_axis=od_axis, od_add=od_add,
        os_sph_original=os_sph, os_cyl_original=os_cyl, os_axis_original=os_axis,
        os_sph=os_sph, os_cyl=os_cyl, os_axis=os_axis, os_add=os_add, pd=63)
    db.add(p); db.commit(); db.refresh(p)
    return p


def _search(db, presc, use_mode=None, technology_intent=None, mode="automatic"):
    req = schemas.ProductSearchRequest(mode=mode, use_mode=use_mode, technology_intent=technology_intent)
    return product_search.search(db, presc, req)


def _stock_product(db, company_name, model_name, category, sph_min, sph_max, cyl_min=-10.0, cyl_max=0.0,
                    add_min=None, add_max=None, coating_code=None, treatment_band=None,
                    color_variant=None, price=1000):
    co = _mk_company(db, company_name)
    cat = _mk_catalog(db, co)
    m = _mk_model(db, co, model_name, category)
    v = _mk_variant(db, m, treatment_band=treatment_band, color_variant=color_variant)
    coating = _mk_coating(db, coating_code) if coating_code else None
    vp = _mk_pricing(db, v, cat, availability=models.PricingAvailability.STOCK, price=price,
                      coating=coating, market_scope="Egypt")
    _mk_range(db, m, v, vp, sph_min=sph_min, sph_max=sph_max, cyl_min=cyl_min, cyl_max=cyl_max,
              add_min=add_min, add_max=add_max)
    return co, m, v, vp


def _rx_product(db, company_name, model_name, category, sph_min, sph_max, cyl_min=-10.0, cyl_max=0.0,
                 coating_code=None, treatment_band=None, color_variant=None, price=1000, company=None,
                 index_value=1.50, market_scope=None):
    co = company or _mk_company(db, company_name)
    cat = _mk_catalog(db, co)
    m = _mk_model(db, co, model_name, category)
    v = _mk_variant(db, m, index_value=index_value, treatment_band=treatment_band, color_variant=color_variant)
    coating = _mk_coating(db, coating_code) if coating_code else None
    vp = _mk_pricing(db, v, cat, availability=models.PricingAvailability.RX, price=price, coating=coating, market_scope=market_scope)
    _mk_range(db, m, v, vp, sph_min=sph_min, sph_max=sph_max, cyl_min=cyl_min, cyl_max=cyl_max)
    return co, m, v, vp


# ===================================================================== USE_MODE

def test_distance_ignores_add(db):
    """A. Distance: ADD present on the Rx must NOT block a single_vision Stock
    range that has no add_min/add_max (the exact bug use_mode=distance fixes)."""
    _stock_product(db, "TestCo", "Basic", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-3.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0)
    presc = _mk_presc(db, -2.0, -2.5, od_cyl=-1.0, os_cyl=-1.0, od_add=2.0, os_add=2.0)
    resp = _search(db, presc, use_mode="distance")
    assert resp.availability_answer.code != "validation_error"
    assert resp.exact_total >= 1
    assert resp.best_match.od.stock_egypt is True


def test_reading_derives_near_rx_and_preserves_stored(db):
    """B. Reading: derived near Rx = Distance SPH + ADD; stored Rx untouched."""
    # range covers ONLY the derived near powers (0.00/-0.50), NOT the distance
    # powers (-2.00/-2.50) - proves the search actually used the near Rx.
    _stock_product(db, "TestCo", "Basic", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-0.5, sph_max=0.0, cyl_min=-1.0, cyl_max=0.0)
    presc = _mk_presc(db, -2.0, -2.5, od_cyl=-1.0, os_cyl=-0.5, od_axis=90, os_axis=80,
                       od_add=2.0, os_add=2.0)
    resp = _search(db, presc, use_mode="reading")
    assert resp.availability_answer.code != "validation_error", resp.availability_answer
    assert resp.exact_total >= 1
    assert resp.derived_search_rx is not None
    assert resp.derived_search_rx.od_sph == 0.0
    assert resp.derived_search_rx.os_sph == -0.5
    assert resp.derived_search_rx.od_axis == 90
    assert resp.derived_search_rx.os_axis == 80
    # stored prescription must be completely unchanged
    fresh = db.query(models.Prescription).get(presc.id)
    assert fresh.od_sph == -2.0 and fresh.os_sph == -2.5
    assert fresh.od_add == 2.0 and fresh.os_add == 2.0


def test_reading_missing_add_is_a_validation_failure_not_invented(db):
    """C. Reading with no ADD -> clear validation failure, zero results, no
    invented ADD value."""
    presc = _mk_presc(db, -2.0, -2.5, od_add=None, os_add=None)
    resp = _search(db, presc, use_mode="reading")
    assert resp.availability_answer.code == "validation_error"
    assert resp.exact_total == 0
    assert resp.best_match is None
    assert resp.derived_search_rx is None


def test_bifocal_uses_distance_rx_plus_add_no_reading_conversion(db):
    """D. Bifocal: original Distance SPH + real ADD retained (no SPH+ADD
    conversion); category is a hard boundary against single_vision."""
    _stock_product(db, "TestCo", "BiModel", schemas.LensCategory.BIFOCAL,
                    sph_min=-3.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    add_min=1.5, add_max=2.5)
    # a same-power single_vision decoy must NEVER leak into a bifocal search
    _stock_product(db, "TestCo", "SVModel", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-3.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0)
    presc = _mk_presc(db, -2.0, -2.5, od_cyl=-1.0, os_cyl=-1.0, od_add=2.0, os_add=2.0)
    resp = _search(db, presc, use_mode="bifocal")
    assert resp.exact_total >= 1
    assert all(r.category == "bifocal" for r in resp.groups[0].results) if resp.groups else True
    for grp in resp.groups:
        for r in grp.results:
            assert r.category == "bifocal"


def test_progressive_uses_distance_rx_plus_add_no_reading_conversion(db):
    """E. Progressive: same rule as Bifocal, category=progressive."""
    _stock_product(db, "TestCo", "ProModel", schemas.LensCategory.PROGRESSIVE,
                    sph_min=-3.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    add_min=1.5, add_max=2.5)
    _stock_product(db, "TestCo", "SVModel", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-3.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0)
    presc = _mk_presc(db, -2.0, -2.5, od_cyl=-1.0, os_cyl=-1.0, od_add=2.0, os_add=2.0)
    resp = _search(db, presc, use_mode="progressive")
    assert resp.exact_total >= 1
    for grp in resp.groups:
        for r in grp.results:
            assert r.category == "progressive"


def test_bifocal_progressive_missing_add_validation(db):
    """D/E: missing ADD for Bifocal/Progressive is a validation failure, not
    an invented ADD."""
    presc = _mk_presc(db, -2.0, -2.5, od_add=None, os_add=0.0)
    for mode in ("bifocal", "progressive"):
        resp = _search(db, presc, use_mode=mode)
        assert resp.availability_answer.code == "validation_error", mode
        assert resp.exact_total == 0, mode


def test_category_safety_distance_never_shows_progressive(db):
    """F. Category safety: Distance/Reading never contaminated by Bifocal or
    Progressive results even when the SAME power range would optically fit."""
    _stock_product(db, "TestCo", "ProModel", schemas.LensCategory.PROGRESSIVE,
                    sph_min=-3.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0, add_min=1.5, add_max=2.5)
    presc = _mk_presc(db, -2.0, -2.5, od_cyl=-1.0, os_cyl=-1.0, od_add=2.0, os_add=2.0)
    resp = _search(db, presc, use_mode="distance")
    assert resp.exact_total == 0
    for grp in resp.groups:
        assert grp.count == 0


def test_unknown_use_mode_is_a_validation_failure(db):
    presc = _mk_presc(db, -2.0, -2.5)
    resp = _search(db, presc, use_mode="something_else")
    assert resp.availability_answer.code == "validation_error"
    assert resp.exact_total == 0


def test_use_mode_none_preserves_prior_behaviour(db):
    """Backward compatibility: use_mode=None must behave exactly like every
    pre-V1.2 caller (no category restriction, ADD checked as before)."""
    _stock_product(db, "TestCo", "ProModel", schemas.LensCategory.PROGRESSIVE,
                    sph_min=-3.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0, add_min=1.5, add_max=2.5)
    presc = _mk_presc(db, -2.0, -2.5, od_cyl=-1.0, os_cyl=-1.0, od_add=2.0, os_add=2.0)
    resp = _search(db, presc, use_mode=None)
    assert resp.exact_total >= 1  # unrestricted by category, exactly as before


# ================================================================ TECHNOLOGY

def _tech_presc(db):
    return _mk_presc(db, -2.0, -2.0, od_cyl=0.0, os_cyl=0.0, od_add=None, os_add=None)


def test_blue_light_cross_manufacturer(db):
    """G. blue_light must surface proven products from MULTIPLE manufacturers
    using different commercial names for the same technology."""
    _stock_product(db, "HOYA", "Hilux", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-3.0, sph_max=0.0, coating_code="Long Life Blue Control")
    _stock_product(db, "VISALL", "1.5 BlueCut", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-3.0, sph_max=0.0, treatment_band="BlueCut")
    _stock_product(db, "PlainCo", "Plain", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-3.0, sph_max=0.0)  # no technology evidence at all
    presc = _tech_presc(db)
    resp = _search(db, presc, technology_intent="blue_light")
    companies = {r.company_name for grp in resp.groups for r in grp.results}
    assert companies == {"HOYA", "VISALL"}


def test_photo_gray_rejects_ordinary_gray_tint(db):
    """H. photo_gray must include proven photochromic Gray and REJECT an
    ordinary Gray tint / Gray sun lens with no photochromic evidence."""
    _stock_product(db, "VISALL", "1.56 PhotoGray", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-3.0, sph_max=0.0, treatment_band="Photochromic", color_variant="Gray")
    _stock_product(db, "PLATINUM", "Sun Gray", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-3.0, sph_max=0.0, color_variant="Gray")  # NOT photochromic
    presc = _tech_presc(db)
    resp = _search(db, presc, technology_intent="photo_gray")
    companies = {r.company_name for grp in resp.groups for r in grp.results}
    assert companies == {"VISALL"}


def test_photo_brown(db):
    """I. photo_brown - same rule, Brown."""
    _stock_product(db, "Maxxee", "H.M.C+ Brown", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-3.0, sph_max=0.0, treatment_band="Photo", color_variant="Brown")
    _stock_product(db, "PlainCo", "Brown Sunlens", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-3.0, sph_max=0.0, color_variant="Brown")  # NOT photochromic
    presc = _tech_presc(db)
    resp = _search(db, presc, technology_intent="photo_brown")
    companies = {r.company_name for grp in resp.groups for r in grp.results}
    assert companies == {"Maxxee"}


def _hat_presc(db):
    """The exact HAT-02/HAT-fix acceptance prescription: OD/OS SPH -2 / CYL
    -1 x 90 - distinct from _tech_presc (CYL 0) so eligibility is proven
    against the real astigmatic case the owner tested with, not a
    coincidentally-easy spherical one."""
    return _mk_presc(db, -2.0, -2.0, od_cyl=-1.0, os_cyl=-1.0, od_axis=90, os_axis=90)


def test_pixel_transmatic_proves_photo_brown_and_photo_gray_when_power_eligible(db):
    """RECONCILIATION (owner-confirmed HAT fix, 2026-09-21): Pixel's
    "Transmatic"/"Transition" line is TR/Transition-equivalent (already
    proven photochromic by catalog text) and, per the owner's confirmed
    Transition=Gray+Brown relationship, now proves BOTH colours - mirrors the
    real DB's 1.61 Transmatic/G Stock Out Of Egypt row (sph -8/0, cyl -2/0,
    price 5500), which the exact HAT prescription (-2/-1x90) falls inside."""
    _stock_product(db, "Pixel", "Astro", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-8.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    color_variant="Transmatic/G", price=5500)
    presc = _hat_presc(db)
    # search via customer_needs (the real seller-facing field), not the legacy scalar
    req = schemas.ProductSearchRequest(mode="automatic", use_mode="distance", customer_needs=["photo_brown"])
    resp_brown = product_search.search(db, presc, req)
    assert resp_brown.exact_total == 1
    assert resp_brown.groups[0].results[0].company_name == "Pixel"
    req_gray = schemas.ProductSearchRequest(mode="automatic", use_mode="distance", customer_needs=["photo_gray"])
    resp_gray = product_search.search(db, presc, req_gray)
    assert resp_gray.exact_total == 1
    assert resp_gray.groups[0].results[0].company_name == "Pixel"


def test_platinum_sun_proves_photo_gray_and_photo_brown_not_sun_polarized(db):
    """RECONCILIATION (owner-confirmed HAT fix, 2026-09-21): PLATINUM "Sun"
    (commercially "Sun Active") is confirmed photochromic Gray+Brown - mirrors
    the real DB's "1.56 SUN" Stock/Egypt row (price 800, sph -6/+4, cyl -3/0).
    "Sun + Polarized" is a DIFFERENT treatment_band with no photochromic
    evidence of its own and must stay unproven."""
    _stock_product(db, "PLATINUM", "1.56 SUN", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-6.0, sph_max=4.0, cyl_min=-3.0, cyl_max=0.0,
                    treatment_band="Sun", price=800)
    _stock_product(db, "PLATINUM", "1.5 POLARIZED", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-6.0, sph_max=4.0, cyl_min=-3.0, cyl_max=0.0,
                    treatment_band="Sun + Polarized", price=650)
    presc = _hat_presc(db)
    req = schemas.ProductSearchRequest(mode="automatic", use_mode="distance", customer_needs=["photo_brown"])
    resp = product_search.search(db, presc, req)
    companies_models = {(r.company_name, r.model_name) for grp in resp.groups for r in grp.results}
    assert ("PLATINUM", "1.56 SUN") in companies_models
    assert ("PLATINUM", "1.5 POLARIZED") not in companies_models


def test_bbgr_tr7_proves_photo_gray_and_photo_brown_when_power_eligible(db):
    """RECONCILIATION (owner-confirmed HAT fix, 2026-09-21): BBGR "TR7" is
    BBGR's Transition line, confirmed photochromic Gray+Brown - mirrors the
    real DB's 1.56/"Neva+"/Stock/Egypt TR7 row (price 5100, sph -6/+4,
    cyl -2/0), which the exact HAT prescription (-2/-1x90) falls inside."""
    _stock_product(db, "BBGR", "1.56 TR7", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-6.0, sph_max=4.0, cyl_min=-2.0, cyl_max=0.0,
                    treatment_band="TR7", coating_code="Neva+", price=5100)
    presc = _hat_presc(db)
    req = schemas.ProductSearchRequest(mode="automatic", use_mode="distance", customer_needs=["photo_brown"])
    resp = product_search.search(db, presc, req)
    assert resp.exact_total == 1
    assert resp.groups[0].results[0].company_name == "BBGR"


def test_bbgr_tr7_power_ineligible_stays_excluded_no_range_invented(db):
    """Safety companion to the above: the SAME proven TR7 capability must
    NEVER override a genuine PowerRange miss - eligibility is decided
    entirely separately from technology capability."""
    _stock_product(db, "BBGR", "1.56 TR7 (narrow)", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-1.0, sph_max=0.0, cyl_min=-0.5, cyl_max=0.0,  # does NOT cover -2/-1
                    treatment_band="TR7", coating_code="Neva+", price=5100)
    presc = _hat_presc(db)
    req = schemas.ProductSearchRequest(mode="automatic", use_mode="distance", customer_needs=["photo_brown"])
    resp = product_search.search(db, presc, req)
    assert resp.exact_total == 0


def test_platinum_g2_and_bbgr_blu_stop_still_never_prove_photo_brown(db):
    """Negative safety: the fix is scoped to the exact "Sun"/"TR7"
    treatment_band values - PLATINUM's unrelated blue-light "G2" line and
    BBGR's unrelated blue-light "Blu stop" line must NOT gain photo_brown
    merely from company association."""
    _stock_product(db, "PLATINUM", "1.56 G2", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-6.0, sph_max=4.0, treatment_band="G2", color_variant="Gray", price=900)
    _stock_product(db, "BBGR", "1.56 Blu stop", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-6.0, sph_max=4.0, treatment_band="Blu stop", price=900)
    presc = _hat_presc(db)
    req = schemas.ProductSearchRequest(mode="automatic", use_mode="distance", customer_needs=["photo_brown"])
    resp = product_search.search(db, presc, req)
    assert resp.exact_total == 0


def test_new_evidence_does_not_break_strict_blue_photo_gray_and(db):
    """Strict AND preserved: a Pixel Transmatic/G row with NO blue-light
    coating proves photo_gray alone but must still FAIL blue_photo_gray."""
    _stock_product(db, "Pixel", "Astro", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-8.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    color_variant="Transmatic/G", price=5500)
    presc = _hat_presc(db)
    resp = _search(db, presc, technology_intent="photo_gray")
    assert resp.exact_total == 1
    resp_and = _search(db, presc, technology_intent="blue_photo_gray")
    assert resp_and.exact_total == 0


def test_new_evidence_rx_suppressed_by_stock_over_rx_fallback(db):
    """Stock-over-RX preserved: a proven-eligible PLATINUM Sun RX row is
    correctly suppressed once an actionable Stock alternative exists for the
    same distance search - the exact HAT-observed rx_count=0 mechanism."""
    _stock_product(db, "VISALL", "1.56 Photo Gray & Brown", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-6.0, sph_max=4.0, treatment_band="Photochromic",
                    color_variant="Gray / Brown", price=1300)
    _rx_product(db, "PLATINUM", "PLATINUM RX Single Vision", schemas.LensCategory.SINGLE_VISION,
                sph_min=-6.0, sph_max=4.0, cyl_min=-3.0, cyl_max=0.0,
                treatment_band="Sun", price=6000)
    presc = _hat_presc(db)
    req = schemas.ProductSearchRequest(mode="automatic", use_mode="distance", customer_needs=["photo_brown"])
    resp = product_search.search(db, presc, req)
    assert resp.rx_count == 0
    assert resp.stock_egypt_count == 1


def test_blue_photo_gray_strict_and(db):
    """J. blue_photo_gray requires BOTH on the SAME row - blue-only and
    photo-gray-only must both be rejected."""
    _stock_product(db, "VISALL", "Combo", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-3.0, sph_max=0.0, treatment_band="Photochromic + BlueCut", color_variant="Gray")
    _stock_product(db, "VISALL", "BlueOnly", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-3.0, sph_max=0.0, treatment_band="BlueCut")
    _stock_product(db, "VISALL", "PhotoGrayOnly", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-3.0, sph_max=0.0, treatment_band="Photochromic", color_variant="Gray")
    presc = _tech_presc(db)
    resp = _search(db, presc, technology_intent="blue_photo_gray")
    names = {r.model_name for grp in resp.groups for r in grp.results}
    assert names == {"Combo"}


def test_blue_photo_brown_strict_and(db):
    """K. blue_photo_brown requires BOTH on the SAME row (SCOPE evidence:
    "Transitions Relax Gray-Brown Blue Light" proves blue+gray+brown at once)."""
    _stock_product(db, "SCOPE", "Transitions Combo", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-3.0, sph_max=0.0, treatment_band="Transitions Relax Gray-Brown Blue Light")
    _stock_product(db, "SCOPE", "PhotoGrayBrownOnly", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-3.0, sph_max=0.0, treatment_band="Transitions Gray-Brown")
    presc = _tech_presc(db)
    resp = _search(db, presc, technology_intent="blue_photo_brown")
    names = {r.model_name for grp in resp.groups for r in grp.results}
    assert names == {"Transitions Combo"}
    # the same combo row must ALSO satisfy blue_photo_gray (proves all three)
    resp2 = _search(db, presc, technology_intent="blue_photo_gray")
    names2 = {r.model_name for grp in resp2.groups for r in grp.results}
    assert names2 == {"Transitions Combo"}


def test_ambiguous_terms_never_match(db):
    """False-positive coverage (Phase 13): Mirror/Polarized colour values and
    an unregistered ambiguous "Blue"-containing code must never be treated as
    proven technology.

    RECONCILED (owner-confirmed HAT fix, 2026-09-21): the Pixel "Transmatic/
    G/B" case this test used to include here was moved to its own dedicated
    test (test_pixel_transmatic_proves_photo_gray_and_photo_brown) - it is no
    longer an ambiguous term, it is now a proven TR/Transition Gray+Brown
    relationship. This test keeps only the still-genuinely-ambiguous DIVEL
    Mirror-tint case."""
    _stock_product(db, "DIVEL ITALIA", "Mirrorish", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-3.0, sph_max=0.0, color_variant="Gray/Brown/G15/Blue")
    presc = _tech_presc(db)
    for intent in ("blue_light", "photo_gray", "photo_brown", "blue_photo_gray", "blue_photo_brown"):
        resp = _search(db, presc, technology_intent=intent)
        assert resp.exact_total == 0, intent


def test_technology_across_availability_groups(db):
    """M. The same proven technology must correctly appear whichever
    availability tier the row is in - Stock Egypt / Stock OOE / unknown-market
    / RX - no false Stock qualification introduced by the technology gate."""
    co = _mk_company(db, "HOYA")
    cat = _mk_catalog(db, co)
    coating = _mk_coating(db, "Long Life Blue Control")
    for market, design_variant in (("Egypt", "eg-line"),
                                    ("Out Of Egypt", "ooe-line"),
                                    (None, "unknown-line")):
        m = _mk_model(db, co, f"Hilux-{design_variant}", schemas.LensCategory.SINGLE_VISION)
        v = _mk_variant(db, m, design_variant=design_variant)
        vp = models.VariantPricing(variant_id=v.id, coating_id=coating.id,
                                    availability=models.PricingAvailability.STOCK,
                                    price_pair=Decimal("1000"), currency="EGP",
                                    source_catalog_id=cat.id, market_scope=market)
        db.add(vp); db.commit(); db.refresh(vp)
        _mk_range(db, m, v, vp, sph_min=-3.0, sph_max=0.0)
    # RX route too, same proven coating
    m_rx = _mk_model(db, co, "Hilux-rx", schemas.LensCategory.SINGLE_VISION)
    v_rx = _mk_variant(db, m_rx, design_variant="rx-line")
    vp_rx = models.VariantPricing(variant_id=v_rx.id, coating_id=coating.id,
                                   availability=models.PricingAvailability.RX,
                                   price_pair=Decimal("1000"), currency="EGP", source_catalog_id=cat.id)
    db.add(vp_rx); db.commit(); db.refresh(vp_rx)
    _mk_range(db, m_rx, v_rx, vp_rx, sph_min=-3.0, sph_max=0.0)

    presc = _tech_presc(db)
    resp = _search(db, presc, technology_intent="blue_light")
    got_groups = {g.key for g in resp.groups if g.count > 0}
    assert got_groups == {"stock_egypt", "stock_out_of_egypt", "stock_market_unknown", "rx"}


def test_targeted_technology_intent_strict_and_with_other_filters(db):
    """technology_intent must combine as strict AND with existing targeted
    filters (e.g. Company + Index), never silently relaxed."""
    co, m, v, vp = _stock_product(db, "HOYA", "Hilux", schemas.LensCategory.SINGLE_VISION,
                                   sph_min=-3.0, sph_max=0.0, coating_code="Long Life Blue Control",
                                   price=1500)
    _stock_product(db, "HOYA", "OtherModel", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-3.0, sph_max=0.0, coating_code="Long Life Blue Control")
    presc = _tech_presc(db)
    req = schemas.ProductSearchRequest(
        mode="targeted", technology_intent="blue_light",
        filters=schemas.LensFilters(company_id=co.id, lens_model_id=m.id))
    resp = product_search.search(db, presc, req)
    assert resp.exact_total == 1
    assert resp.groups[0].results[0].model_name == "Hilux"


# ============================================================ TYPE B: ADD-ON
# Add-on fixtures use exact catalog identities; surcharge units stay unresolved.

def test_addon_blue_completes_rx_row_with_pending_unit(db):
    """B. A Maxxee RX row with a plain (non-blue) coating must be completed by
    the Blue HMC+ add-on: amount is known, but its unit requires confirmation."""
    co, m, v, vp = _rx_product(db, "Maxxee", "Maxxee", schemas.LensCategory.SINGLE_VISION,
                                sph_min=-3.0, sph_max=0.0, coating_code="H.M.C", price=9450, market_scope="Out Of Egypt")
    presc = _tech_presc(db)
    resp = _search(db, presc, technology_intent="blue_light")
    assert resp.exact_total == 1
    r = resp.best_match
    pf = r.pair_fulfillment
    assert pf.status == "rx"
    assert pf.technology_addon is not None
    assert pf.technology_addon.label == "Blue HMC+"
    assert pf.technology_addon.base_price == Decimal("9450")
    assert pf.technology_addon.addon_price == Decimal("1300")
    assert pf.price_pair is None  # printed amount does not prove the unit
    assert pf.price_confirmation_note
    assert pf.technology_addon.unit_status == "UNIT_UNRESOLVED"


def test_addon_blue_never_applied_to_stock_route(db):
    """L/9. The SAME Maxxee identity's Stock route (if any) must NEVER be
    upgraded by the RX-only add-on - Stock stays Stock, unavailable for the
    add-on route, never silently reclassified."""
    co = _mk_company(db, "Maxxee")
    cat = _mk_catalog(db, co)
    m = _mk_model(db, co, "Basic", schemas.LensCategory.SINGLE_VISION)
    v = _mk_variant(db, m, treatment_band=None)  # plain coating-less variant, no blue evidence
    coating = _mk_coating(db, "H.M.C")
    vp_stock = _mk_pricing(db, v, cat, availability=models.PricingAvailability.STOCK,
                            price=700, coating=coating, market_scope="Egypt")
    _mk_range(db, m, v, vp_stock, sph_min=-3.0, sph_max=0.0)
    presc = _tech_presc(db)
    resp = _search(db, presc, technology_intent="blue_light")
    assert resp.exact_total == 0  # Stock-only identity has no rx route -> no addon possible


def test_addon_applicability_scope_rejects_unregistered_company(db):
    """C. An add-on with no proven scope must never be invented - a SEIKO RX
    row with a plain coating (no registered SEIKO add-on exists at all) stays
    excluded. (PIXEL's own "Astro" coating is a separate, DIFFERENT negative
    case - see test_pixel_astro_plain_coating_not_blue_light below - now that
    pixel_phase4_test.pdf proves PIXEL's Blue Cut Coating IS a genuine RX
    add-on; "Astro" itself just isn't blue-light evidence.)"""
    _rx_product(db, "SEIKO", "Plain", schemas.LensCategory.SINGLE_VISION,
                sph_min=-3.0, sph_max=0.0, coating_code="SCC", price=5000)
    presc = _tech_presc(db)
    resp = _search(db, presc, technology_intent="blue_light")
    assert resp.exact_total == 0


def test_pixel_astro_plain_coating_not_blue_light_but_addon_completes_it(db):
    """RECONCILIATION: PIXEL's bare "Astro" coating is proven NOT blue-light
    (pixel_phase4_test.pdf p.6 describes it as anti-reflective/hydrophobic
    only), but the SAME row IS completed via the proven "Blue Cut Coating"
    RX add-on (p.16) - Type A fails, Type B succeeds."""
    _, _, v, vp = _rx_product(db, "Pixel", "Pixel", schemas.LensCategory.SINGLE_VISION,
                sph_min=-3.0, sph_max=0.0, coating_code="Astro", color_variant="Clear", price=5000)
    v.design_variant, vp.market_scope = "Free Form", "Out Of Egypt"
    db.commit()
    presc = _tech_presc(db)
    resp = _search(db, presc, technology_intent="blue_light")
    assert resp.exact_total == 1
    pf = resp.best_match.pair_fulfillment
    assert pf.technology_addon is not None
    assert pf.technology_addon.label == "Blue Cut Coating"
    assert pf.price_pair is None  # unit and Hi Power both need confirmation
    assert pf.price_confirmation_note


def test_pixel_astro_plus_coating_is_included_blue_light(db):
    """RECONCILIATION: PIXEL's "Astro+"/"Astro+B" coatings are explicitly,
    textually proven blue-light (Type A, p.7) - no add-on needed."""
    _rx_product(db, "Pixel", "AstroPlus", schemas.LensCategory.SINGLE_VISION,
                sph_min=-3.0, sph_max=0.0, coating_code="Astro+", price=5000)
    _rx_product(db, "Pixel", "AstroPlusB", schemas.LensCategory.SINGLE_VISION,
                sph_min=-3.0, sph_max=0.0, coating_code="Astro+B", price=6000)
    presc = _tech_presc(db)
    resp = _search(db, presc, technology_intent="blue_light")
    assert resp.exact_total == 2
    for grp in resp.groups:
        for r in grp.results:
            assert r.pair_fulfillment.technology_addon is None  # Type A, no addon


def test_hoya_sensity2_proves_photo_gray_and_photo_brown(db):
    """RECONCILIATION: HOYA "Sensity 2" (color_variant) is explicitly printed
    as "( Gray - Brown - Green )"/"( Gray - Brown - Green - Blue )" at ONE
    price per index (Hoya_Price_List_2025.pdf pp.7/10) - proves BOTH colours
    Type A, on the SAME row."""
    _rx_product(db, "HOYA", "Hilux", schemas.LensCategory.SINGLE_VISION,
                sph_min=-3.0, sph_max=0.0, coating_code="Long Life UV Control",
                color_variant="Sensity 2", price=10150)
    presc = _tech_presc(db)
    resp = _search(db, presc, technology_intent="photo_gray")
    assert resp.exact_total == 1
    resp2 = _search(db, presc, technology_intent="photo_brown")
    assert resp2.exact_total == 1


def test_hoya_sensity_original_does_not_prove_blue_light(db):
    """Sensity is a COLOUR/photochromic line, never blue-light protection by
    itself - a Sensity Original row without a blue-light coating must not
    satisfy blue_light. Its prerequisite Sensity 2 upgrade is not safely
    composable, so BLC completion must fail closed."""
    _rx_product(db, "HOYA", "Nulux", schemas.LensCategory.SINGLE_VISION,
                sph_min=-3.0, sph_max=0.0, coating_code="Super Hi Vision",
                color_variant="Sensity Original", price=15550)
    presc = _tech_presc(db)
    resp = _search(db, presc, technology_intent="blue_light")
    assert resp.exact_total == 0


def test_hoya_blc_addon_proven_index_specific(db):
    """HOYA's BLC add-on (+1500) completes blue_light for a Sensity 2 row at
    a proven identity (1.6), but rejects an unrelated model/index identity.
    This is not a manufacturer-wide exclusion of index 1.53."""
    _rx_product(db, "HOYA", "Nulux iDENTITY", schemas.LensCategory.SINGLE_VISION,
                sph_min=-3.0, sph_max=0.0, coating_code="Long Life UV Control",
                color_variant="Sensity 2", price=22900, index_value=1.6, market_scope="Out Of Egypt")
    _rx_product(db, "HOYA", "Amplitude PNX", schemas.LensCategory.SINGLE_VISION,
                sph_min=-3.0, sph_max=0.0, coating_code="Hi Vision Aqua",
                color_variant="Sensity 2", price=17250, index_value=1.53)
    presc = _tech_presc(db)
    resp = _search(db, presc, technology_intent="blue_light")
    assert resp.exact_total == 1
    r = resp.best_match
    assert r.model_name == "Nulux iDENTITY"
    assert r.pair_fulfillment.technology_addon.addon_price == Decimal("1500")
    assert r.pair_fulfillment.price_pair is None  # BLC unit is unresolved
    assert r.pair_fulfillment.price_confirmation_note


def test_hoya_sensity2_blue_photo_gray_via_base_plus_blc(db):
    """A HOYA Sensity 2 row (photo_gray+photo_brown proven, Type A) completed
    to blue_photo_gray by the index-proven BLC add-on (Type B) - a genuine
    base+add-on combination recovery."""
    _rx_product(db, "HOYA", "Nulux iDENTITY", schemas.LensCategory.SINGLE_VISION,
                sph_min=-3.0, sph_max=0.0, coating_code="Long Life UV Control",
                color_variant="Sensity 2", price=22900, index_value=1.6, market_scope="Out Of Egypt")
    presc = _tech_presc(db)
    resp = _search(db, presc, technology_intent="blue_photo_gray")
    assert resp.exact_total == 1
    assert resp.best_match.pair_fulfillment.price_pair is None
    assert resp.best_match.pair_fulfillment.price_confirmation_note


def test_seiko_sensity2_proves_photo_gray_and_photo_brown_not_blueblock(db):
    """RECONCILIATION: SEIKO "SENSITY 2" (treatment_band) explicitly names
    Green/Brown/Grey/Blue as colours of ONE line (Seiko_Pricelist_2025.pdf
    p.4) - proves both tracked colours; "Sensity 2 Blue" is a colour, never
    confused with the separately-priced BLUEBLOCK coating."""
    _rx_product(db, "SEIKO", "SEIKO", schemas.LensCategory.SINGLE_VISION,
                sph_min=-3.0, sph_max=0.0, treatment_band="SENSITY 2", price=15390)
    presc = _tech_presc(db)
    assert _search(db, presc, technology_intent="photo_gray").exact_total == 1
    assert _search(db, presc, technology_intent="photo_brown").exact_total == 1
    assert _search(db, presc, technology_intent="blue_light").exact_total == 0  # no addon exists for SEIKO


def test_seiko_src_screen_proves_blue_light(db):
    """RECONCILIATION (Seiko_Pricelist_2025.pdf p.5 "SEIKO COATINGS &
    EXCEPTION"): the marketing paragraph printed under the "SRC SCREEN" price
    row explicitly claims reduced eye strain from screens AND exposure to
    blue light - a genuine blue-light claim, unlike SRC ONE/ROAD/ULTRA/SUN on
    the same page (anti-reflective/driver-glare/outdoor-contrast only). The
    DB stores this as coatings.name == "SRC - SCREEN" on Stock-only rows."""
    _stock_product(db, "SEIKO", "SEIKO", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-3.0, sph_max=0.0, coating_code="SRC - SCREEN", price=3037)
    presc = _tech_presc(db)
    resp = _search(db, presc, technology_intent="blue_light")
    assert resp.exact_total == 1
    assert resp.best_match.pair_fulfillment.price_pair == Decimal("3037")
    assert resp.best_match.pair_fulfillment.technology_addon is None  # Type A: base row already proves it


def test_seiko_src_screen_siblings_do_not_prove_blue_light(db):
    """Negative control for the SRC SCREEN fix: SRC ONE/ROAD/ULTRA/SUN and
    plain SCC must NOT be treated as blue-light just because they share the
    "SRC" family/page with SRC SCREEN - each has its own paragraph on
    Seiko_Pricelist_2025.pdf p.5 with no blue-light claim."""
    for coating_code in ("SRC - ONE", "SRC - ROAD", "SRC ULTRA", "SRC - SUN", "SCC"):
        _stock_product(db, "SEIKO", f"Model-{coating_code}", schemas.LensCategory.SINGLE_VISION,
                        sph_min=-3.0, sph_max=0.0, coating_code=coating_code, price=2000)
    resp = _search(db, _tech_presc(db), technology_intent="blue_light")
    assert resp.exact_total == 0


def test_pixel_transmatic_proves_photo_gray_and_photo_brown(db):
    """RECONCILED (owner-confirmed HAT fix, 2026-09-21 - supersedes the prior
    "stays ambiguous" assertion this test name used to make): PIXEL's
    "Transmatic" IS proven photochromic (p.11 descriptive text), and TR/
    Transition products across these catalogs are now confirmed available in
    Gray + Brown - an authoritative relationship, not a guess from "G"/"B".
    See technology_evidence.py's Pixel _EVIDENCE entries for the citation."""
    _rx_product(db, "Pixel", "Astro", schemas.LensCategory.SINGLE_VISION,
                sph_min=-3.0, sph_max=0.0, coating_code="Astro-tm",
                color_variant="Transmatic/G/B", price=8000)
    presc = _tech_presc(db)
    assert _search(db, presc, technology_intent="photo_gray").exact_total == 1
    assert _search(db, presc, technology_intent="photo_brown").exact_total == 1


def test_addon_cannot_complete_photo_intent(db):
    """No photochromic add-on exists in current catalog evidence for any
    manufacturer - a Maxxee RX row with a plain coating must never be offered
    for photo_gray/photo_brown via an invented add-on."""
    _rx_product(db, "Maxxee", "Maxxee", schemas.LensCategory.SINGLE_VISION,
                sph_min=-3.0, sph_max=0.0, coating_code="H.M.C", price=9450, market_scope="Out Of Egypt")
    for intent in ("photo_gray", "photo_brown", "blue_photo_gray", "blue_photo_brown"):
        resp = _search(db, _tech_presc(db), technology_intent=intent)
        assert resp.exact_total == 0, intent


def test_addon_incomplete_combo_rejected(db):
    """I. blue_photo_gray must NEVER be satisfied by Blue-via-addon alone -
    the combo also requires photochromic Gray, which no add-on can supply."""
    _rx_product(db, "Maxxee", "Maxxee", schemas.LensCategory.SINGLE_VISION,
                sph_min=-3.0, sph_max=0.0, coating_code="H.M.C", price=9450, market_scope="Out Of Egypt")
    resp = _search(db, _tech_presc(db), technology_intent="blue_photo_gray")
    assert resp.exact_total == 0


def test_addon_included_beats_addon_when_base_already_qualifies(db):
    """A base row that ALREADY includes the technology must never also carry
    an add-on breakdown - Type A stays Type A, price unchanged."""
    _rx_product(db, "Maxxee", "BlueBase", schemas.LensCategory.SINGLE_VISION,
                sph_min=-3.0, sph_max=0.0, coating_code="Blue U.V", price=9450)
    resp = _search(db, _tech_presc(db), technology_intent="blue_light")
    assert resp.exact_total == 1
    pf = resp.best_match.pair_fulfillment
    assert pf.technology_addon is None
    assert pf.price_pair == Decimal("9450")


def test_addon_availability_semantics_route_is_rx(db):
    """L/9. A Type-B result's own group/availability must be RX, never
    presented under Stock Egypt/OOE/unknown-market."""
    _rx_product(db, "Maxxee", "Maxxee", schemas.LensCategory.SINGLE_VISION,
                sph_min=-3.0, sph_max=0.0, coating_code="H.M.C", price=9450, market_scope="Out Of Egypt")
    resp = _search(db, _tech_presc(db), technology_intent="blue_light")
    rx_group = next(g for g in resp.groups if g.key == "rx")
    assert rx_group.count == 1
    for g in resp.groups:
        if g.key != "rx":
            assert g.count == 0


def test_addon_stock_powerrange_and_category_still_enforced(db):
    """M/N/O. Type-B fulfillment never bypasses Stock PowerRange, RX limits,
    or category boundaries - an out-of-range prescription and a wrong
    category must both still be correctly excluded."""
    _rx_product(db, "Maxxee", "Maxxee", schemas.LensCategory.SINGLE_VISION,
                sph_min=-3.0, sph_max=0.0, coating_code="H.M.C", price=9450, market_scope="Out Of Egypt")
    # out-of-range prescription for this RX row's (unbounded-by-range... but
    # RX rows with a PowerRange DO still enforce it) sph window
    out_of_range = _mk_presc(db, -20.0, -20.0, od_cyl=0.0, os_cyl=0.0)
    resp = _search(db, out_of_range, technology_intent="blue_light")
    assert resp.exact_total == 0
    # correct category boundary: use_mode=bifocal must still exclude this
    # single_vision identity even though it would otherwise qualify via addon
    resp2 = _search(db, _tech_presc(db), use_mode="bifocal", technology_intent="blue_light")
    assert resp2.exact_total == 0


# ================================================ OWNER-CONFIRMED BLUE MAPPINGS
# (owner-confirmed commercial-naming audit, 2026-09-22): DIVEL "Blue Natural"
# and PLATINUM "BLU STEEL" are each manufacturer's OWN commercial name for
# Blue Light Protection - the same evidentiary standard already used for
# every other manufacturer's own named term (BBGR "Blu stop", HOYA "Long Life
# Blue Control", Maxxee "Blue U.V", ...), not an inference from the word
# "Blue" alone. SCOPE's commercial "Relax" line name is the same kind of
# owner-confirmed relationship, extended here to the two "Transitions Relax
# PhotoGray(-Brown) Surface" rows that carry no "Blue" wording in their own
# printed name.

def test_divel_blue_natural_proves_blue_light(db):
    """DIVEL's "Blue Natural" coating is proven blue_light."""
    _stock_product(db, "DIVEL ITALIA", "DIVEL ITALIA", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    coating_code="Blue Natural", price=1300)
    presc = _hat_presc(db)
    resp = _search(db, presc, technology_intent="blue_light")
    assert resp.exact_total == 1
    assert resp.best_match.company_name == "DIVEL ITALIA"
    assert resp.best_match.pair_fulfillment.price_pair == Decimal("1300")


def test_divel_blue_natural_and_aria_blue_fotocolor_gr_both_present(db):
    """Blue Natural (pure BLUE_LIGHT) and Aria Blue FotoColor GR (BLUE_LIGHT +
    PHOTO_GRAY) are DISTINCT products and must both appear for a Blue-only
    search - never collapsed, never one excluding the other."""
    _stock_product(db, "DIVEL ITALIA", "DIVEL ITALIA", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    coating_code="Blue Natural", price=1300)
    _stock_product(db, "DIVEL ITALIA", "DIVEL ITALIA", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    coating_code="Aria Blue FotoColor GR", price=2150)
    presc = _hat_presc(db)
    resp = _search(db, presc, technology_intent="blue_light")
    assert resp.exact_total == 2
    prices = {r.pair_fulfillment.price_pair for grp in resp.groups for r in grp.results}
    assert prices == {Decimal("1300"), Decimal("2150")}
    # only Aria Blue FotoColor GR also satisfies blue_photo_gray
    resp_combo = _search(db, presc, technology_intent="blue_photo_gray")
    assert resp_combo.exact_total == 1
    assert resp_combo.best_match.pair_fulfillment.price_pair == Decimal("2150")


def test_platinum_blu_steel_proves_blue_light(db):
    """PLATINUM's "BLU STEEL" treatment_band is proven blue_light - mirrors
    the real DB's 1.56 Stock/Egypt row (price 600, sph -6/+4, cyl -2/0)."""
    _stock_product(db, "PLATINUM", "1.56 BLU STEEL", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-6.0, sph_max=4.0, cyl_min=-2.0, cyl_max=0.0,
                    treatment_band="BLU STEEL", price=600)
    presc = _hat_presc(db)
    resp = _search(db, presc, technology_intent="blue_light")
    assert resp.exact_total == 1
    assert resp.best_match.company_name == "PLATINUM"
    assert resp.best_match.pair_fulfillment.price_pair == Decimal("600")


def test_scope_relax_transitions_photogray_surface_now_proves_blue_light(db):
    """SCOPE "Transitions Relax PhotoGray Surface" carries no "Blue" wording
    of its own, but is a genuine SCOPE "Relax"-branded product - owner
    confirms Relax means Blue Light Protection company-wide, so this row must
    now prove blue_light IN ADDITION TO its already-proven photo_gray."""
    _stock_product(db, "SCOPE", "SCOPE", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    treatment_band="Transitions Relax PhotoGray Surface", price=1000)
    presc = _hat_presc(db)
    assert _search(db, presc, technology_intent="blue_light").exact_total == 1
    assert _search(db, presc, technology_intent="photo_gray").exact_total == 1
    assert _search(db, presc, technology_intent="blue_photo_gray").exact_total == 1
    assert _search(db, presc, technology_intent="photo_brown").exact_total == 0


def test_scope_relax_transitions_photogray_brown_surface_now_proves_blue_light(db):
    """Same rule, the Gray+Brown sibling row."""
    _stock_product(db, "SCOPE", "SCOPE", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    treatment_band="Transitions Relax PhotoGray-Brown Surface", price=1100)
    presc = _hat_presc(db)
    assert _search(db, presc, technology_intent="blue_light").exact_total == 1
    assert _search(db, presc, technology_intent="blue_photo_gray").exact_total == 1
    assert _search(db, presc, technology_intent="blue_photo_brown").exact_total == 1


def test_scope_relax_contrast_and_night_rider_remain_excluded(db):
    """Evidenced exception preserved: "Relax Blue+Yellow Light Contrast" and
    "Night Rider (Blue+Yellow Light, Day/Night Driving)" both contain "Relax"
    and/or "Blue" but are a DIFFERENT-purpose driving-contrast technology per
    the catalog's own text - the general "SCOPE Relax = Blue Light Protection"
    rule must NOT sweep these in. Proves the fix is exact-value evidence, not
    a "Relax"/"Blue" substring rule."""
    _stock_product(db, "SCOPE", "Contrast", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    treatment_band="Relax Blue+Yellow Light Contrast", price=1000)
    _stock_product(db, "SCOPE", "NightRider", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    treatment_band="Night Rider (Blue+Yellow Light, Day/Night Driving)", price=1200)
    presc = _hat_presc(db)
    resp = _search(db, presc, technology_intent="blue_light")
    assert resp.exact_total == 0


def test_owner_mapping_full_cross_manufacturer_matrix(db):
    """Every owner-confirmed company-specific Blue Light Protection commercial
    name is recognized where a corresponding catalog row exists - one Stock
    row per company, all eleven owner-confirmed mappings in a single search."""
    _stock_product(db, "BBGR", "BBGR", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    treatment_band="Blu stop", price=2700)
    _stock_product(db, "DIVEL ITALIA", "DIVEL ITALIA", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    coating_code="Blue Natural", price=1300)
    _stock_product(db, "HOYA", "Hilux", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    coating_code="Long Life Blue Control", price=3300)
    _stock_product(db, "Maxxee", "Maxxee", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    coating_code="Blue U.V", price=1250)
    _stock_product(db, "SEIKO", "SEIKO", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    coating_code="SRC - SCREEN", price=3037)
    _stock_product(db, "Synchrony", "Synchrony", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    treatment_band="Blue HMC+", price=2300)
    _stock_product(db, "PLATINUM", "1.56 BLU STEEL", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    treatment_band="BLU STEEL", price=600)
    _stock_product(db, "Pixel", "Pixel", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    coating_code="Astro+", color_variant="Clear", price=1100)
    _stock_product(db, "Pixel", "Pixel", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    coating_code="Astro+B", color_variant="Clear", price=1300)
    _stock_product(db, "ZEISS", "ClearView FSV", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    treatment_band="BlueGuard", price=4940)
    _stock_product(db, "SCOPE", "SCOPE", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    treatment_band="Relax Blue Light", price=1500)
    _stock_product(db, "VISALL", "1.56 BlueCut", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    treatment_band="BlueCut", price=1300)
    presc = _hat_presc(db)
    resp = _search(db, presc, technology_intent="blue_light")
    companies = {r.company_name for grp in resp.groups for r in grp.results}
    assert companies == {"BBGR", "DIVEL ITALIA", "HOYA", "Maxxee", "SEIKO", "Synchrony",
                          "PLATINUM", "Pixel", "ZEISS", "SCOPE", "VISALL"}
    assert resp.exact_total == 12  # 11 companies, Pixel contributes 2 rows


def test_owner_mapping_false_positive_guard(db):
    """False-positive guard: generic values merely containing "Blue"/"Screen"/
    "Relax" with NO company-specific evidence entry must never be classified
    blue_light - proves the fix added exact-value entries, not substring
    matching on any of these words."""
    _stock_product(db, "BBGR", "Neva blu", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, coating_code="Neva blu", price=2400)
    _stock_product(db, "DIVEL ITALIA", "Sun Blue", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, coating_code="Sun Lenses",
                    color_variant="Gray/Brown/G15/Blue", price=900)
    _stock_product(db, "PlainCo", "ScreenCo", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, coating_code="Screen Protector", price=1000)
    _stock_product(db, "PlainCo", "RelaxCo", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, treatment_band="Relax Comfort Plus", price=1000)
    resp = _search(db, _hat_presc(db), technology_intent="blue_light")
    assert resp.exact_total == 0


def test_price_ordering_already_prefers_exact_capability_match(db):
    """Presentation-preference check (Section 3/9): within the same
    availability/index tier, when a pure {BLUE_LIGHT} product is CHEAPER than
    a {BLUE_LIGHT, PHOTO_GRAY} combination product - exactly the real DB's
    1.56/Stock/Egypt shape (BLU STEEL 600 < ... < Aria Blue FotoColor GR
    2150, the only combo option, also the most expensive) - the EXISTING
    price-ascending sort key already places the exact match first, with no
    dedicated capability-exactness ranking dimension needed. This test
    documents why no ordering/ranking code was added for this fix."""
    _stock_product(db, "PLATINUM", "1.56 BLU STEEL", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-6.0, sph_max=4.0, cyl_min=-2.0, cyl_max=0.0,
                    treatment_band="BLU STEEL", price=600)
    _stock_product(db, "DIVEL ITALIA", "DIVEL ITALIA", schemas.LensCategory.SINGLE_VISION,
                    sph_min=-4.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0,
                    coating_code="Aria Blue FotoColor GR", price=2150)
    presc = _hat_presc(db)
    resp = _search(db, presc, technology_intent="blue_light")
    assert resp.exact_total == 2
    ordered_prices = [r.pair_fulfillment.price_pair for grp in resp.groups for r in grp.results]
    assert ordered_prices == [Decimal("600"), Decimal("2150")]
    assert resp.best_match.pair_fulfillment.price_pair == Decimal("600")
