"""HOYA "Bi-Focal" category correction (Catalog Truth Audit follow-up,
2026-09-19) - proven, single-model correction discovered during the
read-only category-classification review after the Progressive ADD fix.

Evidence:
  - Hoya_Price_List_2025_Updated.pdf p.27 explicitly headers this product
    "Bi-Focal Lenses (RX)" - never "Progressive Lenses (RX)".
  - app/addon_scope_evidence.py's own pre-existing comment already stated:
    "Category below is the current importer representation, not a claim
    that bifocals are optically progressive" - i.e. category="progressive"
    for this model was already known-wrong, not an intentional design.
  - models.LensCategory.BIFOCAL already exists and is actively used by 4
    other manufacturers (Pixel, BBGR, PLATINUM x2, SCOPE x6) - not a novel
    schema usage.
  - Demonstrated bug: use_mode="bifocal" could never find HOYA Bi-Focal
    (wrong category), while use_mode="progressive" incorrectly included it
    alongside genuine progressive designs (Amplitude Plus, Daynamic, ...).

Strict scope: ONLY HOYA "Bi-Focal". Mineral is explicitly NOT touched (a
separate, still-unresolved finding from the same review) - proven by a
dedicated negative test here. The Progressive ADD rule
(app/progressive_add_evidence.py) is not broadened; a BIFOCAL-category row is
naturally out of its category=PROGRESSIVE-only query, so it is not touched by
this change either.

Occupational (Supereader B, WorkSmart(+PNX), iD WorkStyle(+PNX)) was the other
not-yet-resolved finding from this same review at the time this module was
written; it has since been resolved separately (Special Lenses architecture,
2026-09-19, progressive -> office, not bifocal) - see
tests/test_occupational_office_evidence.py, which is now the source of truth
for those models' category.

Deliberately synthetic (mirrors test_audit_a1_a6_pipeline_persistence.py's
own pattern) - no PDF parsing, no dependency on the live release_runtime.db
for the pipeline-level proof; the live db result is verified separately.
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
def test_corrected_category_fixes_hoya_bifocal():
    assert catalog_corrections.corrected_category(
        "HOYA", "Bi-Focal", models.LensCategory.PROGRESSIVE) == models.LensCategory.BIFOCAL


def test_corrected_category_is_idempotent_once_already_bifocal():
    assert catalog_corrections.corrected_category(
        "HOYA", "Bi-Focal", models.LensCategory.BIFOCAL) == models.LensCategory.BIFOCAL


@pytest.mark.parametrize("model_name", [
    "Supereader B", "WorkSmart", "WorkSmart PNX", "iD WorkStyle", "iD WorkStyle PNX",
])
def test_corrected_category_moves_occupational_models_to_office_not_bifocal(model_name):
    # Occupational was the other not-yet-resolved finding when this module
    # was first written (see module docstring); resolved separately as
    # progressive -> office, never bifocal - full coverage in
    # test_occupational_office_evidence.py. This test only pins the
    # BIFOCAL-specific boundary: Occupational must never end up BIFOCAL.
    assert catalog_corrections.corrected_category(
        "HOYA", model_name, models.LensCategory.PROGRESSIVE) != models.LensCategory.BIFOCAL


def test_corrected_category_never_touches_mineral():
    assert catalog_corrections.corrected_category(
        "HOYA", "Mineral", models.LensCategory.PROGRESSIVE) == models.LensCategory.PROGRESSIVE


def test_corrected_category_never_touches_other_hoya_progressive_families():
    assert catalog_corrections.corrected_category(
        "HOYA", "Daynamic", models.LensCategory.PROGRESSIVE) == models.LensCategory.PROGRESSIVE
    assert catalog_corrections.corrected_category(
        "HOYA", "Amplitude Plus", models.LensCategory.PROGRESSIVE) == models.LensCategory.PROGRESSIVE


def test_corrected_category_never_touches_other_companies_bifocal_named_model():
    assert catalog_corrections.corrected_category(
        "Other", "Bi-Focal", models.LensCategory.PROGRESSIVE) == models.LensCategory.PROGRESSIVE


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
         design_variant=None, sph_min=-6.0, sph_max=6.0, cyl_min=-4.0, cyl_max=0.0):
    md = {"name": name, "material": "CR39", "index": index, "availability": availability,
          "price": price, "category": category, "design_type": "spherical", "is_aspherical": False}
    for k, v in (("design_variant", design_variant),):
        if v is not None:
            md[k] = v
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


def test_hoya_bifocal_ingests_as_bifocal_category(db):
    co = _company(db, "HOYA")
    cat = _catalog(db, co)
    coating = models.Coating(code="Hi Vision Aqua", name="Hi Vision Aqua")
    db.add(coating); db.commit()
    # Raw extraction shaped exactly like the real (known-wrong) source data:
    # category="progressive", as a fresh rebuild's extraction would produce
    # before this fix.
    _ext(db, cat, name="Bi-Focal", price=9450, availability="stock", index=1.5,
         category="progressive", coating_id=coating.id, design_variant="Flat Top S28")
    result = crud.confirm_catalog_commercial(db, cat.id)
    assert result["status"] == "confirmed"
    [model] = db.query(models.LensModel).filter(models.LensModel.company_id == co.id).all()
    assert model.category == models.LensCategory.BIFOCAL


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


# --------------------------------------------------------------- use_mode routing
def _mk_bifocal_row(db):
    """An otherwise-eligible HOYA Bi-Focal row: real category-fix identity,
    with explicit add_min/add_max so this test isolates the category-routing
    fix only, never the separate (out-of-scope) Bi-Focal ADD-completeness
    question."""
    co = models.Company(name="HOYA", country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename="hoya.pdf", file_path="hoya.pdf",
                         status=models.CatalogStatus.CONFIRMED)
    db.add(cat); db.commit(); db.refresh(cat)
    m = models.LensModel(company_id=co.id, name="Bi-Focal", category=models.LensCategory.BIFOCAL)
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
                           sph_min=-8.0, sph_max=8.0, cyl_min=-4.0, cyl_max=0.0,
                           add_min=1.0, add_max=3.0)
    db.add(pr); db.commit()
    return m


def test_use_mode_bifocal_reaches_hoya_bifocal(db):
    _mk_bifocal_row(db)
    presc = _mk_presc(db, -2.0, -2.0, od_cyl=-1.0, os_cyl=-1.0, od_add=2.0, os_add=2.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="bifocal"))
    rows = [r for g in resp.groups for r in g.results if r.model_name == "Bi-Focal"]
    assert len(rows) == 1


def test_use_mode_progressive_does_not_return_hoya_bifocal(db):
    _mk_bifocal_row(db)
    presc = _mk_presc(db, -2.0, -2.0, od_cyl=-1.0, os_cyl=-1.0, od_add=2.0, os_add=2.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="progressive"))
    rows = [r for g in resp.groups for r in g.results if r.model_name == "Bi-Focal"]
    assert rows == []


# --------------------------------------------------------------- addon scope
def test_addon_scope_still_recognizes_hoya_bifocal_after_reclassification():
    assert proves_addon_scope(
        "HOYA", model_name="Bi-Focal", category="bifocal", index_value=1.5,
        design_type="spherical", design_variant="Curve Top C28", design_tier=None,
        treatment_band=None, color_variant=None, coating_name="Hi Vision Aqua",
        market_scope="Out Of Egypt")


def test_addon_scope_no_longer_recognizes_hoya_bifocal_under_stale_progressive_category():
    assert not proves_addon_scope(
        "HOYA", model_name="Bi-Focal", category="progressive", index_value=1.5,
        design_type="spherical", design_variant="Curve Top C28", design_tier=None,
        treatment_band=None, color_variant=None, coating_name="Hi Vision Aqua",
        market_scope="Out Of Egypt")
