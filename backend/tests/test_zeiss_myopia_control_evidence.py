"""ZEISS MyoCare / MyoCare S ingestion (Special Lenses architecture,
owner-confirmed, 2026-09-19/20) - the second manufacturer under the generic
Myopia Control subtype, after SCOPE Myoblock/Metavision.

Evidence: ZEISS_Main_Catalog.pdf pp.51-52 "ZEISS MyoCare Lenses" - see
app/zeiss_myopia_control_evidence.py's own module docstring for the full
second-pass vector-extraction citation (two catalog-proven distinct designs,
MyoCare 7mm/+4.6D and MyoCare S 9mm/+3.8D, sharing one identical printed
price/PowerRange table). RX vs Stock split and market_scope are per the
2026-09-20 owner confirmation: "ZEISS RX lenses are RX/Manufacturing, NOT
Stock" - the "ZEISS Stock is in Egypt" business fact never extends to RX.

Strict scope: ONLY MyoCare and MyoCare S. ZEISS MyoActive is deliberately
NOT ingested here (future-dated "Available from 1st October 2026", and its
own power-range chart has no per-product split proven separately from
MyoCare/MyoCare S RX) - proven absent by dedicated negative tests. ZEISS
SmartLife Young is out of scope entirely (its own catalog classifies it as
Single Vision).

Deliberately synthetic (mirrors test_special_lenses_subtypes_evidence.py's
own pattern) - no PDF parsing, no dependency on the live release_runtime.db;
the live db result is verified separately.
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
from app import models, database, schemas, product_search  # noqa: E402
from app import zeiss_myopia_control_evidence as zmc  # noqa: E402

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


def _mk_existing_zeiss_model(db, co, name, category=models.LensCategory.SINGLE_VISION):
    m = models.LensModel(company_id=co.id, name=name, category=category)
    db.add(m); db.commit(); db.refresh(m)
    return m


# --------------------------------------------------------------- 1/2: identity + category
def test_myocare_and_myocare_s_are_distinct_products_both_myopia_control(db):
    co = _mk_zeiss_company(db)
    result = zmc.reconcile(db)
    assert result["rx_created"] > 0 and result["stock_created"] > 0
    models_ = (db.query(models.LensModel)
               .filter(models.LensModel.company_id == co.id, models.LensModel.name.in_(zmc.PRODUCT_NAMES))
               .all())
    names = {m.name for m in models_}
    assert names == {"MyoCare", "MyoCare S"}
    ids = {m.id for m in models_}
    assert len(ids) == 2  # distinct rows, never collapsed into one
    for m in models_:
        assert m.category == models.LensCategory.MYOPIA_CONTROL


# --------------------------------------------------------------- 3/4: routing
def test_neither_product_appears_in_ordinary_single_vision_search(db):
    _mk_zeiss_company(db)
    zmc.reconcile(db)
    presc = _mk_presc(db, -3.0, -1.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="distance"))
    names = {r.model_name for g in resp.groups for r in g.results}
    assert "MyoCare" not in names and "MyoCare S" not in names


def test_both_products_reachable_through_myopia_control_use_mode(db):
    _mk_zeiss_company(db)
    zmc.reconcile(db)
    presc = _mk_presc(db, -3.0, -1.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="myopia_control"))
    names = {r.model_name for g in resp.groups for r in g.results}
    assert {"MyoCare", "MyoCare S"} <= names


# --------------------------------------------------------------- 5/6: shared price/range table
@pytest.mark.parametrize("product", zmc.PRODUCT_NAMES)
def test_shared_rx_price_table_is_represented_identically_for_both_products(db, product):
    co = _mk_zeiss_company(db)
    zmc.reconcile(db)
    model = db.query(models.LensModel).filter_by(company_id=co.id, name=product).one()
    rows = (db.query(models.VariantPricing)
            .join(models.LensVariant, models.LensVariant.id == models.VariantPricing.variant_id)
            .join(models.Coating, models.Coating.id == models.VariantPricing.coating_id)
            .filter(models.LensVariant.lens_model_id == model.id,
                    models.VariantPricing.availability == models.PricingAvailability.RX)
            .all())
    prices = {(r.variant.index_value, r.coating.code): r.price_pair for r in rows}
    for coating_code, by_index in zmc.RX_PRICES.items():
        for index_value, price in by_index.items():
            assert prices[(index_value, coating_code)] == price


@pytest.mark.parametrize("product", zmc.PRODUCT_NAMES)
def test_shared_rx_power_range_bands_match_the_extracted_evidence(db, product):
    co = _mk_zeiss_company(db)
    zmc.reconcile(db)
    model = db.query(models.LensModel).filter_by(company_id=co.id, name=product).one()
    ranges = (db.query(models.PowerRange)
              .join(models.LensVariant, models.LensVariant.id == models.PowerRange.variant_id)
              .join(models.VariantPricing, models.VariantPricing.id == models.PowerRange.pricing_id)
              .filter(models.LensVariant.lens_model_id == model.id,
                      models.VariantPricing.availability == models.PricingAvailability.RX)
              .all())
    # Every distinct total_power_min proven in the evidence must appear at least once.
    seen_bounds = {round(pr.total_power_min, 2) for pr in ranges}
    expected_bounds = {b.total_power_min for b in zmc._RX_BANDS}
    assert expected_bounds <= seen_bounds
    for pr in ranges:
        assert pr.total_power_max is None  # no plus-side cap printed anywhere


# --------------------------------------------------------------- 7: design identity distinct
def test_myocare_vs_myocare_s_design_identity_is_distinct_not_collapsed(db):
    co = _mk_zeiss_company(db)
    zmc.reconcile(db)
    myocare = db.query(models.LensModel).filter_by(company_id=co.id, name="MyoCare").one()
    myocare_s = db.query(models.LensModel).filter_by(company_id=co.id, name="MyoCare S").one()
    assert myocare.id != myocare_s.id
    assert myocare.name != myocare_s.name


# --------------------------------------------------------------- 8/9: RX vs Stock
def test_rx_rows_are_manufacturing_rx_never_stock_egypt(db):
    co = _mk_zeiss_company(db)
    zmc.reconcile(db)
    rx_rows = (db.query(models.VariantPricing)
               .join(models.LensVariant, models.LensVariant.id == models.VariantPricing.variant_id)
               .join(models.LensModel, models.LensModel.id == models.LensVariant.lens_model_id)
               .filter(models.LensModel.company_id == co.id, models.LensModel.name.in_(zmc.PRODUCT_NAMES),
                       models.VariantPricing.availability == models.PricingAvailability.RX)
               .all())
    assert len(rx_rows) == 16  # 2 products x 2 coatings x 4 indexes
    for r in rx_rows:
        assert r.market_scope is None  # never "Egypt" - owner-confirmed 2026-09-20


def test_stock_row_is_stock_egypt_only(db):
    co = _mk_zeiss_company(db)
    zmc.reconcile(db)
    stock_rows = (db.query(models.VariantPricing)
                  .join(models.LensVariant, models.LensVariant.id == models.VariantPricing.variant_id)
                  .join(models.LensModel, models.LensModel.id == models.LensVariant.lens_model_id)
                  .filter(models.LensModel.company_id == co.id, models.LensModel.name.in_(zmc.PRODUCT_NAMES),
                          models.VariantPricing.availability == models.PricingAvailability.STOCK)
                  .all())
    assert len(stock_rows) == 2  # 2 products x 1 stock coating
    for r in stock_rows:
        assert r.market_scope == "Egypt"
        assert r.variant.index_value == 1.59
        assert r.price_pair == zmc.STOCK_PRICE


# --------------------------------------------------------------- 10/11: stock-over-rx priority
def test_prescription_inside_stock_range_routes_stock_egypt(db):
    _mk_zeiss_company(db)
    zmc.reconcile(db)
    presc = _mk_presc(db, -3.0, -1.0)  # low meridian -4.0, cyl 1.0: inside stock's -6.00/2.00 band
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="myopia_control"))
    assert resp.availability_answer.code == "stock_egypt"


def test_prescription_outside_stock_but_inside_rx_range_routes_rx(db):
    _mk_zeiss_company(db)
    zmc.reconcile(db)
    presc = _mk_presc(db, -8.0, 0.0)  # low meridian -8.0: outside stock (-6.00), inside RX 1.59 65mm (-9.00)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="myopia_control"))
    assert resp.availability_answer.code == "rx_only"


# --------------------------------------------------------------- 12: price ordering unchanged
def test_price_ordering_ascending_within_rx_tier(db):
    _mk_zeiss_company(db)
    zmc.reconcile(db)
    presc = _mk_presc(db, -8.0, 0.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="myopia_control"))
    prices = [r.pair_fulfillment.price_pair for g in resp.groups for r in g.results
              if r.model_name == "MyoCare"]
    assert prices == sorted(prices)


# --------------------------------------------------------------- 13/14: MyoActive strict negative
def test_myoactive_is_never_created(db):
    co = _mk_zeiss_company(db)
    zmc.reconcile(db)
    assert db.query(models.LensModel).filter_by(company_id=co.id, name="MyoActive").first() is None


def test_myoactive_absent_from_myopia_control_search(db):
    _mk_zeiss_company(db)
    zmc.reconcile(db)
    presc = _mk_presc(db, -3.0, -1.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="myopia_control"))
    names = {r.model_name for g in resp.groups for r in g.results}
    assert "MyoActive" not in names


# --------------------------------------------------------------- 15: SmartLife Young untouched
def test_smartlife_young_is_never_created(db):
    co = _mk_zeiss_company(db)
    zmc.reconcile(db)
    assert db.query(models.LensModel).filter_by(company_id=co.id, name="SmartLife Young").first() is None


# --------------------------------------------------------------- 16: existing ZEISS untouched
def test_existing_zeiss_products_are_not_reclassified(db):
    co = _mk_zeiss_company(db)
    existing_names = ("ClearMind", "ClearView RX", "SPH RX", "AS FSV", "ClearView FSV", "SPH FSV")
    existing = {name: _mk_existing_zeiss_model(db, co, name) for name in existing_names}
    zmc.reconcile(db)
    for name, m in existing.items():
        db.refresh(m)
        assert m.category == models.LensCategory.SINGLE_VISION, name


# --------------------------------------------------------------- 17: idempotency
def test_reconcile_is_idempotent(db):
    _mk_zeiss_company(db)
    result1 = zmc.reconcile(db)
    assert result1["rx_created"] == 16 and result1["stock_created"] == 2
    result2 = zmc.reconcile(db)
    assert result2["rx_created"] == 0 and result2["stock_created"] == 0
