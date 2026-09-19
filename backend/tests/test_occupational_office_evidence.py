"""Occupational / Office category correction (Special Lenses architecture,
owner-confirmed, 2026-09-19) - the proven first Special Lenses subtype.

Evidence:
  - HOYA: Hoya_Price_List_2025_Updated.pdf pp.25-26 explicitly headers
    Supereader B, WorkSmart(+PNX), iD WorkStyle(+PNX) "Occupational Lenses
    (RX)" - never "Progressive Lenses (RX)". Currently stored under
    category=PROGRESSIVE (a known pre-existing importer quirk, already
    documented in addon_scope_evidence.py / progressive_add_evidence.py's
    own excluded-model lists).
  - SCOPE: catalog explicitly headers Office Doctor / Office Officestar rows
    "Office Design / Indoor" with near/intermediate working-distance
    descriptions. Currently stored under category=SINGLE_VISION.

Both are the SAME owner-confirmed "Occupational / Office" Special Lenses
subtype. models.LensCategory.OFFICE already existed in the schema (unused
until now) and required no migration - see app/catalog_corrections.py's
OCCUPATIONAL_OFFICE_MODELS (ingestion-time) and
app/occupational_office_evidence.py (already-persisted-row backfill).

Strict scope: exactly these 7 catalog-proven models. ZEISS (catalog has an
Office Lenses section but no rows are currently ingested), PLATINUM "Office"
(weaker evidence per the 2026-09-19 audit), and BBGR "Anti-Fatigue" (no
preserved per-product identity) are all deliberately NOT touched - proven by
dedicated negative tests here.

SCOPE "Young"/"Myoblock" were the other not-yet-resolved candidates when this
module was first written; they have since been resolved separately (Special
Lenses architecture, 2026-09-19, single_vision -> anti_fatigue / single_vision
-> myopia_control, never office) - see
tests/test_special_lenses_subtypes_evidence.py, which is now the source of
truth for those models' category.

Deliberately synthetic (mirrors test_hoya_bifocal_category_evidence.py's own
pattern) - no PDF parsing, no dependency on the live release_runtime.db for
the pipeline-level proof; the live db result is verified separately.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database import Base  # noqa: E402
from app import models, crud, database, schemas, product_search, catalog_corrections  # noqa: E402
from app import occupational_office_evidence  # noqa: E402
from app.addon_scope_evidence import proves_addon_scope  # noqa: E402

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


# --------------------------------------------------------------- unit rule
@pytest.mark.parametrize("model_name", [
    "Supereader B", "WorkSmart", "WorkSmart PNX", "iD WorkStyle", "iD WorkStyle PNX",
])
def test_corrected_category_fixes_hoya_occupational(model_name):
    assert catalog_corrections.corrected_category(
        "HOYA", model_name, models.LensCategory.PROGRESSIVE) == models.LensCategory.OFFICE


@pytest.mark.parametrize("model_name", ["SCOPE Office Doctor", "SCOPE Office Officestar"])
def test_corrected_category_fixes_scope_office(model_name):
    assert catalog_corrections.corrected_category(
        "SCOPE", model_name, models.LensCategory.SINGLE_VISION) == models.LensCategory.OFFICE


@pytest.mark.parametrize("company,model_name", [
    ("HOYA", "Supereader B"), ("HOYA", "WorkSmart"), ("HOYA", "WorkSmart PNX"),
    ("HOYA", "iD WorkStyle"), ("HOYA", "iD WorkStyle PNX"),
    ("SCOPE", "SCOPE Office Doctor"), ("SCOPE", "SCOPE Office Officestar"),
])
def test_corrected_category_is_idempotent_once_already_office(company, model_name):
    assert catalog_corrections.corrected_category(
        company, model_name, models.LensCategory.OFFICE) == models.LensCategory.OFFICE


@pytest.mark.parametrize("name", [
    "Daynamic", "Amplitude Plus", "Balansis", "iD LifeStyle", "iD MyStyle", "iD MySelf",
])
def test_corrected_category_never_touches_other_hoya_progressive_families(name):
    assert catalog_corrections.corrected_category(
        "HOYA", name, models.LensCategory.PROGRESSIVE) == models.LensCategory.PROGRESSIVE


def test_corrected_category_never_touches_hoya_bifocal_or_mineral():
    assert catalog_corrections.corrected_category(
        "HOYA", "Bi-Focal", models.LensCategory.BIFOCAL) == models.LensCategory.BIFOCAL
    assert catalog_corrections.corrected_category(
        "HOYA", "Mineral", models.LensCategory.PROGRESSIVE) == models.LensCategory.PROGRESSIVE


@pytest.mark.parametrize("model_name", ["SCOPE Young Shabab", "SCOPE Myoblock Metavision (Myoblock)"])
def test_corrected_category_moves_scope_young_and_myoblock_to_their_own_subtype_not_office(model_name):
    # SCOPE Young/Myoblock were the other not-yet-resolved candidates when
    # this module was first written (see module docstring); resolved
    # separately as their own Special Lenses subtypes (anti_fatigue /
    # myopia_control) - full coverage in
    # test_special_lenses_subtypes_evidence.py. This test only pins the
    # OFFICE-specific boundary: neither must ever end up OFFICE.
    assert catalog_corrections.corrected_category(
        "SCOPE", model_name, models.LensCategory.SINGLE_VISION) != models.LensCategory.OFFICE


@pytest.mark.parametrize("company,model_name", [
    ("ZEISS", "Office"), ("PLATINUM", "Office"), ("BBGR", "Anti-Fatigue"),
    ("Other", "WorkSmart"), ("Other", "SCOPE Office Doctor"),
])
def test_corrected_category_never_touches_unproven_companies(company, model_name):
    assert catalog_corrections.corrected_category(
        company, model_name, models.LensCategory.SINGLE_VISION) == models.LensCategory.SINGLE_VISION


# --------------------------------------------------------------- pipeline (rebuild proof)
def _company(db, name):
    c = models.Company(name=name)
    db.add(c); db.commit(); db.refresh(c)
    return c


def _catalog(db, company):
    cat = models.Catalog(company_id=company.id, filename="c.pdf", file_path="/x/c.pdf",
                         status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)
    return cat


def _ext(db, catalog, *, name, price, availability, index, category, coating_id=None,
         sph_min=-6.0, sph_max=6.0, cyl_min=-4.0, cyl_max=0.0):
    md = {"name": name, "material": "CR39", "index": index, "availability": availability,
          "price": price, "category": category, "design_type": "spherical", "is_aspherical": False}
    coating_status = (models.CoatingExtractionStatus.RESOLVED if coating_id is not None
                       else models.CoatingExtractionStatus.EXPLICIT_NONE)
    row = models.CatalogExtraction(
        catalog_id=catalog.id, extracted_name=name, extracted_material="CR39",
        extracted_index=index, extracted_availability=availability, extracted_price=price,
        extracted_category=category,
        sph_min=sph_min, sph_max=sph_max, cyl_min=cyl_min, cyl_max=cyl_max,
        coating_extraction_status=coating_status, coating_id=coating_id,
        modified_data=md, status="confirmed")
    db.add(row); db.commit(); db.refresh(row)
    return row


def test_hoya_worksmart_ingests_as_office_category(db):
    co = _company(db, "HOYA")
    cat = _catalog(db, co)
    coating = models.Coating(code="Super Hi Vision", name="Super Hi Vision")
    db.add(coating); db.commit()
    _ext(db, cat, name="WorkSmart", price=9450, availability="stock", index=1.5,
         category="progressive", coating_id=coating.id)
    result = crud.confirm_catalog_commercial(db, cat.id)
    assert result["status"] == "confirmed"
    [model] = db.query(models.LensModel).filter(models.LensModel.company_id == co.id).all()
    assert model.category == models.LensCategory.OFFICE


def test_scope_office_doctor_ingests_as_office_category(db):
    co = _company(db, "SCOPE")
    cat = _catalog(db, co)
    _ext(db, cat, name="SCOPE Office Doctor", price=1430, availability="stock", index=1.5,
         category="single_vision")
    result = crud.confirm_catalog_commercial(db, cat.id)
    assert result["status"] == "confirmed"
    [model] = db.query(models.LensModel).filter(models.LensModel.company_id == co.id).all()
    assert model.category == models.LensCategory.OFFICE


def test_hoya_other_progressive_families_still_ingest_as_progressive(db):
    co = _company(db, "HOYA")
    cat = _catalog(db, co)
    coating = models.Coating(code="Super Hi Vision", name="Super Hi Vision")
    db.add(coating); db.commit()
    _ext(db, cat, name="Daynamic", price=12600, availability="stock", index=1.5,
         category="progressive", coating_id=coating.id)
    crud.confirm_catalog_commercial(db, cat.id)
    [model] = db.query(models.LensModel).filter(models.LensModel.company_id == co.id).all()
    assert model.category == models.LensCategory.PROGRESSIVE


# --------------------------------------------------------------- reconcile (already-persisted rows)
def _mk_persisted_model(db, company_name, model_name, category):
    co = db.query(models.Company).filter(models.Company.name == company_name).first()
    if co is None:
        co = models.Company(name=company_name, country="EG", is_active=True, is_deleted=False)
        db.add(co); db.commit(); db.refresh(co)
    m = models.LensModel(company_id=co.id, name=model_name, category=category)
    db.add(m); db.commit(); db.refresh(m)
    return m


def test_reconcile_fixes_already_persisted_hoya_occupational_rows(db):
    m1 = _mk_persisted_model(db, "HOYA", "Supereader B", models.LensCategory.PROGRESSIVE)
    m2 = _mk_persisted_model(db, "HOYA", "iD WorkStyle PNX", models.LensCategory.PROGRESSIVE)
    result = occupational_office_evidence.reconcile(db)
    assert result["updated"] == 2
    db.refresh(m1); db.refresh(m2)
    assert m1.category == models.LensCategory.OFFICE
    assert m2.category == models.LensCategory.OFFICE


def test_reconcile_fixes_already_persisted_scope_office_rows(db):
    m1 = _mk_persisted_model(db, "SCOPE", "SCOPE Office Doctor", models.LensCategory.SINGLE_VISION)
    m2 = _mk_persisted_model(db, "SCOPE", "SCOPE Office Officestar", models.LensCategory.SINGLE_VISION)
    result = occupational_office_evidence.reconcile(db)
    assert result["updated"] == 2
    db.refresh(m1); db.refresh(m2)
    assert m1.category == models.LensCategory.OFFICE
    assert m2.category == models.LensCategory.OFFICE


def test_reconcile_never_touches_unrelated_rows(db):
    m_daynamic = _mk_persisted_model(db, "HOYA", "Daynamic", models.LensCategory.PROGRESSIVE)
    m_bifocal = _mk_persisted_model(db, "HOYA", "Bi-Focal", models.LensCategory.BIFOCAL)
    m_young = _mk_persisted_model(db, "SCOPE", "SCOPE Young Shabab", models.LensCategory.SINGLE_VISION)
    result = occupational_office_evidence.reconcile(db)
    assert result["updated"] == 0
    db.refresh(m_daynamic); db.refresh(m_bifocal); db.refresh(m_young)
    assert m_daynamic.category == models.LensCategory.PROGRESSIVE
    assert m_bifocal.category == models.LensCategory.BIFOCAL
    assert m_young.category == models.LensCategory.SINGLE_VISION


def test_reconcile_is_idempotent(db):
    _mk_persisted_model(db, "HOYA", "WorkSmart", models.LensCategory.PROGRESSIVE)
    result1 = occupational_office_evidence.reconcile(db)
    result2 = occupational_office_evidence.reconcile(db)
    assert result1["updated"] == 1
    assert result2["updated"] == 0


# --------------------------------------------------------------- use_mode routing
def test_office_use_mode_is_a_recognized_route(db):
    presc = _mk_presc(db, -2.0, -2.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="office"))
    assert resp.availability_answer.code != "validation_error"


def _mk_hoya_occupational_row(db, model_name="WorkSmart", category=models.LensCategory.OFFICE):
    co = models.Company(name="HOYA", country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename="hoya.pdf", file_path="hoya.pdf",
                         status=models.CatalogStatus.CONFIRMED)
    db.add(cat); db.commit(); db.refresh(cat)
    m = models.LensModel(company_id=co.id, name=model_name, category=category)
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


def test_use_mode_office_reaches_hoya_occupational(db):
    _mk_hoya_occupational_row(db)
    presc = _mk_presc(db, -2.0, -2.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="office"))
    rows = [r for g in resp.groups for r in g.results if r.model_name == "WorkSmart"]
    assert len(rows) == 1


def test_use_mode_office_ignores_unrelated_add_already_on_the_prescription(db):
    # No ADD-power corridor is proven for Occupational/Office (item 4: never
    # reuse Progressive's "requires ADD" rule) - an unrelated ADD already
    # recorded on the prescription must never gate Office eligibility.
    _mk_hoya_occupational_row(db)
    presc = _mk_presc(db, -2.0, -2.0, od_add=2.0, os_add=2.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="office"))
    rows = [r for g in resp.groups for r in g.results if r.model_name == "WorkSmart"]
    assert len(rows) == 1


@pytest.mark.parametrize("leaking_use_mode,needs_add", [
    ("progressive", True), ("bifocal", True), ("distance", False),
])
def test_hoya_occupational_never_leaks_into_other_use_modes(db, leaking_use_mode, needs_add):
    _mk_hoya_occupational_row(db)
    presc = _mk_presc(db, -2.0, -2.0, od_add=2.0 if needs_add else None,
                      os_add=2.0 if needs_add else None)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode=leaking_use_mode))
    rows = [r for g in resp.groups for r in g.results if r.model_name == "WorkSmart"]
    assert rows == []


def _mk_scope_office_row(db, model_name="SCOPE Office Doctor"):
    co = models.Company(name="SCOPE", country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename="scope.pdf", file_path="scope.pdf",
                         status=models.CatalogStatus.CONFIRMED)
    db.add(cat); db.commit(); db.refresh(cat)
    m = models.LensModel(company_id=co.id, name=model_name, category=models.LensCategory.OFFICE)
    db.add(m); db.commit(); db.refresh(m)
    v = models.LensVariant(lens_model_id=m.id, material=models.MaterialType.CR39, index_value=1.5,
                           design_type=models.DesignType.SPHERICAL, is_aspherical=False,
                           price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    vp = models.VariantPricing(variant_id=v.id, availability=models.PricingAvailability.RX,
                               price_pair=1430, currency="EGP",
                               source_catalog_id=cat.id,
                               power_eligibility=models.PowerEligibilityStatus.UNRESTRICTED)
    db.add(vp); db.commit()
    return m


def test_use_mode_office_reaches_scope_office(db):
    _mk_scope_office_row(db)
    presc = _mk_presc(db, -2.0, -2.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="office"))
    rows = [r for g in resp.groups for r in g.results if r.model_name == "SCOPE Office Doctor"]
    assert len(rows) == 1


def test_use_mode_single_vision_does_not_return_scope_office(db):
    _mk_scope_office_row(db)
    presc = _mk_presc(db, -2.0, -2.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="distance"))
    rows = [r for g in resp.groups for r in g.results if r.model_name == "SCOPE Office Doctor"]
    assert rows == []


# --------------------------------------------------------------- addon scope
@pytest.mark.parametrize("model_name,index_value,coating_name", [
    ("Supereader B", 1.5, "Hi Vision Aqua"), ("WorkSmart", 1.5, "Super Hi Vision"),
    ("iD WorkStyle", 1.5, "Long Life UV Control"),
])
def test_addon_scope_recognizes_hoya_occupational_under_office_category(
        model_name, index_value, coating_name):
    assert proves_addon_scope(
        "HOYA", model_name=model_name, category="office", index_value=index_value,
        design_type="spherical", design_variant=None, design_tier=None,
        treatment_band=None, color_variant=None, coating_name=coating_name,
        market_scope="Out Of Egypt")


@pytest.mark.parametrize("model_name,index_value,coating_name", [
    ("Supereader B", 1.5, "Hi Vision Aqua"), ("WorkSmart", 1.5, "Super Hi Vision"),
])
def test_addon_scope_no_longer_recognizes_hoya_occupational_under_stale_progressive_category(
        model_name, index_value, coating_name):
    assert not proves_addon_scope(
        "HOYA", model_name=model_name, category="progressive", index_value=index_value,
        design_type="spherical", design_variant=None, design_tier=None,
        treatment_band=None, color_variant=None, coating_name=coating_name,
        market_scope="Out Of Egypt")
