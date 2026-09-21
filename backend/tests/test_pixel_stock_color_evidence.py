"""Permanent regression coverage for the PIXEL Stock Out Of Egypt "Finished,
Single Vision, Out Of Egypt" color-attribute correction (owner-supplied
catalog evidence, HAT catalog-gap reconciliation, 2026-09-21).

The two corrected identities (index 1.50/"Astro" and 1.56/"Astro+B") already
had fully correct price/PowerRange/coating/index/availability before this
correction - only LensVariant.color_variant was NULL. This suite exercises
the reconciliation module (app/pixel_stock_color_evidence.py) directly via a
synthetic in-memory DB shaped exactly like the real pre-fix data, then
confirms the corrected rows behave correctly through the real search path.
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
from app import models, database, schemas, product_search, pixel_stock_color_evidence as ev  # noqa: E402


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


def _mk_coating(db, code):
    c = models.Coating(code=code, name=code)
    db.add(c); db.commit(); db.refresh(c)
    return c


def _mk_pixel_stock_setup(db):
    """Mirrors the real pre-correction release_runtime.db shape exactly:
    both target variants exist, fully priced with real positive/negative
    PowerRange bands, coating, index and availability all already correct -
    only color_variant is NULL, matching what the original import left."""
    co = models.Company(name="Pixel", country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename="synthetic.pdf", file_path="synthetic.pdf",
                         status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)
    model = models.LensModel(company_id=co.id, name="Pixel", category=models.LensCategory.SINGLE_VISION)
    db.add(model); db.commit(); db.refresh(model)
    astro = _mk_coating(db, "Astro")
    astro_b = _mk_coating(db, "Astro+B")

    def _stock_variant(index_value, design_type, is_aspherical, coating, price, sph_min, sph_max):
        v = models.LensVariant(lens_model_id=model.id, material=models.MaterialType.CR39,
                               index_value=index_value, design_type=design_type,
                               is_aspherical=is_aspherical, price=0.0, currency="EGP")
        db.add(v); db.commit(); db.refresh(v)
        vp = models.VariantPricing(variant_id=v.id, coating_id=coating.id,
                                   availability=models.PricingAvailability.STOCK,
                                   price_pair=Decimal(str(price)), currency="EGP",
                                   source_catalog_id=cat.id, market_scope="Out Of Egypt",
                                   power_scope="negative")
        db.add(vp); db.commit(); db.refresh(vp)
        pr = models.PowerRange(lens_model_id=model.id, variant_id=v.id, pricing_id=vp.id,
                               sph_min=sph_min, sph_max=sph_max, cyl_min=-2.0, cyl_max=0.0)
        db.add(pr); db.commit()
        return v

    v150 = _stock_variant(1.50, models.DesignType.SPHERICAL, False, astro, 3500, -4.0, 0.0)
    _stock_variant_extra_band(db, v150, cat, astro, 3500, 0.0, 4.0)
    v156 = _stock_variant(1.56, models.DesignType.ASPHERICAL, True, astro_b, 5000, -4.0, 0.0)
    _stock_variant_extra_band(db, v156, cat, astro_b, 5000, 0.0, 4.0)
    return {"company": co, "model": model, "v150": v150, "v156": v156}


def _stock_variant_extra_band(db, variant, cat, coating, price, sph_min, sph_max):
    """The SAME variant's second (positive) commercial pricing band, mirroring
    the project's existing positive/negative VariantPricing representation
    (distinct power_scope keeps both current rows valid under
    uq_variant_pricing_current, exactly as the real data already does)."""
    vp = models.VariantPricing(variant_id=variant.id, coating_id=coating.id,
                               availability=models.PricingAvailability.STOCK,
                               price_pair=Decimal(str(price)), currency="EGP",
                               source_catalog_id=cat.id, market_scope="Out Of Egypt",
                               power_scope="positive")
    db.add(vp); db.commit(); db.refresh(vp)
    pr = models.PowerRange(lens_model_id=variant.lens_model_id, variant_id=variant.id, pricing_id=vp.id,
                           sph_min=sph_min, sph_max=sph_max, cyl_min=-2.0, cyl_max=0.0)
    db.add(pr); db.commit()


def _hat_presc(db):
    p = models.Prescription(
        customer_name="hat", od_sph_original=-2.0, od_cyl_original=-1.0, od_axis_original=90,
        od_sph=-2.0, od_cyl=-1.0, od_axis=90, os_sph_original=-2.0, os_cyl_original=-1.0,
        os_axis_original=90, os_sph=-2.0, os_cyl=-1.0, os_axis=90, pd=63)
    db.add(p); db.commit(); db.refresh(p)
    return p


def test_1_2_reconcile_sets_color_on_exactly_the_two_target_variants(db):
    setup = _mk_pixel_stock_setup(db)
    assert setup["v150"].color_variant is None
    assert setup["v156"].color_variant is None
    changed = ev.reconcile_pixel_stock_transmatic_colors(db)
    assert changed == 2
    db.refresh(setup["v150"]); db.refresh(setup["v156"])
    assert setup["v150"].color_variant == "Transmatic/B/G"
    assert setup["v156"].color_variant == "Transmatic/B/G"


def test_3_hat_prescription_is_inside_both_stored_ranges(db):
    setup = _mk_pixel_stock_setup(db)
    ev.reconcile_pixel_stock_transmatic_colors(db)
    presc = _hat_presc(db)
    req = schemas.ProductSearchRequest(mode="automatic", use_mode="distance", customer_needs=["photo_brown"])
    resp = product_search.search(db, presc, req)
    pixel_indexes = {r.index_value for g in resp.groups for r in g.results if r.company_name == "Pixel"}
    assert pixel_indexes == {1.50, 1.56}


def test_4_photo_brown_returns_both_corrected_rows(db):
    setup = _mk_pixel_stock_setup(db)
    ev.reconcile_pixel_stock_transmatic_colors(db)
    presc = _hat_presc(db)
    req = schemas.ProductSearchRequest(mode="automatic", use_mode="distance", customer_needs=["photo_brown"])
    resp = product_search.search(db, presc, req)
    prices = sorted(float(r.pair_fulfillment.price_pair) for g in resp.groups for r in g.results
                     if r.company_name == "Pixel")
    assert prices == [3500.0, 5000.0]


def test_5_photo_gray_returns_both_corrected_rows(db):
    setup = _mk_pixel_stock_setup(db)
    ev.reconcile_pixel_stock_transmatic_colors(db)
    presc = _hat_presc(db)
    req = schemas.ProductSearchRequest(mode="automatic", use_mode="distance", customer_needs=["photo_gray"])
    resp = product_search.search(db, presc, req)
    prices = sorted(float(r.pair_fulfillment.price_pair) for g in resp.groups for r in g.results
                     if r.company_name == "Pixel")
    assert prices == [3500.0, 5000.0]


def test_6_rows_stay_stock_out_of_egypt_never_rx(db):
    setup = _mk_pixel_stock_setup(db)
    ev.reconcile_pixel_stock_transmatic_colors(db)
    presc = _hat_presc(db)
    req = schemas.ProductSearchRequest(mode="automatic", use_mode="distance", customer_needs=["photo_brown"])
    resp = product_search.search(db, presc, req)
    pixel_rows = [r for g in resp.groups for r in g.results if r.company_name == "Pixel"]
    assert len(pixel_rows) == 2
    for r in pixel_rows:
        assert r.pair_fulfillment.status == "stock_outside"
    assert resp.rx_count == 0


def test_7_pair_prices_remain_3500_and_5000(db):
    setup = _mk_pixel_stock_setup(db)
    ev.reconcile_pixel_stock_transmatic_colors(db)
    prices = {vp.price_pair for vp in setup["v150"].pricing_records} | {vp.price_pair for vp in setup["v156"].pricing_records}
    assert prices == {Decimal("3500.00"), Decimal("5000.00")}


def test_8_stock_over_rx_still_suppresses_rx_when_stock_actionable(db):
    """A cheaper actionable Stock Egypt alternative must still suppress every
    RX candidate for this distance search - unrelated to this correction,
    reasserted here so the new Pixel rows cannot accidentally interact with
    it."""
    setup = _mk_pixel_stock_setup(db)
    ev.reconcile_pixel_stock_transmatic_colors(db)
    co2 = models.Company(name="VISALL", country="EG", is_active=True, is_deleted=False)
    db.add(co2); db.commit(); db.refresh(co2)
    cat2 = models.Catalog(company_id=co2.id, filename="s2.pdf", file_path="s2.pdf",
                          status=models.CatalogStatus.DRAFT)
    db.add(cat2); db.commit(); db.refresh(cat2)
    m2 = models.LensModel(company_id=co2.id, name="Photo Gray & Brown", category=models.LensCategory.SINGLE_VISION)
    db.add(m2); db.commit(); db.refresh(m2)
    v2 = models.LensVariant(lens_model_id=m2.id, material=models.MaterialType.CR39, index_value=1.56,
                            design_type=models.DesignType.SPHERICAL, is_aspherical=False,
                            treatment_band="Photochromic", color_variant="Gray / Brown", price=0.0, currency="EGP")
    db.add(v2); db.commit(); db.refresh(v2)
    vp2 = models.VariantPricing(variant_id=v2.id, availability=models.PricingAvailability.STOCK,
                                price_pair=Decimal("1300"), currency="EGP", source_catalog_id=cat2.id,
                                market_scope="Egypt")
    db.add(vp2); db.commit(); db.refresh(vp2)
    pr2 = models.PowerRange(lens_model_id=m2.id, variant_id=v2.id, pricing_id=vp2.id,
                            sph_min=-6.0, sph_max=4.0, cyl_min=-3.0, cyl_max=0.0)
    db.add(pr2); db.commit()

    presc = _hat_presc(db)
    req = schemas.ProductSearchRequest(mode="automatic", use_mode="distance", customer_needs=["photo_brown"])
    resp = product_search.search(db, presc, req)
    assert resp.rx_count == 0
    assert resp.stock_egypt_count == 1
    assert resp.stock_out_of_egypt_count == 2


def test_9_strict_and_unaffected_1_50_astro_alone_fails_blue_photo_brown(db):
    """Strict AND preserved: the 1.50/"Astro" row (plain coating, no blue-
    light evidence - unlike "Astro+B", already proven BLUE_LIGHT elsewhere in
    technology_evidence.py) proves photo_brown alone but must still fail
    blue_photo_brown. Scoped to index 1.50 only so the 1.56/"Astro+B" row
    (which legitimately DOES combine blue_light + photo_brown on one row,
    and must keep doing so) cannot supply a false pass."""
    setup = _mk_pixel_stock_setup(db)
    ev.reconcile_pixel_stock_transmatic_colors(db)
    presc = _hat_presc(db)
    req = schemas.ProductSearchRequest(mode="targeted", use_mode="distance",
                                       technology_intent="blue_photo_brown",
                                       filters=schemas.LensFilters(lens_model_id=setup["model"].id, index_value=1.50))
    resp = product_search.search(db, presc, req)
    assert resp.exact_total == 0


def test_10_repeat_reconcile_never_duplicates_or_errors(db):
    setup = _mk_pixel_stock_setup(db)
    first = ev.reconcile_pixel_stock_transmatic_colors(db)
    second = ev.reconcile_pixel_stock_transmatic_colors(db)
    third = ev.reconcile_pixel_stock_transmatic_colors(db)
    assert (first, second, third) == (2, 0, 0)
    variants = db.query(models.LensVariant).filter(
        models.LensVariant.lens_model_id == setup["model"].id).all()
    assert len(variants) == 2  # no new variant created by any repeat run


def test_11_reconcile_refuses_to_guess_when_shape_unexpected(db):
    """Safety companion: if the expected uncoloured/pre-matched shape is not
    found (e.g. a future re-import already assigned a different color), the
    module must raise rather than silently touching the wrong row."""
    co = models.Company(name="Pixel", country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    # no Single Vision model/variant at all -> reconcile must raise, not no-op silently
    with pytest.raises(RuntimeError):
        ev.reconcile_pixel_stock_transmatic_colors(db)
