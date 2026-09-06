"""Phase 2 - legacy commercial-write-path lockdown.

Proves that after Phase 2 the ONLY registered public path able to create
authoritative commercial pricing/history is POST /pdf-import/bulk-confirm/{id}.
"""
import os
import sys
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database import Base  # noqa: E402
from app import models, schemas, crud, database  # noqa: E402
from app.routers import lens_models as lm_router  # noqa: E402
from app.routers import pdf_import as pi_router  # noqa: E402


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


def _company(db, name="ACME"):
    c = models.Company(name=name)
    db.add(c); db.commit(); db.refresh(c)
    return c


def _model(db, company, name="M1"):
    m = models.LensModel(company_id=company.id, name=name,
                         category=models.LensCategory.SINGLE_VISION)
    db.add(m); db.commit(); db.refresh(m)
    return m


def _catalog(db, company):
    cat = models.Catalog(company_id=company.id, filename="c.pdf", file_path="/x",
                         status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)
    return cat


def _confirmed_ext(db, catalog, name="M1", price=100.0):
    e = models.CatalogExtraction(
        catalog_id=catalog.id, extracted_name=name, extracted_material="CR39",
        extracted_index=1.5, extracted_availability="stock", extracted_price=price,
        sph_min=-4.0, sph_max=0.0,
        coating_extraction_status=models.CoatingExtractionStatus.EXPLICIT_NONE,
        modified_data={"name": name, "material": "CR39", "index": 1.5,
                       "availability": "stock", "price": price,
                       "sph_min": -4.0, "sph_max": 0.0},
        status="confirmed",
    )
    db.add(e); db.commit(); db.refresh(e)
    return e


# ---------------------------------------------------------------------------
# Route inventory
# ---------------------------------------------------------------------------
def _api_routes(mod):
    return [r for r in mod.router.routes if isinstance(r, APIRoute)]


def test_route_inventory_no_variant_or_range_mutation_endpoints():
    lm = _api_routes(lm_router)
    variant_routes = [(sorted(r.methods), r.path, r.endpoint.__name__)
                      for r in lm if "variants" in r.path]
    range_routes = [(sorted(r.methods), r.path, r.endpoint.__name__)
                    for r in lm if "power-ranges" in r.path]

    # variants: exactly one writer (POST create_variant, structural) + one GET
    variant_methods = {m for methods, _, _ in variant_routes for m in methods}
    assert variant_methods <= {"GET", "POST"}
    assert not (variant_methods & {"PUT", "PATCH", "DELETE"})
    assert any(mm == ["POST"] and name == "create_variant" for mm, _, name in variant_routes)

    # power-ranges: no mutation writer survives except the disabled POST + a GET
    range_methods = {m for methods, _, _ in range_routes for m in methods}
    assert range_methods <= {"GET", "POST"}
    assert not (range_methods & {"PUT", "PATCH", "DELETE"})

    # pdf-import: the only commercial writer endpoint present
    pi_names = {r.endpoint.__name__ for r in _api_routes(pi_router)}
    assert "bulk_confirm" in pi_names
    assert "bulk_upload_power_ranges" in pi_names  # present but disabled (see test below)


def test_crud_manual_pricing_mutators_are_not_wired_to_any_route():
    # these helpers exist but must not be reachable through a registered endpoint
    wired = []
    for mod in (lm_router, pi_router):
        src = ""
        import inspect
        src = inspect.getsource(mod)
        for banned in ("update_lens_variant", "delete_power_range", "create_power_range(db",
                       "create_lens_variant(db"):
            if banned in src:
                wired.append((mod.__name__, banned))
    # create_lens_variant(db is still used by the *structural* variant route - allowed;
    # the commercial mutators must not appear
    assert not any(b in ("update_lens_variant", "delete_power_range") for _, b in wired)


# ---------------------------------------------------------------------------
# B. LensVariant create cannot write an authoritative legacy price
# ---------------------------------------------------------------------------
def test_variant_create_rejects_real_price(db):
    company = _company(db)
    model = _model(db, company)
    with pytest.raises(HTTPException) as exc:
        lm_router.create_variant(
            model_id=model.id,
            variant=schemas.LensVariantCreate(
                lens_model_id=model.id, material=schemas.MaterialType.CR39,
                index_value=1.5, price=250.0,
            ),
            db=db,
        )
    assert exc.value.status_code == 422
    assert db.query(models.LensVariant).count() == 0
    assert db.query(models.VariantPricing).count() == 0


