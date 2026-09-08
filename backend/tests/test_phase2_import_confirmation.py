"""Phase 2 - commercial import / confirmation wiring.

Exercised against the real crud + router code on a fresh in-memory SQLite
database per test (same FK-enforcement hook the application registers).
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
from app.routers import pdf_import  # noqa: E402


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    event.listen(engine, "connect", database._set_sqlite_pragma)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# ----- builders --------------------------------------------------------------
def _company(db, name="ACME"):
    c = models.Company(name=name)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _catalog(db, company, status=models.CatalogStatus.DRAFT):
    cat = models.Catalog(
        company_id=company.id, filename="c.pdf", file_path="/x/c.pdf", status=status
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def _ext(
    db,
    catalog,
    *,
    name="Model One",
    price=100.0,
    availability="stock",
    coating_status=models.CoatingExtractionStatus.EXPLICIT_NONE,
    coating_id=None,
    extracted_coating=None,
    material="CR39",
    index=1.50,
    design_type="spherical",
    is_aspherical=False,
    design_variant=None,
    color_variant=None,
    market_scope=None,
    sph_min=None,
    sph_max=None,
    cyl_min=None,
    cyl_max=None,
    add_min=None,
    add_max=None,
    review_status="confirmed",
):
    md = {"name": name, "material": material, "index": index, "availability": availability,
          "price": price, "design_type": design_type, "is_aspherical": is_aspherical}
    for k, v in (
        ("design_variant", design_variant), ("color_variant", color_variant),
        ("market_scope", market_scope), ("sph_min", sph_min), ("sph_max", sph_max),
        ("cyl_min", cyl_min), ("cyl_max", cyl_max), ("add_min", add_min), ("add_max", add_max),
    ):
        if v is not None:
            md[k] = v
    row = models.CatalogExtraction(
        catalog_id=catalog.id,
        extracted_name=name,
        extracted_material=material,
        extracted_index=index,
        extracted_availability=availability,
        extracted_price=price,
        sph_min=sph_min, sph_max=sph_max, cyl_min=cyl_min, cyl_max=cyl_max,
        add_min=add_min, add_max=add_max,
        coating_extraction_status=coating_status,
        coating_id=coating_id,
        extracted_coating=extracted_coating,
        modified_data=md,
        status=review_status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _current(db, company_id):
    return crud._company_current_pricing_rows(db, company_id)


def _all_pricing(db):
    return db.query(models.VariantPricing).order_by(models.VariantPricing.id).all()


# ===========================================================================
# power_scope builder
# ===========================================================================
def test_power_scope_builder_is_deterministic_and_normalised():
    a = crud.build_power_scope(-6, 0)
    assert a == crud.build_power_scope(-6.0, 0.0)
    assert a == crud.build_power_scope(-6.00, 0.00)
    assert a == crud.build_power_scope(0.0, -6.0)          # order independent
    assert a != crud.build_power_scope(0, 4)               # different range -> different scope
    assert crud.build_power_scope(None, None) is None
    assert crud.build_power_scope(0, 0) is None


# ===========================================================================
# A. valid catalog confirm
# ===========================================================================
def test_A_valid_catalog_confirm(db):
    company = _company(db)
    cat = _catalog(db, company)
    _ext(db, cat, name="Aspire", price=250.0, availability="stock",
         sph_min=-6.0, sph_max=2.0, cyl_min=-2.0, cyl_max=0.0)

    result = crud.confirm_catalog_commercial(db, cat.id, reviewed_by="qa")

    assert result["status"] == "confirmed"
    assert result["priced_rows"] == 1
    db.refresh(cat)
    assert cat.status == models.CatalogStatus.CONFIRMED
    assert cat.confirmed_by == "qa"

    prices = _all_pricing(db)
    assert len(prices) == 1
    p = prices[0]
    assert p.effective_to is None
    assert p.availability == models.PricingAvailability.STOCK
    assert p.source_catalog_id == cat.id
    assert isinstance(p.price_pair, Decimal) and p.price_pair == Decimal("250.00")
    assert db.query(models.PowerRange).filter_by(pricing_id=p.id).count() == 1


# ===========================================================================
# B. replacement catalog preserves history  (mandatory scenario, item 6)
# ===========================================================================
def test_B_replacement_catalog_preserves_history(db):
    company = _company(db)

    v1 = _catalog(db, company)
    _ext(db, v1, name="Uno", price=2500.0, availability="stock",
         sph_min=-6.0, sph_max=0.0)                       # Scope A
    _ext(db, v1, name="Uno", price=5500.0, availability="stock",
         sph_min=0.0, sph_max=4.0)                        # Scope B
    crud.confirm_catalog_commercial(db, v1.id)

    scope_a = crud.build_power_scope(-6.0, 0.0)
    scope_b = crud.build_power_scope(0.0, 4.0)

    v2 = _catalog(db, company)
    _ext(db, v2, name="Uno", price=2700.0, availability="stock",
         sph_min=-6.0, sph_max=0.0)                       # Scope A only
    crud.confirm_catalog_commercial(db, v2.id)

    current = _current(db, company.id)
    assert {(c.power_scope, c.price_pair) for c in current} == {(scope_a, Decimal("2700.00"))}

    history = [(p.power_scope, p.price_pair, p.effective_to is None) for p in _all_pricing(db)]
    assert (scope_a, Decimal("2500.00"), False) in history      # closed
    assert (scope_b, Decimal("5500.00"), False) in history      # closed, not re-created
    assert (scope_a, Decimal("2700.00"), True) in history       # new current
    assert all(not (p.power_scope == scope_b and p.effective_to is None) for p in _all_pricing(db))

    db.refresh(v1)
    db.refresh(v2)
    assert v1.status == models.CatalogStatus.SUPERSEDED
    assert v2.status == models.CatalogStatus.CONFIRMED


# ===========================================================================
# C. missing old SKU / range becomes non-current
# ===========================================================================
def test_C_missing_old_sku_becomes_non_current(db):
    company = _company(db)
    v1 = _catalog(db, company)
    _ext(db, v1, name="Keeps", price=100.0, sph_min=-4.0, sph_max=0.0)
    _ext(db, v1, name="Drops", price=200.0, sph_min=-4.0, sph_max=0.0)
    crud.confirm_catalog_commercial(db, v1.id)
    assert len(_current(db, company.id)) == 2

    v2 = _catalog(db, company)
    _ext(db, v2, name="Keeps", price=110.0, sph_min=-4.0, sph_max=0.0)
    crud.confirm_catalog_commercial(db, v2.id)

    current = _current(db, company.id)
    assert len(current) == 1
    kept_model = db.query(models.LensModel).filter_by(name="Keeps").one()
    assert current[0].variant.lens_model_id == kept_model.id
    assert current[0].price_pair == Decimal("110.00")
    # "Drops" pricing still exists but only as history
    drops_model = db.query(models.LensModel).filter_by(name="Drops").one()
    drops_prices = [p for p in _all_pricing(db)
                    if p.variant.lens_model_id == drops_model.id]
    assert drops_prices and all(p.effective_to is not None for p in drops_prices)


# ===========================================================================
# D. RX without PowerRange confirms
# ===========================================================================
def test_D_rx_without_power_range_confirms(db):
    company = _company(db)
    cat = _catalog(db, company)
    _ext(db, cat, name="RxOnly", price=400.0, availability="rx")  # no sph range

    crud.confirm_catalog_commercial(db, cat.id)

    prices = _all_pricing(db)
    assert len(prices) == 1
    assert prices[0].availability == models.PricingAvailability.RX
    assert prices[0].power_scope is None
    assert db.query(models.PowerRange).count() == 0


# ===========================================================================
# E. STOCK without PowerRange blocks the whole catalog
# ===========================================================================
def test_E_stock_without_power_range_is_parked_not_catalog_blocking(db):
    # Batch 1: a minority of unresolved rows must NOT zero out the good rows.
    # The STOCK-without-range row is PARKED (back to needs_review with an exact
    # reason); the good row still confirms atomically.
    company = _company(db)
    cat = _catalog(db, company)
    good = _ext(db, cat, name="Good", price=100.0, availability="stock",
                sph_min=-4.0, sph_max=0.0)
    bad = _ext(db, cat, name="BadStock", price=100.0, availability="stock")  # no range

    result = crud.confirm_catalog_commercial(db, cat.id)

    assert result["confirmed"] == 1
    assert result["skipped_unresolved"] == 1
    assert any(p["extraction_id"] == bad.id and "STOCK requires PowerRange" in p["reason"]
               for p in result["parked"])

    prices = _all_pricing(db)
    assert len(prices) == 1                             # only the good row
    db.refresh(cat); db.refresh(bad)
    assert cat.status == models.CatalogStatus.CONFIRMED
    assert bad.status == "needs_review"
    assert "STOCK requires PowerRange" in (bad.review_notes or "")


# ===========================================================================
# F. explicit_none coating confirms
# ===========================================================================
def test_F_explicit_none_coating_confirms(db):
    company = _company(db)
    cat = _catalog(db, company)
    _ext(db, cat, name="NoCoat", price=100.0, sph_min=-4.0, sph_max=0.0,
         coating_status=models.CoatingExtractionStatus.EXPLICIT_NONE)

    crud.confirm_catalog_commercial(db, cat.id)

    prices = _all_pricing(db)
    assert len(prices) == 1
    assert prices[0].coating_id is None


# ===========================================================================
# G. not_found coating blocks the whole catalog
# ===========================================================================
def test_G_not_found_coating_row_is_parked_not_catalog_blocking(db):
    company = _company(db)
    cat = _catalog(db, company)
    _ext(db, cat, name="Ok", price=100.0, sph_min=-4.0, sph_max=0.0)
    bad = _ext(db, cat, name="NoCoating", price=100.0, sph_min=-4.0, sph_max=0.0,
               coating_status=models.CoatingExtractionStatus.NOT_FOUND)

    result = crud.confirm_catalog_commercial(db, cat.id)

    assert result["confirmed"] == 1 and result["skipped_unresolved"] == 1
    assert any(p["extraction_id"] == bad.id for p in result["parked"])
    assert len(_all_pricing(db)) == 1
    db.refresh(cat); db.refresh(bad)
    assert cat.status == models.CatalogStatus.CONFIRMED
    assert bad.status == "needs_review"


# ===========================================================================
# H. needs_review / unresolved extraction blocks the whole catalog
# ===========================================================================
def test_H_unresolved_review_state_row_is_parked_not_catalog_blocking(db):
    company = _company(db)
    cat = _catalog(db, company)
    _ext(db, cat, name="Ready", price=100.0, sph_min=-4.0, sph_max=0.0)
    pend = _ext(db, cat, name="Pending", price=100.0, sph_min=-4.0, sph_max=0.0,
                review_status="pending")

    result = crud.confirm_catalog_commercial(db, cat.id)

    assert result["confirmed"] == 1 and result["skipped_unresolved"] == 1
    assert any(p["extraction_id"] == pend.id and "not review-approved" in p["reason"]
               for p in result["parked"])
    assert len(_all_pricing(db)) == 1
    db.refresh(cat)
    assert cat.status == models.CatalogStatus.CONFIRMED


# ===========================================================================
# I. two designs with different prices stay independent
# ===========================================================================
def test_I_two_designs_independent(db):
    company = _company(db)
    cat = _catalog(db, company)
    _ext(db, cat, name="DualDesign", price=100.0, sph_min=-4.0, sph_max=0.0,
         design_variant="Core")
    _ext(db, cat, name="DualDesign", price=200.0, sph_min=-4.0, sph_max=0.0,
         design_variant="Premium")

    crud.confirm_catalog_commercial(db, cat.id)

    current = _current(db, company.id)
    assert len(current) == 2
    by_dv = {c.variant.design_variant: c.price_pair for c in current}
    assert by_dv == {"Core": Decimal("100.00"), "Premium": Decimal("200.00")}
    assert len({c.variant_id for c in current}) == 2


# ===========================================================================
# J. two colour variants stay independent
# ===========================================================================
def test_J_two_color_variants_independent(db):
    company = _company(db)
    cat = _catalog(db, company)
    _ext(db, cat, name="DualColor", price=100.0, sph_min=-4.0, sph_max=0.0,
         color_variant="Clear")
    _ext(db, cat, name="DualColor", price=150.0, sph_min=-4.0, sph_max=0.0,
         color_variant="Transmatic/G/B")

    crud.confirm_catalog_commercial(db, cat.id)

    current = _current(db, company.id)
    assert {c.variant.color_variant: c.price_pair for c in current} == {
        "Clear": Decimal("100.00"), "Transmatic/G/B": Decimal("150.00")
    }
    assert len({c.variant_id for c in current}) == 2


# ===========================================================================
# K. two markets stay independent
# ===========================================================================
def test_K_two_markets_independent(db):
    company = _company(db)
    cat = _catalog(db, company)
    _ext(db, cat, name="DualMarket", price=100.0, sph_min=-4.0, sph_max=0.0,
         market_scope="retail")
    _ext(db, cat, name="DualMarket", price=90.0, sph_min=-4.0, sph_max=0.0,
         market_scope="wholesale")

    crud.confirm_catalog_commercial(db, cat.id)

    current = _current(db, company.id)
    assert {c.market_scope: c.price_pair for c in current} == {
        "retail": Decimal("100.00"), "wholesale": Decimal("90.00")
    }
    # same variant, two prices
    assert len({c.variant_id for c in current}) == 1


# ===========================================================================
# L. two STOCK power scopes stay independent
# ===========================================================================
def test_L_two_stock_power_scopes_independent(db):
    company = _company(db)
    cat = _catalog(db, company)
    _ext(db, cat, name="DualScope", price=100.0, availability="stock",
         sph_min=-6.0, sph_max=0.0)
    _ext(db, cat, name="DualScope", price=120.0, availability="stock",
         sph_min=0.0, sph_max=4.0)

    crud.confirm_catalog_commercial(db, cat.id)

    current = _current(db, company.id)
    assert len(current) == 2
    assert {c.power_scope for c in current} == {
        crud.build_power_scope(-6.0, 0.0), crud.build_power_scope(0.0, 4.0)
    }
    assert len({c.variant_id for c in current}) == 1
    assert db.query(models.PowerRange).count() == 2


# ===========================================================================
# M. true duplicate commercial identity blocks confirmation
# ===========================================================================
def test_M_true_duplicate_identity_collapses_to_one_pricing(db):
    # Batch 1: an EXACT duplicate (same identity + same price + same power_scope)
    # collapses to one pricing; the extra row is parked, the catalog confirms.
    company = _company(db)
    cat = _catalog(db, company)
    _ext(db, cat, name="Same", price=100.0, sph_min=-4.0, sph_max=0.0,
         design_variant="Core", color_variant="Clear", market_scope="retail")
    dup = _ext(db, cat, name="Same", price=100.0, sph_min=-4.0, sph_max=0.0,
               design_variant="Core", color_variant="Clear", market_scope="retail")

    result = crud.confirm_catalog_commercial(db, cat.id)

    assert result["confirmed"] == 1
    assert result["true_duplicates_collapsed"] == 1
    assert result["conflicts"] == 0
    assert any(p["extraction_id"] == dup.id and "exact duplicate" in p["reason"]
               for p in result["parked"])
    assert len(_all_pricing(db)) == 1
    db.refresh(cat)
    assert cat.status == models.CatalogStatus.CONFIRMED


def test_M2_price_conflict_parks_both_rows(db):
    # Same commercial identity, DIFFERENT price -> a genuine conflict. Neither
    # row is chosen / merged / averaged; both are parked; the rest confirms.
    company = _company(db)
    cat = _catalog(db, company)
    _ext(db, cat, name="Clean", price=50.0, sph_min=-2.0, sph_max=0.0)
    a = _ext(db, cat, name="Same", price=100.0, sph_min=-4.0, sph_max=0.0,
             design_variant="Core", color_variant="Clear", market_scope="retail")
    b = _ext(db, cat, name="Same", price=200.0, sph_min=-4.0, sph_max=0.0,
             design_variant="Core", color_variant="Clear", market_scope="retail")

    result = crud.confirm_catalog_commercial(db, cat.id)

    assert result["confirmed"] == 1                     # only "Clean"
    assert result["conflicts"] == 2                     # both a and b parked
    parked_ids = {p["extraction_id"] for p in result["parked"] if "price conflict" in p["reason"]}
    assert parked_ids == {a.id, b.id}
    prices = {float(p.price_pair) for p in _all_pricing(db)}
    assert prices == {50.0}                             # neither 100 nor 200 written
    db.refresh(cat)
    assert cat.status == models.CatalogStatus.CONFIRMED


# ===========================================================================
# N. forced exception mid-confirm -> full rollback
# ===========================================================================
def _boom(_db):
    raise RuntimeError("injected mid-confirm fault")


def test_N_forced_exception_rolls_everything_back(db):
    company = _company(db)

    v1 = _catalog(db, company)
    _ext(db, v1, name="Solo", price=100.0, sph_min=-4.0, sph_max=0.0)
    crud.confirm_catalog_commercial(db, v1.id)
    before = _current(db, company.id)
    assert len(before) == 1 and before[0].price_pair == Decimal("100.00")

    v2 = _catalog(db, company)
    _ext(db, v2, name="Solo", price=200.0, sph_min=-4.0, sph_max=0.0)

    with pytest.raises(RuntimeError):
        crud.confirm_catalog_commercial(db, v2.id, _fault_hook=_boom)

    # no new pricing, prior current NOT left closed, catalog statuses unchanged
    after = _current(db, company.id)
    assert len(after) == 1
    assert after[0].price_pair == Decimal("100.00")
    assert after[0].effective_to is None
    assert len(_all_pricing(db)) == 1
    db.refresh(v1)
    db.refresh(v2)
    assert v1.status == models.CatalogStatus.CONFIRMED
    assert v2.status == models.CatalogStatus.DRAFT


# ===========================================================================
# O. row-level extraction confirm never writes VariantPricing
# ===========================================================================
def test_O_row_confirm_writes_no_pricing(db):
    company = _company(db)
    cat = _catalog(db, company)
    ext = _ext(db, cat, name="Row", price=100.0, sph_min=-4.0, sph_max=0.0,
               review_status="pending")

    # via crud
    crud.confirm_extraction(db, ext.id, reviewed_by="qa")
    assert db.query(models.VariantPricing).count() == 0
    db.refresh(ext)
    assert ext.status == "confirmed"

    # via the router handler itself
    ext2 = _ext(db, cat, name="Row2", price=100.0, sph_min=-4.0, sph_max=0.0,
                review_status="pending",
                coating_status=models.CoatingExtractionStatus.EXPLICIT_NONE)
    out = pdf_import.confirm_extraction(extraction_id=ext2.id, reviewed_by="qa", db=db)
    assert out["status"] == "confirmed"
    assert db.query(models.VariantPricing).count() == 0
    assert db.query(models.LensModel).count() == 0
    assert db.query(models.PowerRange).count() == 0


# ===========================================================================
# P. Decimal price_pair written exactly
# ===========================================================================
@pytest.mark.parametrize("raw,expected", [
    (1234.56, Decimal("1234.56")),
    ("19.99", Decimal("19.99")),
    (2500.0, Decimal("2500.00")),
    (0.05, Decimal("0.05")),
])
def test_P_decimal_price_pair_exact(db, raw, expected):
    company = _company(db)
    cat = _catalog(db, company)
    _ext(db, cat, name="Money", price=raw, sph_min=-4.0, sph_max=0.0)
    crud.confirm_catalog_commercial(db, cat.id)
    db.expire_all()
    p = _all_pricing(db)[0]
    assert isinstance(p.price_pair, Decimal)
    assert p.price_pair == expected
    assert str(p.price_pair) == str(expected)


def test_P_more_than_two_decimal_places_blocks(db):
    company = _company(db)
    cat = _catalog(db, company)
    _ext(db, cat, name="BadMoney", price="19.999", sph_min=-4.0, sph_max=0.0)
    with pytest.raises(crud.CommercialValidationError) as exc:
        crud.confirm_catalog_commercial(db, cat.id)
    assert any("decimal places" in e for e in exc.value.errors)
    assert _all_pricing(db) == []


# ===========================================================================
# Legacy bypass endpoint disabled
# ===========================================================================
def test_bulk_upload_endpoint_is_disabled(db):
    payload = _schemas_bulk_upload_request()
    with pytest.raises(Exception) as exc:
        pdf_import.bulk_upload_power_ranges(data=payload, db=db)
    # FastAPI HTTPException with status 410
    assert getattr(exc.value, "status_code", None) == 410


def _schemas_bulk_upload_request():
    from app import schemas
    return schemas.BulkUploadRequest(company_id=1, ranges=[])


# ===========================================================================
# invalid commercial availability blocks
# ===========================================================================
def test_invalid_availability_blocks_catalog(db):
    company = _company(db)
    cat = _catalog(db, company)
    _ext(db, cat, name="Bad", price=100.0, availability="both",
         sph_min=-4.0, sph_max=0.0)
    with pytest.raises(crud.CommercialValidationError) as exc:
        crud.confirm_catalog_commercial(db, cat.id)
    assert any("availability" in e for e in exc.value.errors)
    assert _all_pricing(db) == []
