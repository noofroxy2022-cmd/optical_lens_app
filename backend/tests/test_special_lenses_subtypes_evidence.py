"""Young/Anti-Fatigue and Myopia Control category corrections (Special
Lenses architecture, owner-confirmed, 2026-09-19) - the second and third
proven Special Lenses subtypes, following the exact
occupational_office_evidence.py pattern.

Evidence (already proven by the prior read-only investigation, not repeated
here):
  - SCOPE Young/Shabab: SCOPE.pdf p.9 "Young Lenses / عدسات ضد الإجهاد
    للشباب" - designed for ages 18-40, relieves strain/headache from heavy
    electronic-device use and prolonged reading; improves reading/
    intermediate vision while remaining usable at distance. Currently stored
    as category=SINGLE_VISION.
  - SCOPE Myoblock/Metavision: SCOPE.pdf pp.13-15 "Myoblock Lenses / عدسات
    مايوبلوك لإيقاف تدهور النظر عند الأطفال" + "myoblock reduces the myopia
    progression". Printed power range (Sph -0.50 to -10.00, Cyl to -4.00) is
    already represented via a real PowerRange row in this project (see
    test_scope_import.py's MYOBLOCK_LIMIT). Currently stored as
    category=SINGLE_VISION.

OWNER-CONFIRMED BUSINESS RULE (2026-09-19, resolves the previous read-only
investigation's STOP blocker): the app must NOT gate either subtype on
patient age or on any frame/fitting measurement (segment height, frame
width, boxing dimensions, ...). Neither field exists anywhere in the schema,
and neither is added here. Selecting "Special Lenses -> Young/Anti-Fatigue"
or "Special Lenses -> Myopia Control" is a deliberate choice by the seller/
doctor; the app's job is only to show the proven products under the correct
subtype, match the printed Power Range, and apply the normal price/
availability mechanisms - catalog age/fitting text remains documentation
only, never a search eligibility gate. This module's tests pin that down so
the blocker is never reintroduced.

Strict scope: exactly these two catalog-proven SCOPE products. PLATINUM
"Young" and "MYO D" (bare price tables, no catalog description), BBGR
"Anti-Fatigue"/"Extenso" (bare price table, no catalog description; owner
already confirmed BBGR identity is not to be changed), ZEISS "SmartLife
Young" (ZEISS's own catalog classifies it as Single Vision, not Special
Lenses), and ZEISS "MyoCare"/"MyoCare S"/"MyoActive" (proven Myopia
Management products, but not currently ingested at all - a separate task;
MyoActive's own catalog page prints "Available from 1st October 2026", after
the current project date) are all deliberately NOT touched - proven by
dedicated negative tests here.

Deliberately synthetic (mirrors test_occupational_office_evidence.py's own
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
from app import anti_fatigue_evidence, myopia_control_evidence  # noqa: E402

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


# --------------------------------------------------------------- unit rule (1/2)
def test_corrected_category_fixes_scope_young_shabab():
    assert catalog_corrections.corrected_category(
        "SCOPE", "SCOPE Young Shabab", models.LensCategory.SINGLE_VISION
    ) == models.LensCategory.ANTI_FATIGUE


def test_corrected_category_fixes_scope_myoblock():
    assert catalog_corrections.corrected_category(
        "SCOPE", "SCOPE Myoblock Metavision (Myoblock)", models.LensCategory.SINGLE_VISION
    ) == models.LensCategory.MYOPIA_CONTROL


def test_corrected_category_is_idempotent_for_both_new_subtypes():
    assert catalog_corrections.corrected_category(
        "SCOPE", "SCOPE Young Shabab", models.LensCategory.ANTI_FATIGUE
    ) == models.LensCategory.ANTI_FATIGUE
    assert catalog_corrections.corrected_category(
        "SCOPE", "SCOPE Myoblock Metavision (Myoblock)", models.LensCategory.MYOPIA_CONTROL
    ) == models.LensCategory.MYOPIA_CONTROL


# --------------------------------------------------------------- exact scope negatives (3)
@pytest.mark.parametrize("company,model_name", [
    ("PLATINUM", "PLATINUM Young"),
    ("PLATINUM", "PLATINUM MYO D"),
    ("BBGR", "BBGR"),  # BBGR Anti-Fatigue/Extenso live under the generic "BBGR" model name
    ("ZEISS", "SmartLife Young"),
    # ZEISS MyoActive stays a negative: proven Myopia Management, but not
    # ingested (future-dated "Available from 1st October 2026", and its own
    # power-range chart has no per-product split proven separately from
    # MyoCare/MyoCare S RX) - see app/zeiss_myopia_control_evidence.py.
    # MyoCare/MyoCare S themselves are no longer negatives here: owner-
    # confirmed and ingested 2026-09-19/20 - see
    # test_zeiss_myopia_control_evidence.py, now the source of truth for
    # those two models' category.
    ("ZEISS", "MyoActive"),
])
def test_corrected_category_never_touches_strict_negative_products(company, model_name):
    assert catalog_corrections.corrected_category(
        company, model_name, models.LensCategory.SINGLE_VISION) == models.LensCategory.SINGLE_VISION


def test_corrected_category_never_confuses_the_two_new_subtypes_or_office():
    # Young/Shabab never becomes Myopia Control or Office, and vice versa.
    assert catalog_corrections.corrected_category(
        "SCOPE", "SCOPE Myoblock Metavision (Myoblock)", models.LensCategory.SINGLE_VISION
    ) != models.LensCategory.ANTI_FATIGUE
    assert catalog_corrections.corrected_category(
        "SCOPE", "SCOPE Young Shabab", models.LensCategory.SINGLE_VISION
    ) != models.LensCategory.MYOPIA_CONTROL
    assert catalog_corrections.corrected_category(
        "SCOPE", "SCOPE Office Doctor", models.LensCategory.SINGLE_VISION
    ) == models.LensCategory.OFFICE  # existing Office correction still exact-matches only its own name


# --------------------------------------------------------------- pipeline / rebuild proof (5)
def _company(db, name):
    c = models.Company(name=name)
    db.add(c); db.commit(); db.refresh(c)
    return c


def _catalog(db, company):
    cat = models.Catalog(company_id=company.id, filename="c.pdf", file_path="/x/c.pdf",
                         status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)
    return cat


def _ext(db, catalog, *, name, price, availability, index, category):
    md = {"name": name, "material": "CR39", "index": index, "availability": availability,
          "price": price, "category": category, "design_type": "spherical", "is_aspherical": False}
    row = models.CatalogExtraction(
        catalog_id=catalog.id, extracted_name=name, extracted_material="CR39",
        extracted_index=index, extracted_availability=availability, extracted_price=price,
        extracted_category=category,
        sph_min=-6.0, sph_max=6.0, cyl_min=-4.0, cyl_max=0.0,
        coating_extraction_status=models.CoatingExtractionStatus.EXPLICIT_NONE,
        modified_data=md, status="confirmed")
    db.add(row); db.commit(); db.refresh(row)
    return row


def test_scope_young_shabab_ingests_as_anti_fatigue_category(db):
    co = _company(db, "SCOPE")
    cat = _catalog(db, co)
    _ext(db, cat, name="SCOPE Young Shabab", price=1390, availability="stock", index=1.5,
         category="single_vision")
    result = crud.confirm_catalog_commercial(db, cat.id)
    assert result["status"] == "confirmed"
    [model] = db.query(models.LensModel).filter(models.LensModel.company_id == co.id).all()
    assert model.category == models.LensCategory.ANTI_FATIGUE


def test_scope_myoblock_ingests_as_myopia_control_category(db):
    co = _company(db, "SCOPE")
    cat = _catalog(db, co)
    _ext(db, cat, name="SCOPE Myoblock Metavision (Myoblock)", price=3700, availability="stock", index=1.5,
         category="single_vision")
    result = crud.confirm_catalog_commercial(db, cat.id)
    assert result["status"] == "confirmed"
    [model] = db.query(models.LensModel).filter(models.LensModel.company_id == co.id).all()
    assert model.category == models.LensCategory.MYOPIA_CONTROL


def test_scope_other_single_vision_products_still_ingest_unchanged(db):
    co = _company(db, "SCOPE")
    cat = _catalog(db, co)
    _ext(db, cat, name="SCOPE Single Vision Toric", price=950, availability="stock", index=1.5,
         category="single_vision")
    crud.confirm_catalog_commercial(db, cat.id)
    [model] = db.query(models.LensModel).filter(models.LensModel.company_id == co.id).all()
    assert model.category == models.LensCategory.SINGLE_VISION


# --------------------------------------------------------------- reconcile (4) idempotency + already-persisted rows
def _mk_persisted_model(db, company_name, model_name, category):
    co = db.query(models.Company).filter(models.Company.name == company_name).first()
    if co is None:
        co = models.Company(name=company_name, country="EG", is_active=True, is_deleted=False)
        db.add(co); db.commit(); db.refresh(co)
    m = models.LensModel(company_id=co.id, name=model_name, category=category)
    db.add(m); db.commit(); db.refresh(m)
    return m


def test_anti_fatigue_reconcile_fixes_already_persisted_row_and_is_idempotent(db):
    m = _mk_persisted_model(db, "SCOPE", "SCOPE Young Shabab", models.LensCategory.SINGLE_VISION)
    result1 = anti_fatigue_evidence.reconcile(db)
    assert result1["updated"] == 1
    db.refresh(m)
    assert m.category == models.LensCategory.ANTI_FATIGUE
    result2 = anti_fatigue_evidence.reconcile(db)
    assert result2["updated"] == 0


def test_myopia_control_reconcile_fixes_already_persisted_row_and_is_idempotent(db):
    m = _mk_persisted_model(db, "SCOPE", "SCOPE Myoblock Metavision (Myoblock)", models.LensCategory.SINGLE_VISION)
    result1 = myopia_control_evidence.reconcile(db)
    assert result1["updated"] == 1
    db.refresh(m)
    assert m.category == models.LensCategory.MYOPIA_CONTROL
    result2 = myopia_control_evidence.reconcile(db)
    assert result2["updated"] == 0


def test_reconcile_never_touches_unrelated_scope_or_other_company_rows(db):
    m_sv = _mk_persisted_model(db, "SCOPE", "SCOPE Single Vision Toric", models.LensCategory.SINGLE_VISION)
    m_young_scope = _mk_persisted_model(db, "SCOPE", "SCOPE Young Shabab", models.LensCategory.SINGLE_VISION)
    m_platinum_young = _mk_persisted_model(db, "PLATINUM", "PLATINUM Young", models.LensCategory.SINGLE_VISION)
    m_platinum_myo = _mk_persisted_model(db, "PLATINUM", "PLATINUM MYO D", models.LensCategory.SINGLE_VISION)
    result_af = anti_fatigue_evidence.reconcile(db)
    result_mc = myopia_control_evidence.reconcile(db)
    assert result_af["updated"] == 1  # only SCOPE Young Shabab
    assert result_mc["updated"] == 0  # no Myoblock row present
    db.refresh(m_sv); db.refresh(m_platinum_young); db.refresh(m_platinum_myo)
    assert m_sv.category == models.LensCategory.SINGLE_VISION
    assert m_platinum_young.category == models.LensCategory.SINGLE_VISION
    assert m_platinum_myo.category == models.LensCategory.SINGLE_VISION
    db.refresh(m_young_scope)
    assert m_young_scope.category == models.LensCategory.ANTI_FATIGUE


# --------------------------------------------------------------- use_mode routing (6/7/8/9)
def _mk_row(db, company_name, model_name, category, *, price=3000):
    co = models.Company(name=company_name, country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename=f"{company_name.lower()}.pdf",
                         file_path=f"{company_name.lower()}.pdf", status=models.CatalogStatus.CONFIRMED)
    db.add(cat); db.commit(); db.refresh(cat)
    m = models.LensModel(company_id=co.id, name=model_name, category=category)
    db.add(m); db.commit(); db.refresh(m)
    v = models.LensVariant(lens_model_id=m.id, material=models.MaterialType.CR39, index_value=1.5,
                           design_type=models.DesignType.SPHERICAL, is_aspherical=False,
                           price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    vp = models.VariantPricing(variant_id=v.id, availability=models.PricingAvailability.RX,
                               price_pair=price, currency="EGP", source_catalog_id=cat.id,
                               power_eligibility=models.PowerEligibilityStatus.UNRESTRICTED)
    db.add(vp); db.commit(); db.refresh(vp)
    pr = models.PowerRange(lens_model_id=m.id, variant_id=v.id, pricing_id=vp.id,
                           sph_min=-8.0, sph_max=8.0, cyl_min=-4.0, cyl_max=0.0)
    db.add(pr); db.commit()
    return m


def test_use_mode_anti_fatigue_reaches_scope_young(db):
    _mk_row(db, "SCOPE", "SCOPE Young Shabab", models.LensCategory.ANTI_FATIGUE)
    presc = _mk_presc(db, -2.0, -2.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="anti_fatigue"))
    rows = [r for g in resp.groups for r in g.results if r.model_name == "SCOPE Young Shabab"]
    assert len(rows) == 1


def test_use_mode_myopia_control_reaches_scope_myoblock(db):
    _mk_row(db, "SCOPE", "SCOPE Myoblock Metavision (Myoblock)", models.LensCategory.MYOPIA_CONTROL)
    presc = _mk_presc(db, -2.0, -2.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="myopia_control"))
    rows = [r for g in resp.groups for r in g.results if r.model_name == "SCOPE Myoblock Metavision (Myoblock)"]
    assert len(rows) == 1


@pytest.mark.parametrize("subtype_use_mode,model_name,category", [
    ("anti_fatigue", "SCOPE Young Shabab", models.LensCategory.ANTI_FATIGUE),
    ("myopia_control", "SCOPE Myoblock Metavision (Myoblock)", models.LensCategory.MYOPIA_CONTROL),
])
def test_subtype_search_never_leaks_ordinary_single_vision_products(db, subtype_use_mode, model_name, category):
    _mk_row(db, "SCOPE", model_name, category)
    _mk_row(db, "SCOPE", "SCOPE Single Vision Toric", models.LensCategory.SINGLE_VISION)
    presc = _mk_presc(db, -2.0, -2.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode=subtype_use_mode))
    names = {r.model_name for g in resp.groups for r in g.results}
    assert names == {model_name}  # the ordinary SV product never leaks in


@pytest.mark.parametrize("model_name,category", [
    ("SCOPE Young Shabab", models.LensCategory.ANTI_FATIGUE),
    ("SCOPE Myoblock Metavision (Myoblock)", models.LensCategory.MYOPIA_CONTROL),
])
def test_subtype_row_absent_from_ordinary_single_vision_search(db, model_name, category):
    _mk_row(db, "SCOPE", model_name, category)
    presc = _mk_presc(db, -2.0, -2.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="distance"))
    rows = [r for g in resp.groups for r in g.results if r.model_name == model_name]
    assert rows == []


# --------------------------------------------------------------- no age / no fitting gate (10/11)
def test_prescription_schema_has_no_age_or_fitting_fields():
    # Owner-confirmed (2026-09-19): neither field is ever added for Special
    # Lenses eligibility - this pins down that the schema stays that way.
    columns = {c.name for c in models.Prescription.__table__.columns}
    banned = {"age", "birth_date", "birthdate", "date_of_birth",
              "frame_width", "segment_height", "fitting_height", "boxing_width"}
    assert not (columns & banned)


@pytest.mark.parametrize("use_mode,model_name,category", [
    ("anti_fatigue", "SCOPE Young Shabab", models.LensCategory.ANTI_FATIGUE),
    ("myopia_control", "SCOPE Myoblock Metavision (Myoblock)", models.LensCategory.MYOPIA_CONTROL),
])
def test_subtype_search_succeeds_with_no_age_or_fitting_input_of_any_kind(db, use_mode, model_name, category):
    # There is no age/fitting field on Prescription or ProductSearchRequest
    # to even supply - this proves the search path works fully without one.
    _mk_row(db, "SCOPE", model_name, category)
    presc = _mk_presc(db, -2.0, -2.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode=use_mode))
    assert resp.availability_answer.code != "validation_error"
    assert any(r.model_name == model_name for g in resp.groups for r in g.results)


# --------------------------------------------------------------- not gated by Progressive ADD logic (12)
@pytest.mark.parametrize("use_mode,model_name,category", [
    ("anti_fatigue", "SCOPE Young Shabab", models.LensCategory.ANTI_FATIGUE),
    ("myopia_control", "SCOPE Myoblock Metavision (Myoblock)", models.LensCategory.MYOPIA_CONTROL),
])
def test_subtype_never_requires_add_and_ignores_unrelated_add(db, use_mode, model_name, category):
    _mk_row(db, "SCOPE", model_name, category)
    # No ADD entered at all - unlike bifocal/progressive, this must NOT be a validation error.
    presc_no_add = _mk_presc(db, -2.0, -2.0)
    resp_no_add = product_search.search(db, presc_no_add, schemas.ProductSearchRequest(use_mode=use_mode))
    assert resp_no_add.availability_answer.code != "validation_error"
    assert any(r.model_name == model_name for g in resp_no_add.groups for r in g.results)
    # An unrelated real ADD on the prescription must not exclude the row either
    # (no printed ADD/boost range exists for either catalog-proven product).
    presc_with_add = _mk_presc(db, -2.0, -2.0, od_add=2.0, os_add=2.0)
    resp_with_add = product_search.search(db, presc_with_add, schemas.ProductSearchRequest(use_mode=use_mode))
    assert any(r.model_name == model_name for g in resp_with_add.groups for r in g.results)


# --------------------------------------------------------------- existing Office behavior unchanged (13)
def test_office_use_mode_still_routes_exactly_as_before(db):
    _mk_row(db, "HOYA", "WorkSmart", models.LensCategory.OFFICE)
    presc = _mk_presc(db, -2.0, -2.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="office"))
    rows = [r for g in resp.groups for r in g.results if r.model_name == "WorkSmart"]
    assert len(rows) == 1