def test_variant_create_structural_is_allowed_but_non_commercial(db):
    company = _company(db)
    model = _model(db, company)
    out = lm_router.create_variant(
        model_id=model.id,
        variant=schemas.LensVariantCreate(
            lens_model_id=model.id, material=schemas.MaterialType.CR39,
            index_value=1.5, price=0.0, currency="USD",
            availability=schemas.LensAvailability.BOTH,
        ),
        db=db,
    )
    row = db.query(models.LensVariant).one()
    assert row.price == 0.0                              # legacy price not written
    assert row.currency == "EGP"                         # forced placeholder
    assert row.availability == models.LensAvailability.STOCK   # caller's BOTH ignored
    assert db.query(models.VariantPricing).count() == 0  # no commercial pricing created


# ---------------------------------------------------------------------------
# C. Public PowerRange creation: deterministic 410, never 500, no orphan range
# ---------------------------------------------------------------------------
def test_power_range_create_endpoint_is_disabled_410(db):
    company = _company(db)
    model = _model(db, company)
    with pytest.raises(HTTPException) as exc:
        lm_router.create_power_range(model_id=model.id, db=db)
    assert exc.value.status_code == 410
    assert db.query(models.PowerRange).count() == 0


# ---------------------------------------------------------------------------
# D. No registered endpoint can mutate a PowerRange tied to commercial pricing
# ---------------------------------------------------------------------------
def test_no_endpoint_can_mutate_commercial_power_range(db):
    company = _company(db)
    cat = _catalog(db, company)
    _confirmed_ext(db, cat, name="Prod", price=100.0)
    crud.confirm_catalog_commercial(db, cat.id)

    pr = db.query(models.PowerRange).one()
    assert pr.pricing_id is not None  # it belongs to commercial pricing

    # there is simply no registered PUT/PATCH/DELETE route for power ranges
    all_routes = _api_routes(lm_router) + _api_routes(pi_router)
    mutating = [
        (sorted(r.methods), r.path)
        for r in all_routes
        if ("power-range" in r.path or "power_range" in r.path)
        and (r.methods & {"PUT", "PATCH", "DELETE"})
    ]
    assert mutating == []


# ---------------------------------------------------------------------------
# E. /pdf-import/bulk-upload stays 410
# ---------------------------------------------------------------------------
def test_bulk_upload_still_410(db):
    with pytest.raises(HTTPException) as exc:
        pi_router.bulk_upload_power_ranges(
            data=schemas.BulkUploadRequest(company_id=1, ranges=[]), db=db
        )
    assert exc.value.status_code == 410


# ---------------------------------------------------------------------------
# A. bulk-confirm remains the ONLY path that produces VariantPricing
# ---------------------------------------------------------------------------
def test_bulk_confirm_is_the_only_commercial_pricing_writer(db):
    company = _company(db)
    model = _model(db, company)
    cat = _catalog(db, company)
    _confirmed_ext(db, cat, name="M1", price=100.0)

    # every legacy write attempt is blocked and writes no pricing
    with pytest.raises(HTTPException):
        lm_router.create_variant(
            model_id=model.id,
            variant=schemas.LensVariantCreate(
                lens_model_id=model.id, material=schemas.MaterialType.CR39,
                index_value=1.5, price=999.0),
            db=db)
    with pytest.raises(HTTPException):
        lm_router.create_power_range(model_id=model.id, db=db)
    with pytest.raises(HTTPException):
        pi_router.bulk_upload_power_ranges(
            data=schemas.BulkUploadRequest(company_id=company.id, ranges=[]), db=db)
    assert db.query(models.VariantPricing).count() == 0

    # only bulk-confirm creates authoritative pricing
    crud.confirm_catalog_commercial(db, cat.id)
    prices = db.query(models.VariantPricing).all()
    assert len(prices) == 1
    assert prices[0].price_pair == Decimal("100.00")
    assert prices[0].effective_to is None
