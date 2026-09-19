"""HOYA Daynamic / Daynamic PNX ingestion (Catalog Truth Audit B2).

OWNER-CONFIRMED BUSINESS RULE (authoritative, not an inference): across the
HOYA price catalog, a two-price row is wholesale (first) | customer/retail
(second). The wholesale price must NEVER be persisted as - or surface as -
a seller/customer price. app/hoya_daynamic_evidence.py is the single,
re-runnable, idempotent source that ingests the 8 catalog-proven Daynamic
rows (Hoya_Price_List_2025_Updated.pdf p.20) using ONLY the second (retail)
number, cross-validated against three independent pieces of evidence already
present elsewhere in this codebase before this change (addon_scope_evidence's
Daynamic identity whitelist, technology_evidence's "Daynamic PNX" impact
mechanism, and technology_evidence's "Sensity Original" photochromic
mapping) plus HOYA's own sibling progressive lines (Amplitude Plus) sharing
the identical G3 total-power envelope at every shared index.

Deliberately synthetic (mirrors test_phase2_import_confirmation.py's /
test_p0_stock_egypt_reconciliation.py's own patterns) - no PDF parsing, no
dependency on the live release_runtime.db.
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
from app import models, database, schemas, product_search, technology_evidence as te  # noqa: E402
from app import hoya_daynamic_evidence, progressive_add_evidence  # noqa: E402
from app.addon_scope_evidence import proves_addon_scope  # noqa: E402

from test_use_mode_technology import _mk_presc  # noqa: E402

# The 8 catalog-printed wholesale prices - must NEVER appear as a persisted
# price_pair anywhere after reconciliation.
_WHOLESALE_PRICES = {Decimal(v) for v in
                     (6000, 7200, 8000, 8200, 8700, 9650, 10300, 10600)}
# The 8 catalog-printed customer/retail prices - the ONLY values allowed.
_RETAIL_PRICES = {Decimal(v) for v in
                  (12600, 15150, 16800, 17250, 18300, 20300, 21650, 22300)}


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


def _mk_hoya_confirmed_catalog(db):
    co = models.Company(name="HOYA", country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename="hoya.pdf", file_path="hoya.pdf",
                         status=models.CatalogStatus.CONFIRMED)
    db.add(cat); db.commit(); db.refresh(cat)
    coating = models.Coating(code="Super Hi Vision", name="Super Hi Vision")
    db.add(coating); db.commit()
    return co, cat


def _pricing_rows(db, model_name):
    return (db.query(models.VariantPricing)
            .join(models.LensVariant, models.LensVariant.id == models.VariantPricing.variant_id)
            .join(models.LensModel, models.LensModel.id == models.LensVariant.lens_model_id)
            .filter(models.LensModel.name == model_name)
            .all())


def test_reconcile_creates_exactly_the_eight_proven_rows_at_retail_price(db):
    _mk_hoya_confirmed_catalog(db)
    result = hoya_daynamic_evidence.reconcile(db)
    assert result["created_pricing_rows"] == 8

    base_rows = _pricing_rows(db, "Daynamic")
    pnx_rows = _pricing_rows(db, "Daynamic PNX")
    assert len(base_rows) == 6   # 1.5 / 1.6 / 1.67 x {base, Sensity Original}
    assert len(pnx_rows) == 2    # 1.53 x {base, Sensity Original}

    prices = {vp.price_pair for vp in base_rows + pnx_rows}
    assert prices == _RETAIL_PRICES


def test_reconcile_never_persists_wholesale_price_anywhere(db):
    _mk_hoya_confirmed_catalog(db)
    hoya_daynamic_evidence.reconcile(db)
    all_prices = {vp.price_pair for vp in db.query(models.VariantPricing).all()}
    assert all_prices.isdisjoint(_WHOLESALE_PRICES)


def test_reconcile_power_ranges_match_the_proven_g3_envelope_per_index(db):
    _mk_hoya_confirmed_catalog(db)
    hoya_daynamic_evidence.reconcile(db)
    expected = {  # index -> (total_power_min, total_power_max, max_cyl_abs)
        1.5: (-8.0, 6.0, 6.0), 1.53: (-8.0, 6.0, 6.0),
        1.6: (-13.0, 6.5, 6.0), 1.67: (-13.0, 8.0, 6.0),
    }
    rows = _pricing_rows(db, "Daynamic") + _pricing_rows(db, "Daynamic PNX")
    for vp in rows:
        [pr] = vp.power_ranges
        tmin, tmax, mcyl = expected[vp.variant.index_value]
        assert (pr.total_power_min, pr.total_power_max, pr.max_cyl_abs) == (tmin, tmax, mcyl)
        assert pr.cyl_min == -mcyl and pr.cyl_max == 0.0
        assert pr.sph_min == tmin and pr.sph_max == tmax + mcyl


def test_reconcile_is_idempotent(db):
    _mk_hoya_confirmed_catalog(db)
    hoya_daynamic_evidence.reconcile(db)
    first_count = db.query(models.VariantPricing).count()
    result2 = hoya_daynamic_evidence.reconcile(db)
    assert result2["created_pricing_rows"] == 0
    assert db.query(models.VariantPricing).count() == first_count
    prices = {vp.price_pair for vp in db.query(models.VariantPricing).all()}
    assert prices == _RETAIL_PRICES


def test_daynamic_pnx_gets_impact_resistant_capability():
    caps = te.proven_capabilities("HOYA", None, None, None,
                                  model_name="Daynamic PNX", index_value=1.53)
    assert "impact_resistant" in caps


def test_daynamic_sensity_original_gets_photochromic_capability():
    caps = te.proven_capabilities("HOYA", None, None, "Sensity Original",
                                  model_name="Daynamic", index_value=1.5)
    assert {"photo_gray", "photo_brown"} <= caps


@pytest.mark.parametrize("model_name,index", [("Daynamic", 1.5), ("Daynamic", 1.6),
                                              ("Daynamic", 1.67), ("Daynamic PNX", 1.53)])
def test_daynamic_identity_is_recognized_by_addon_scope_evidence(model_name, index):
    # Validates the pre-existing addon_scope_evidence.py whitelist entry this
    # module relies on for HOYA's generic BLC Type-B add-on to reach Daynamic.
    assert proves_addon_scope(
        "HOYA", model_name=model_name, category="progressive", index_value=index,
        design_type="spherical", design_variant=None, design_tier=None,
        treatment_band=None, color_variant=None, coating_name="Super Hi Vision",
        market_scope="Out Of Egypt")


def test_search_returns_only_retail_price_never_wholesale(db):
    # Realistic progressive search: use_mode="progressive" with a real ADD
    # power, exactly how a seller would search for this product. This
    # requires app.progressive_add_evidence.reconcile() (the owner-confirmed
    # +0.75/+3.50 Progressive ADD default) to have also run - without it,
    # HOYA's progressive PowerRanges (Daynamic included) have no add_min/
    # add_max and are correctly rejected by the unmodified, unweakened
    # lens_matcher ADD check. See test_progressive_add_evidence.py for the
    # full audit/fix; this test only proves Daynamic itself is reachable
    # end-to-end once that fix is applied, and still returns retail-only
    # prices.
    _mk_hoya_confirmed_catalog(db)
    hoya_daynamic_evidence.reconcile(db)
    progressive_add_evidence.reconcile(db)
    presc = _mk_presc(db, -2.0, -2.0, od_cyl=-1.0, os_cyl=-1.0, od_add=2.0, os_add=2.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="progressive"))
    rows = [r for g in resp.groups for r in g.results if r.model_name.startswith("Daynamic")]
    assert len(rows) == 8, "expected all 8 catalog-proven Daynamic rows to match this prescription"
    for r in rows:
        price = r.pair_fulfillment.price_pair
        assert price is not None
        assert price not in _WHOLESALE_PRICES
        assert price in _RETAIL_PRICES
