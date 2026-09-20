"""ZEISS Office Lenses ingestion (Special Lenses architecture, owner-
confirmed 2026-09-19/20/21) - see app/zeiss_office_evidence.py's own module
docstring for the full position-based extraction citation
(ZEISS_Main_Catalog.pdf pp.33-34) and the ADD-eligibility owner decision
(2026-09-21): ZEISS Office is ADD-aware (missing ADD => ineligible, entered
ADD must sit inside the row's own printed range) while HOYA/SCOPE Office -
which prove no ADD corridor at all - stay exactly as ADD-neutral as before.

Deliberately synthetic (mirrors test_zeiss_myopia_control_evidence.py's own
pattern) - no PDF parsing, no dependency on the live release_runtime.db; the
live db result is verified separately.
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
from app import zeiss_office_evidence as zoe  # noqa: E402

from test_use_mode_technology import _mk_presc  # noqa: E402


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    event.listen(engine, "connect", database._set_sqlite_pragma)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _mk_zeiss_company(db):
    co = models.Company(name="ZEISS", country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    return co


# ------------------------------------------------------------- reconcile: identity/structure
def test_reconcile_creates_one_office_model_with_three_design_tiers(db):
    _mk_zeiss_company(db)
    result = zoe.reconcile(db)
    assert result["created"] > 0
    models_ = db.query(models.LensModel).filter(models.LensModel.name == "Office").all()
    assert len(models_) == 1
    model = models_[0]
    assert model.category == models.LensCategory.OFFICE
    tiers = {v.design_tier for v in
             db.query(models.LensVariant).filter(models.LensVariant.lens_model_id == model.id).all()}
    assert tiers == {"Individual", "Superb", "Plus"}


def test_reconcile_never_touches_unrelated_zeiss_models(db):
    co = _mk_zeiss_company(db)
    other = models.LensModel(company_id=co.id, name="MyoCare", category=models.LensCategory.MYOPIA_CONTROL)
    db.add(other); db.commit(); db.refresh(other)
    zoe.reconcile(db)
    db.refresh(other)
    assert other.category == models.LensCategory.MYOPIA_CONTROL
    assert db.query(models.LensModel).filter(models.LensModel.company_id == co.id).count() == 2


def test_reconcile_is_idempotent(db):
    _mk_zeiss_company(db)
    result1 = zoe.reconcile(db)
    result2 = zoe.reconcile(db)
    assert result1["created"] > 0
    assert result2["created"] == 0


# ------------------------------------------------------------- reconcile: exact price cells
def _pricing_row(db, model, index_value, design_tier, treatment_band, coating_code):
    v = (db.query(models.LensVariant)
         .filter(models.LensVariant.lens_model_id == model.id,
                 models.LensVariant.index_value == index_value,
                 models.LensVariant.design_tier == design_tier,
                 models.LensVariant.treatment_band == treatment_band)
         .first())
    assert v is not None, f"variant missing: {index_value}/{design_tier}/{treatment_band}"
    coating = db.query(models.Coating).filter(models.Coating.code == coating_code).first()
    assert coating is not None, f"coating missing: {coating_code}"
    return (db.query(models.VariantPricing)
            .filter(models.VariantPricing.variant_id == v.id,
                    models.VariantPricing.coating_id == coating.id)
            .first())


@pytest.mark.parametrize("tier,band,coating,index_value,expected", [
    ("Individual", "Clear", "DuraVision Plus Gold", 1.5, "14900"),
    ("Individual", "Clear", "DuraVision Plus Gold", 1.74, "26600"),
    ("Superb", "BlueGuard", "DuraVision Plus Platinum", 1.67, "21200"),
    ("Plus", "Tinted", "DuraVision Plus Sun", 1.6, "13400"),
    ("Plus", "PhotoFusion X", "DuraVision Plus Chrome", 1.5, "17200"),
])
def test_reconcile_preserves_exact_price_cells(db, tier, band, coating, index_value, expected):
    _mk_zeiss_company(db)
    zoe.reconcile(db)
    model = db.query(models.LensModel).filter(models.LensModel.name == "Office").first()
    vp = _pricing_row(db, model, index_value, tier, band, coating)
    assert vp is not None
    assert vp.price_pair == Decimal(expected)


def _pricing_row_or_none(db, model, index_value, design_tier, treatment_band, coating_code):
    """Same lookup as _pricing_row, but tolerates a missing LensVariant - a
    completely dashed (tier, treatment_band, index) combination legitimately
    never gets a variant created at all (no coating in that band ever prices
    that index), which is even stronger evidence of "no fabricated price"
    than a variant existing with zero pricing rows."""
    v = (db.query(models.LensVariant)
         .filter(models.LensVariant.lens_model_id == model.id,
                 models.LensVariant.index_value == index_value,
                 models.LensVariant.design_tier == design_tier,
                 models.LensVariant.treatment_band == treatment_band)
         .first())
    if v is None:
        return None
    coating = db.query(models.Coating).filter(models.Coating.code == coating_code).first()
    if coating is None:
        return None
    return (db.query(models.VariantPricing)
            .filter(models.VariantPricing.variant_id == v.id,
                    models.VariantPricing.coating_id == coating.id)
            .first())


@pytest.mark.parametrize("tier,band,coating,index_value", [
    ("Individual", "PhotoFusion X", "DuraVision Plus Gold", 1.53),   # dashed on every tier
    ("Individual", "Tinted", "DuraVision Plus Gold", 1.53),
    ("Individual", "Tinted", "DuraVision Plus Gold", 1.74),          # Tinted dashed at 1.74 too
    ("Individual", "PhotoFusion X", "DuraVision Plus Flash", 1.74),  # Flash dashed at 1.74
])
def test_reconcile_never_fabricates_a_dashed_price_cell(db, tier, band, coating, index_value):
    _mk_zeiss_company(db)
    zoe.reconcile(db)
    model = db.query(models.LensModel).filter(models.LensModel.name == "Office").first()
    vp = _pricing_row_or_none(db, model, index_value, tier, band, coating)
    assert vp is None


# ------------------------------------------------------------- reconcile: material / availability
def test_reconcile_1_53_is_trivex_not_cr39(db):
    _mk_zeiss_company(db)
    zoe.reconcile(db)
    model = db.query(models.LensModel).filter(models.LensModel.name == "Office").first()
    variants = (db.query(models.LensVariant)
                .filter(models.LensVariant.lens_model_id == model.id, models.LensVariant.index_value == 1.53)
                .all())
    assert variants
    assert all(v.material == models.MaterialType.TRIVEX for v in variants)


def test_reconcile_other_indexes_stay_cr39(db):
    _mk_zeiss_company(db)
    zoe.reconcile(db)
    model = db.query(models.LensModel).filter(models.LensModel.name == "Office").first()
    variants = (db.query(models.LensVariant)
                .filter(models.LensVariant.lens_model_id == model.id, models.LensVariant.index_value != 1.53)
                .all())
    assert variants
    assert all(v.material == models.MaterialType.CR39 for v in variants)


def test_reconcile_availability_is_rx_and_market_scope_none(db):
    _mk_zeiss_company(db)
    zoe.reconcile(db)
    model = db.query(models.LensModel).filter(models.LensModel.name == "Office").first()
    variant_ids = [v.id for v in
                   db.query(models.LensVariant).filter(models.LensVariant.lens_model_id == model.id).all()]
    pricing = (db.query(models.VariantPricing)
               .filter(models.VariantPricing.variant_id.in_(variant_ids)).all())
    assert pricing
    assert all(p.availability == models.PricingAvailability.RX for p in pricing)
    assert all(p.market_scope is None for p in pricing)


# ------------------------------------------------------------- reconcile: PowerRange bounds
def test_reconcile_1_67_has_three_diameter_zones(db):
    _mk_zeiss_company(db)
    zoe.reconcile(db)
    model = db.query(models.LensModel).filter(models.LensModel.name == "Office").first()
    vp = _pricing_row(db, model, 1.67, "Individual", "Clear", "DuraVision Plus Gold")
    ranges = db.query(models.PowerRange).filter(models.PowerRange.pricing_id == vp.id).all()
    assert len(ranges) == 3
    bounds = sorted((r.total_power_min, r.total_power_max, r.max_cyl_abs) for r in ranges)
    assert bounds == sorted([(-10.00, 6.00, 4.00), (-10.00, 8.00, 4.00), (-12.00, 8.00, 6.00)])


def test_reconcile_1_6_has_two_diameter_zones_with_add_0_75_to_4_00(db):
    _mk_zeiss_company(db)
    zoe.reconcile(db)
    model = db.query(models.LensModel).filter(models.LensModel.name == "Office").first()
    vp = _pricing_row(db, model, 1.6, "Individual", "Clear", "DuraVision Plus Gold")
    ranges = db.query(models.PowerRange).filter(models.PowerRange.pricing_id == vp.id).all()
    assert len(ranges) == 2
    for r in ranges:
        assert r.add_min == 0.75
        assert r.add_max == 4.00


@pytest.mark.parametrize("index_value", [1.5, 1.53, 1.67, 1.74])
def test_reconcile_every_other_index_keeps_add_0_75_to_3_50(db, index_value):
    _mk_zeiss_company(db)
    zoe.reconcile(db)
    model = db.query(models.LensModel).filter(models.LensModel.name == "Office").first()
    vp = _pricing_row(db, model, index_value, "Individual", "Clear", "DuraVision Plus Gold")
    ranges = db.query(models.PowerRange).filter(models.PowerRange.pricing_id == vp.id).all()
    assert ranges
    for r in ranges:
        assert r.add_min == 0.75
        assert r.add_max == 3.50


# ------------------------------------------------------------- search: ADD eligibility (owner rule)
def _mk_office_row(db, index_value, add_min, add_max, total_power_min=-30.0, total_power_max=30.0,
                    max_cyl_abs=10.0, price=15000, model_name="Office", coating_name="Test Coating"):
    co = models.Company(name="ZEISS", country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename="z.pdf", file_path="z.pdf",
                         status=models.CatalogStatus.CONFIRMED)
    db.add(cat); db.commit(); db.refresh(cat)
    m = models.LensModel(company_id=co.id, name=model_name, category=models.LensCategory.OFFICE)
    db.add(m); db.commit(); db.refresh(m)
    v = models.LensVariant(lens_model_id=m.id, material=models.MaterialType.CR39, index_value=index_value,
                           design_type=models.DesignType.SPHERICAL, is_aspherical=False,
                           design_tier="Individual", treatment_band="Clear", price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    coating = models.Coating(code=coating_name, name=coating_name)
    db.add(coating); db.commit(); db.refresh(coating)
    vp = models.VariantPricing(variant_id=v.id, coating_id=coating.id, availability=models.PricingAvailability.RX,
                               price_pair=price, currency="EGP", source_catalog_id=cat.id,
                               power_eligibility=models.PowerEligibilityStatus.UNRESTRICTED)
    db.add(vp); db.commit(); db.refresh(vp)
    pr = models.PowerRange(lens_model_id=m.id, variant_id=v.id, pricing_id=vp.id,
                           sph_min=total_power_min, sph_max=total_power_max,
                           cyl_min=-max_cyl_abs, cyl_max=0.0,
                           total_power_min=total_power_min, total_power_max=total_power_max,
                           max_cyl_abs=max_cyl_abs, add_min=add_min, add_max=add_max)
    db.add(pr); db.commit()
    return m


def _office_rows(resp, model_name="Office"):
    return [r for g in resp.groups for r in g.results if r.model_name == model_name]


@pytest.mark.parametrize("add_value,should_be_eligible", [
    (0.75, True), (4.00, True), (0.70, False), (4.01, False),
])
def test_zeiss_office_1_6_add_boundary_0_75_to_4_00(db, add_value, should_be_eligible):
    _mk_office_row(db, 1.6, add_min=0.75, add_max=4.00)
    presc = _mk_presc(db, -2.0, -2.0, od_add=add_value, os_add=add_value)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="office"))
    rows = _office_rows(resp)
    assert (len(rows) == 1) == should_be_eligible


@pytest.mark.parametrize("add_value,should_be_eligible", [
    (0.75, True), (3.50, True), (0.70, False), (3.51, False),
])
def test_zeiss_office_other_index_add_boundary_0_75_to_3_50(db, add_value, should_be_eligible):
    _mk_office_row(db, 1.67, add_min=0.75, add_max=3.50)
    presc = _mk_presc(db, -2.0, -2.0, od_add=add_value, os_add=add_value)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="office"))
    rows = _office_rows(resp)
    assert (len(rows) == 1) == should_be_eligible


def test_zeiss_office_missing_add_is_ineligible(db):
    _mk_office_row(db, 1.67, add_min=0.75, add_max=3.50)
    presc = _mk_presc(db, -2.0, -2.0, od_add=None, os_add=None)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="office"))
    assert _office_rows(resp) == []


def test_zeiss_office_zero_add_is_ineligible(db):
    _mk_office_row(db, 1.67, add_min=0.75, add_max=3.50)
    presc = _mk_presc(db, -2.0, -2.0, od_add=0.0, os_add=0.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="office"))
    assert _office_rows(resp) == []


# ------------------------------------------------------------- search: HOYA/SCOPE Office regression
def _mk_hoya_occupational_row(db, model_name="WorkSmart"):
    co = models.Company(name="HOYA", country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename="hoya.pdf", file_path="hoya.pdf",
                         status=models.CatalogStatus.CONFIRMED)
    db.add(cat); db.commit(); db.refresh(cat)
    m = models.LensModel(company_id=co.id, name=model_name, category=models.LensCategory.OFFICE)
    db.add(m); db.commit(); db.refresh(m)
    v = models.LensVariant(lens_model_id=m.id, material=models.MaterialType.CR39, index_value=1.5,
                           design_type=models.DesignType.SPHERICAL, is_aspherical=False,
                           price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    vp = models.VariantPricing(variant_id=v.id, availability=models.PricingAvailability.RX,
                               price_pair=9450, currency="EGP", market_scope="Out Of Egypt",
                               source_catalog_id=cat.id,
                               power_eligibility=models.PowerEligibilityStatus.UNRESTRICTED)
    db.add(vp); db.commit(); db.refresh(vp)
    pr = models.PowerRange(lens_model_id=m.id, variant_id=v.id, pricing_id=vp.id,
                           sph_min=-8.0, sph_max=12.0, cyl_min=-6.0, cyl_max=0.0)
    db.add(pr); db.commit()
    return m


def test_hoya_office_stays_add_neutral_even_with_a_zeiss_office_row_present(db):
    # The critical cross-manufacturer regression: introducing ZEISS Office's
    # ADD-aware rows must not change HOYA Office's existing, proven
    # ADD-neutral behaviour. An unrelated nonzero ADD on the prescription
    # (not matching any ZEISS-style range) must still be ignored for HOYA.
    _mk_hoya_occupational_row(db)
    _mk_office_row(db, 1.67, add_min=0.75, add_max=3.50)  # ZEISS Office present in the same search
    presc = _mk_presc(db, -2.0, -2.0, od_add=99.0, os_add=99.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="office"))
    hoya_rows = _office_rows(resp, model_name="WorkSmart")
    assert len(hoya_rows) == 1
    zeiss_rows = _office_rows(resp, model_name="Office")
    assert zeiss_rows == []  # 99.0 is outside 0.75-3.50, correctly rejected


def test_scope_office_stays_add_neutral_even_with_a_zeiss_office_row_present(db):
    co = models.Company(name="SCOPE", country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename="scope.pdf", file_path="scope.pdf",
                         status=models.CatalogStatus.CONFIRMED)
    db.add(cat); db.commit(); db.refresh(cat)
    m = models.LensModel(company_id=co.id, name="SCOPE Office Doctor", category=models.LensCategory.OFFICE)
    db.add(m); db.commit(); db.refresh(m)
    v = models.LensVariant(lens_model_id=m.id, material=models.MaterialType.CR39, index_value=1.5,
                           design_type=models.DesignType.SPHERICAL, is_aspherical=False,
                           price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    vp = models.VariantPricing(variant_id=v.id, availability=models.PricingAvailability.RX,
                               price_pair=1430, currency="EGP", source_catalog_id=cat.id,
                               power_eligibility=models.PowerEligibilityStatus.UNRESTRICTED)
    db.add(vp); db.commit()
    _mk_office_row(db, 1.6, add_min=0.75, add_max=4.00)
    presc = _mk_presc(db, -2.0, -2.0, od_add=50.0, os_add=50.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="office"))
    scope_rows = _office_rows(resp, model_name="SCOPE Office Doctor")
    assert len(scope_rows) == 1
    zeiss_rows = _office_rows(resp, model_name="Office")
    assert zeiss_rows == []


# ------------------------------------------------------------- use_mode isolation
def test_zeiss_office_never_leaks_into_other_use_modes(db):
    _mk_office_row(db, 1.67, add_min=0.75, add_max=3.50)
    presc = _mk_presc(db, -2.0, -2.0, od_add=2.0, os_add=2.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="distance"))
    assert _office_rows(resp) == []
