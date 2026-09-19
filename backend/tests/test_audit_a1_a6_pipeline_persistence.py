"""Rebuild-survival proof for Catalog Truth Audit (2026-09-18) Section A
items A1-A6.

Exercises the REAL ingestion pipeline (crud.confirm_catalog_commercial, via
crud._prepare_extraction_row) with synthetic CatalogExtraction rows shaped
exactly like a fresh PDF extraction+review would produce - i.e. the same raw
wrong values release_runtime.db had before the one-time manual SQL patch
(see test_audit_a1_a6_data_corrections.py, which checks that live db).
A clean rebuild is: drop the db, re-run extraction/review/confirm from the
source PDFs. These tests stand in for that using the same
CatalogExtraction/modified_data shape the real pipeline consumes, proving
the six corrections now happen automatically and idempotently, in source -
never as a manual SQL step.

Deliberately synthetic (mirrors test_phase2_import_confirmation.py's own
_ext() builder pattern) - no PDF parsing, no dependency on the live db.
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
from app import models, crud, database  # noqa: E402


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


def _company(db, name):
    c = models.Company(name=name)
    db.add(c); db.commit(); db.refresh(c)
    return c


def _catalog(db, company):
    cat = models.Catalog(company_id=company.id, filename="c.pdf", file_path="/x/c.pdf",
                         status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)
    return cat


def _coating(db, code):
    c = models.Coating(code=code, name=code)
    db.add(c); db.commit(); db.refresh(c)
    return c


def _ext(db, catalog, *, name, price, availability, index, material="CR39",
         category=None, design_type="spherical", is_aspherical=False,
         design_variant=None, market_scope=None, coating_id=None,
         sph_min=-6.0, sph_max=6.0, cyl_min=-2.0, cyl_max=0.0):
    """Mirrors exactly what a fresh parser extraction + reviewer-accepted
    modified_data overlay looks like - both extracted_* and modified_data
    carry the SAME raw (pre-correction) values, as they would for a row the
    reviewer simply approved as-is."""
    md = {"name": name, "material": material, "index": index, "availability": availability,
          "price": price, "design_type": design_type, "is_aspherical": is_aspherical}
    for k, v in (("design_variant", design_variant), ("category", category),
                 ("market_scope", market_scope), ("sph_min", sph_min), ("sph_max", sph_max),
                 ("cyl_min", cyl_min), ("cyl_max", cyl_max)):
        if v is not None:
            md[k] = v
    coating_status = (models.CoatingExtractionStatus.RESOLVED if coating_id is not None
                       else models.CoatingExtractionStatus.EXPLICIT_NONE)
    row = models.CatalogExtraction(
        catalog_id=catalog.id, extracted_name=name, extracted_material=material,
        extracted_index=index, extracted_availability=availability, extracted_price=price,
        sph_min=sph_min, sph_max=sph_max, cyl_min=cyl_min, cyl_max=cyl_max,
        coating_extraction_status=coating_status, coating_id=coating_id,
        modified_data=md, status="confirmed")
    db.add(row); db.commit(); db.refresh(row)
    return row


def _variants(db, company_id):
    return (db.query(models.LensVariant).join(models.LensModel)
            .filter(models.LensModel.company_id == company_id).all())


def _pricings(db, company_id):
    return (db.query(models.VariantPricing).join(models.LensVariant).join(models.LensModel)
            .filter(models.LensModel.company_id == company_id).all())


# --------------------------------------------------------------- A1 (ZEISS)
def test_a1_zeiss_1_53_ingests_as_trivex(db):
    co = _company(db, "ZEISS")
    cat = _catalog(db, co)
    _ext(db, cat, name="ClearView", price=500, availability="stock", index=1.53)
    result = crud.confirm_catalog_commercial(db, cat.id)
    assert result["status"] == "confirmed"
    [variant] = _variants(db, co.id)
    assert variant.material == models.MaterialType.TRIVEX


# --------------------------------------------------------------- A2 (Pixel)
def test_a2_pixel_1_53_ingests_as_trivex(db):
    co = _company(db, "Pixel")
    cat = _catalog(db, co)
    _ext(db, cat, name="Pixel", price=500, availability="stock", index=1.53)
    crud.confirm_catalog_commercial(db, cat.id)
    [variant] = _variants(db, co.id)
    assert variant.material == models.MaterialType.TRIVEX


# --------------------------------------------------------------- A3 (HOYA Mineral)
def test_a3_hoya_mineral_ingests_as_glass(db):
    co = _company(db, "HOYA")
    cat = _catalog(db, co)
    _ext(db, cat, name="Mineral", price=1000, availability="stock", index=1.6,
         category="progressive")
    crud.confirm_catalog_commercial(db, cat.id)
    [variant] = _variants(db, co.id)
    assert variant.material == models.MaterialType.GLASS


# --------------------------------------------------------------- A6 (Pixel design_type)
def test_a6_pixel_single_vision_base_sku_ingests_as_aspherical(db):
    co = _company(db, "Pixel")
    cat = _catalog(db, co)
    for idx in (1.56, 1.61, 1.67):
        _ext(db, cat, name="Pixel", price=1000 + idx, availability="stock", index=idx)
    crud.confirm_catalog_commercial(db, cat.id)
    variants = _variants(db, co.id)
    assert len(variants) == 3
    assert all(v.design_type == models.DesignType.ASPHERICAL and v.is_aspherical for v in variants)


def test_a6_ingestion_does_not_generalize_beyond_proven_scope(db):
    co = _company(db, "Pixel")
    cat = _catalog(db, co)
    _ext(db, cat, name="Opal", price=100, availability="stock", index=1.56)
    _ext(db, cat, name="Pixel", price=200, availability="stock", index=1.56,
         design_variant="Free Form")
    _ext(db, cat, name="Pixel", price=300, availability="stock", index=1.74)
    crud.confirm_catalog_commercial(db, cat.id)
    variants = _variants(db, co.id)
    assert len(variants) == 3
    assert all(v.design_type == models.DesignType.SPHERICAL and not v.is_aspherical for v in variants)


# --------------------------------------------------------------- A4 (Maxxee market_scope)
def test_a4_maxxee_1_6_asph_hmc_plus_stock_ingests_as_out_of_egypt(db):
    co = _company(db, "Maxxee")
    cat = _catalog(db, co)
    coating = _coating(db, "H.M.C+")
    _ext(db, cat, name="Maxxee", price=2450, availability="stock", index=1.6,
         design_type="aspherical", is_aspherical=True, market_scope="Egypt",
         coating_id=coating.id)
    crud.confirm_catalog_commercial(db, cat.id)
    [vp] = _pricings(db, co.id)
    assert vp.market_scope == "Out Of Egypt"


def test_a4_ingestion_does_not_generalize_to_sibling_index(db):
    co = _company(db, "Maxxee")
    cat = _catalog(db, co)
    coating = _coating(db, "H.M.C+")
    _ext(db, cat, name="Maxxee", price=2350, availability="stock", index=1.56,
         design_type="aspherical", is_aspherical=True, market_scope="Egypt",
         coating_id=coating.id)
    crud.confirm_catalog_commercial(db, cat.id)
    [vp] = _pricings(db, co.id)
    assert vp.market_scope == "Egypt"


def test_a4_ingestion_does_not_generalize_to_spherical_sibling(db):
    # Review finding: a Spherical sibling at the exact same
    # company/coating/index/availability/market_scope is a different, unproven
    # identity and must stay 'Egypt'.
    co = _company(db, "Maxxee")
    cat = _catalog(db, co)
    coating = _coating(db, "H.M.C+")
    _ext(db, cat, name="Maxxee", price=2300, availability="stock", index=1.6,
         design_type="spherical", is_aspherical=False, market_scope="Egypt",
         coating_id=coating.id)
    crud.confirm_catalog_commercial(db, cat.id)
    [vp] = _pricings(db, co.id)
    assert vp.market_scope == "Egypt"


def test_a4_attach_range_matches_corrected_market_scope(db):
    """Review finding: attach_range_to_existing_pricing must use the SAME
    centralized corrected market_scope when matching an existing
    VariantPricing row - not a stale pre-correction 'Egypt' value it computed
    independently. A fresh graphical/G3 range extraction for the exact same
    identity (raw, pre-correction market_scope, exactly as a clean rebuild's
    second extraction pass would produce it) must still find and attach to
    the already-corrected 'Out Of Egypt' pricing row."""
    co = _company(db, "Maxxee")
    cat = _catalog(db, co)
    coating = _coating(db, "H.M.C+")
    _ext(db, cat, name="Maxxee", price=2450, availability="stock", index=1.6,
         design_type="aspherical", is_aspherical=True, market_scope="Egypt",
         coating_id=coating.id)
    crud.confirm_catalog_commercial(db, cat.id)
    [vp] = _pricings(db, co.id)
    assert vp.market_scope == "Out Of Egypt"  # sanity: A4 already applied

    range_ext = _ext(db, cat, name="Maxxee", price=2450, availability="stock", index=1.6,
                      design_type="aspherical", is_aspherical=True, market_scope="Egypt",
                      coating_id=coating.id, sph_min=-6.0, sph_max=6.0, cyl_min=-2.0, cyl_max=0.0)
    result = crud.attach_range_to_existing_pricing(db, range_ext.id)
    assert "error" not in result, result.get("error")
    assert result["power_range_ids"]


# --------------------------------------------------------------- A5 (Pixel Astro price)
def test_a5_pixel_astro_1_56_stock_egypt_ingests_at_proven_rate(db):
    co = _company(db, "Pixel")
    cat = _catalog(db, co)
    coating = _coating(db, "Astro")
    for price, sph_min, sph_max, cyl_min, cyl_max in [
        (1300, -6.0, 0.0, -2.0, 0.0),
        (1400, -6.0, 0.0, -4.0, 0.0),
        (1300, 0.0, 6.0, -2.0, 0.0),
    ]:
        _ext(db, cat, name="Pixel", price=price, availability="stock", index=1.56,
             market_scope="Egypt", coating_id=coating.id,
             sph_min=sph_min, sph_max=sph_max, cyl_min=cyl_min, cyl_max=cyl_max)
    result = crud.confirm_catalog_commercial(db, cat.id)
    assert result["priced_rows"] == 3
    prices = sorted(vp.price_pair for vp in _pricings(db, co.id))
    # Exactly the 3 catalog-proven rows, remapped to Astro's own rate - never
    # a 4th invented band.
    assert prices == [Decimal("900.00"), Decimal("900.00"), Decimal("1000.00")]


def test_a5_ingestion_does_not_generalize_to_other_astro_rows(db):
    # variant_id 186 (index 1.5) legitimately has its own 700/800/900/1000
    # Astro/Stock/Egypt bands in the real catalog - untouched by the 1.56-only
    # A5 correction.
    co = _company(db, "Pixel")
    cat = _catalog(db, co)
    coating = _coating(db, "Astro")
    _ext(db, cat, name="Pixel", price=1300, availability="stock", index=1.5,
         market_scope="Egypt", coating_id=coating.id)
    crud.confirm_catalog_commercial(db, cat.id)
    [vp] = _pricings(db, co.id)
    assert vp.price_pair == Decimal("1300.00")
