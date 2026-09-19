"""Progressive ADD data-completeness fix (Catalog Truth Audit follow-up,
2026-09-19).

OWNER-CONFIRMED BUSINESS RULE (authoritative, not an inference): Progressive
ADD is available from +0.75D through +3.50D inclusive, in +0.25D steps, and
this is the Progressive ADD range used across every Progressive manufacturer
in this project. For HOYA specifically, the catalog note "Available
Additions From +0.75 To +3.50 Maximum" (repeated verbatim on every genuine
"...Progressive Lenses (RX)" page - Hoya_Price_List_2025_Updated.pdf pp.18,
19-20, 21, 22, 23, 24) means the Progressive lens Addition power range
itself, per the owner.

Audit findings this module's tests pin down (see app/progressive_add_evidence.py
for full evidence citations):
  - Maxxee's 34 Progressive PowerRange rows ALREADY have add_min=0.75/
    add_max=3.5 - no conflict with the owner rule, never touched.
  - HOYA's 12 genuinely-progressive families (each explicitly headed
    "Progressive Lenses (RX)" in the real catalog: Amplitude Plus(+PNX),
    Balansis(+PNX), Daynamic(+PNX), iD LifeStyle(+PNX), iD MyStyle(+PNX),
    iD MySelf(+PNX)) have NULL add_min/add_max on all 52 rows - the proven
    gap this module fixes.
  - HOYA's "Bi-Focal" (headed "Bi-Focal Lenses (RX)", p.27) and "Occupational"
    families (Supereader B, WorkSmart(+PNX), iD WorkStyle(+PNX); headed
    "Occupational Lenses (RX)", p.25-26, with fixed reading-distance specs,
    not a continuous ADD corridor) and "Mineral" (headed only "Lenses (RX)",
    p.28 - never proven "Progressive") are stored under category=PROGRESSIVE
    (a known pre-existing importer quirk) but are explicitly OUT of the
    owner's "Progressive only" rule and are never touched by this module.

Deliberately synthetic where isolating the rule (no PDF parsing); the live
release_runtime.db result is verified separately.
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
from app import models, database, schemas, product_search, progressive_add_evidence  # noqa: E402
from app import hoya_daynamic_evidence  # noqa: E402

from test_use_mode_technology import _mk_presc  # noqa: E402

_HOYA_PROGRESSIVE_FAMILIES = {
    "Amplitude Plus": 6, "Amplitude Plus PNX": 2,
    "Balansis": 7, "Balansis PNX": 2,
    "Daynamic": 6, "Daynamic PNX": 2,
    "iD LifeStyle": 7, "iD LifeStyle PNX": 2,
    "iD MyStyle": 7, "iD MyStyle PNX": 2,
    "iD MySelf": 7, "iD MySelf PNX": 2,
}
_HOYA_EXCLUDED_FAMILIES = {
    "Bi-Focal": 5, "Mineral": 10, "Supereader B": 2,
    "WorkSmart": 2, "WorkSmart PNX": 1, "iD WorkStyle": 2, "iD WorkStyle PNX": 1,
}


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


def _mk_company(db, name):
    co = models.Company(name=name, country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename="synthetic.pdf", file_path="synthetic.pdf",
                         status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)
    co._catalog = cat
    return co


def _mk_model(db, company, name, category=models.LensCategory.PROGRESSIVE):
    m = models.LensModel(company_id=company.id, name=name, category=category)
    db.add(m); db.commit(); db.refresh(m)
    return m


def _mk_variant(db, model, index_value=1.5):
    v = models.LensVariant(lens_model_id=model.id, material=models.MaterialType.CR39,
                           index_value=index_value, design_type=models.DesignType.SPHERICAL,
                           is_aspherical=False, price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    return v


def _mk_pricing_with_range(db, variant, catalog_id, *, add_min=None, add_max=None,
                            sph_min=-8.0, sph_max=8.0, cyl_min=-6.0, cyl_max=0.0):
    vp = models.VariantPricing(variant_id=variant.id, availability=models.PricingAvailability.RX,
                               price_pair=10000, currency="EGP", source_catalog_id=catalog_id,
                               power_eligibility=models.PowerEligibilityStatus.UNRESTRICTED)
    db.add(vp); db.commit(); db.refresh(vp)
    pr = models.PowerRange(lens_model_id=variant.lens_model_id, variant_id=variant.id,
                           pricing_id=vp.id, sph_min=sph_min, sph_max=sph_max,
                           cyl_min=cyl_min, cyl_max=cyl_max, add_min=add_min, add_max=add_max)
    db.add(pr); db.commit(); db.refresh(pr)
    return vp, pr


# --------------------------------------------------------------- central rule
def test_fills_null_add_bounds_on_a_generic_progressive_row(db):
    co = _mk_company(db, "SomeMaker")
    m = _mk_model(db, co, "SomeProgressive")
    v = _mk_variant(db, m)
    vp, pr = _mk_pricing_with_range(db, v, co._catalog.id)  # add_min/max default None
    result = progressive_add_evidence.reconcile(db)
    db.refresh(pr)
    assert pr.add_min == 0.75 and pr.add_max == 3.50
    assert result["updated"] == 1


def test_never_overwrites_existing_explicit_add_bounds(db):
    co = _mk_company(db, "Maxxee")
    m = _mk_model(db, co, "Maxxee")
    v = _mk_variant(db, m)
    vp, pr = _mk_pricing_with_range(db, v, co._catalog.id, add_min=0.75, add_max=3.5)
    progressive_add_evidence.reconcile(db)
    db.refresh(pr)
    assert pr.add_min == 0.75 and pr.add_max == 3.5


def test_never_overwrites_a_conflicting_explicit_range(db):
    # Explicit, more-specific catalog evidence must win over the general rule.
    co = _mk_company(db, "OddMaker")
    m = _mk_model(db, co, "OddProgressive")
    v = _mk_variant(db, m)
    vp, pr = _mk_pricing_with_range(db, v, co._catalog.id, add_min=1.00, add_max=3.00)
    progressive_add_evidence.reconcile(db)
    db.refresh(pr)
    assert pr.add_min == 1.00 and pr.add_max == 3.00


def test_never_touches_bifocal_category(db):
    co = _mk_company(db, "SomeMaker")
    m = _mk_model(db, co, "SomeBifocal", category=models.LensCategory.BIFOCAL)
    v = _mk_variant(db, m)
    vp, pr = _mk_pricing_with_range(db, v, co._catalog.id)
    progressive_add_evidence.reconcile(db)
    db.refresh(pr)
    assert pr.add_min is None and pr.add_max is None


def test_is_idempotent(db):
    co = _mk_company(db, "SomeMaker")
    m = _mk_model(db, co, "SomeProgressive")
    v = _mk_variant(db, m)
    vp, pr = _mk_pricing_with_range(db, v, co._catalog.id)
    progressive_add_evidence.reconcile(db)
    result2 = progressive_add_evidence.reconcile(db)
    assert result2["updated"] == 0
    db.refresh(pr)
    assert pr.add_min == 0.75 and pr.add_max == 3.50


# --------------------------------------------------------------- HOYA exclusions
@pytest.mark.parametrize("name", sorted(_HOYA_EXCLUDED_FAMILIES))
def test_hoya_occupational_bifocal_and_mineral_are_never_touched(db, name):
    co = _mk_company(db, "HOYA")
    m = _mk_model(db, co, name)  # category=PROGRESSIVE, matching the real importer quirk
    v = _mk_variant(db, m)
    vp, pr = _mk_pricing_with_range(db, v, co._catalog.id)
    progressive_add_evidence.reconcile(db)
    db.refresh(pr)
    assert pr.add_min is None and pr.add_max is None


@pytest.mark.parametrize("name", sorted(_HOYA_PROGRESSIVE_FAMILIES))
def test_hoya_genuine_progressive_families_get_the_add_range(db, name):
    co = _mk_company(db, "HOYA")
    m = _mk_model(db, co, name)
    v = _mk_variant(db, m)
    vp, pr = _mk_pricing_with_range(db, v, co._catalog.id)
    progressive_add_evidence.reconcile(db)
    db.refresh(pr)
    assert pr.add_min == 0.75 and pr.add_max == 3.50


# --------------------------------------------------------------- boundary tests
# Confirms the EXISTING, unmodified lens_matcher check enforces the range
# correctly once populated - never weakened, never bypassed, never special-cased.
@pytest.mark.parametrize("add,eligible", [
    (0.50, False), (0.75, True), (1.00, True),
    (2.00, True), (3.50, True), (3.75, False),
])
def test_add_boundaries_enforced_by_the_unmodified_matcher(db, add, eligible):
    co = _mk_company(db, "SomeMaker")
    m = _mk_model(db, co, "SomeProgressive")
    v = _mk_variant(db, m)
    vp, pr = _mk_pricing_with_range(db, v, co._catalog.id)
    progressive_add_evidence.reconcile(db)
    presc = _mk_presc(db, -2.0, -2.0, od_cyl=-1.0, os_cyl=-1.0, od_add=add, os_add=add)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="progressive"))
    rows = [r for g in resp.groups for r in g.results if r.lens_model_id == m.id]
    assert bool(rows) == eligible


# --------------------------------------------------------------- realistic HOYA e2e
def test_hoya_daynamic_reachable_with_use_mode_progressive_and_real_add(db):
    co = models.Company(name="HOYA", country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename="hoya.pdf", file_path="hoya.pdf",
                         status=models.CatalogStatus.CONFIRMED)
    db.add(cat); db.commit(); db.refresh(cat)
    coating = models.Coating(code="Super Hi Vision", name="Super Hi Vision")
    db.add(coating); db.commit()
    hoya_daynamic_evidence.reconcile(db)
    progressive_add_evidence.reconcile(db)

    presc = _mk_presc(db, -2.0, -2.0, od_cyl=-1.0, os_cyl=-1.0, od_add=2.0, os_add=2.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="progressive"))
    rows = [r for g in resp.groups for r in g.results if r.model_name.startswith("Daynamic")]
    assert len(rows) == 8


def test_hoya_amplitude_plus_and_balansis_reachable_after_fix(db):
    # Rule 10: existing HOYA Progressive families become reachable too, not
    # just Daynamic - proves the fix is central, not Daynamic-specific.
    co = models.Company(name="HOYA", country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename="hoya.pdf", file_path="hoya.pdf",
                         status=models.CatalogStatus.CONFIRMED)
    db.add(cat); db.commit(); db.refresh(cat)
    coating = models.Coating(code="Hi Vision Aqua", name="Hi Vision Aqua")
    db.add(coating); db.commit()
    for name in ("Amplitude Plus", "Balansis"):
        m = _mk_model(db, co, name)
        v = _mk_variant(db, m, index_value=1.5)
        vp = models.VariantPricing(variant_id=v.id, coating_id=coating.id,
                                   availability=models.PricingAvailability.RX,
                                   price_pair=10000, currency="EGP", market_scope="Out Of Egypt",
                                   source_catalog_id=cat.id,
                                   power_eligibility=models.PowerEligibilityStatus.UNRESTRICTED)
        db.add(vp); db.commit(); db.refresh(vp)
        pr = models.PowerRange(lens_model_id=m.id, variant_id=v.id, pricing_id=vp.id,
                               sph_min=-8.0, sph_max=12.0, cyl_min=-6.0, cyl_max=0.0,
                               total_power_min=-8.0, total_power_max=6.0, max_cyl_abs=6.0)
        db.add(pr); db.commit()
    progressive_add_evidence.reconcile(db)

    presc = _mk_presc(db, -2.0, -2.0, od_cyl=-1.0, os_cyl=-1.0, od_add=2.0, os_add=2.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="progressive"))
    names = {r.model_name for g in resp.groups for r in g.results}
    assert {"Amplitude Plus", "Balansis"} <= names
