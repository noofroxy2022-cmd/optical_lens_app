"""Phase 4I - closing the Phase 4H acceptance gaps.

Section C finding AS OF PHASE 4I (superseded - see below): no canonical
ZEISS 315-row price fixture existed anywhere in this repository at the time.
The project's established convention for ZEISS-shaped testing
(test_phase5_eligibility_safety.py) used a synthetic "ZeissLike" company for
exactly this reason, and Section D below follows that same convention - it
was never a claim to be the real 315 rows.

RESOLVED IN PHASE 4J: test_phase4j_real_zeiss_e2e.py now reconstructs the
real 315-row commercial dataset directly from the authoritative
ZEISS_Main_Catalog.pdf via the production index-grid extraction strategy,
then attaches the proven graphical ranges to it - closing this gap for real.
test_4i_no_canonical_315_fixture_exists below was the Phase 4I tripwire that
correctly fired once that file appeared; it now asserts the resolved state
instead of the absence.
"""
import os
import sys
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database import Base  # noqa: E402
from app import models, database, schemas, product_search, crud as _crud  # noqa: E402
from app.pdf_hybrid_parser import PDFHybridParser  # noqa: E402
from app.routers.prescriptions import (  # noqa: E402
    match_lenses as match_endpoint,
    product_search as search_endpoint,
)
from app.zeiss_svrx_graphical_evidence import build_extracted_models  # noqa: E402


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    event.listen(engine, "connect", database._set_sqlite_pragma)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


# ============================================================
# Section C: canonical 315 fixture - RESOLVED in Phase 4J
# ============================================================
def test_4i_canonical_315_fixture_now_resolved_by_phase_4j():
    """Phase 4I's tripwire correctly fired once test_phase4j_real_zeiss_e2e.py
    was added (a real canonical-315 reconstruction, not a pre-existing stale
    fixture). This now asserts that resolution explicitly: the real-PDF
    integration test exists and is the one place production identity linking
    against the actual 315 rows is proven."""
    real_e2e = os.path.join(BACKEND_DIR, "tests", "test_phase4j_real_zeiss_e2e.py")
    assert os.path.exists(real_e2e), (
        "expected Phase 4J's real ZEISS 315-row reconstruction test to exist")
    text = open(real_e2e, encoding="utf-8").read()
    assert "315" in text and "_reconstruct_index_grid" in text


# ---------------------------------------------------------------------------
# Fixture builder for a "ZeissLike" proven G3 commercial identity, following
# the SAME convention test_phase5_eligibility_safety.py already established.
# ---------------------------------------------------------------------------
def _mk_company(db, name):
    co = models.Company(name=name, country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    return co


def _mk_catalog(db, company, status=models.CatalogStatus.DRAFT):
    cat = models.Catalog(company_id=company.id, filename="synthetic.pdf",
                         file_path="synthetic.pdf", status=status)
    db.add(cat); db.commit(); db.refresh(cat)
    return cat


def _mk_presc(db, od_sph, od_cyl, os_sph, os_cyl, name="p"):
    p = models.Prescription(
        customer_name=name,
        od_sph_original=od_sph, od_cyl_original=od_cyl, od_axis_original=90,
        od_sph=od_sph, od_cyl=od_cyl, od_axis=90,
        os_sph_original=os_sph, os_cyl_original=os_cyl, os_axis_original=90,
        os_sph=os_sph, os_cyl=os_cyl, os_axis=90, pd=63,
    )
    db.add(p); db.commit(); db.refresh(p)
    return p


def _targeted(db, presc, model, **extra):
    f = schemas.LensFilters(lens_model_id=model.id, **extra)
    req = schemas.ProductSearchRequest(mode="targeted", filters=f)
    return product_search.search(db, presc, req)


def _seed_zeisslike_pricing(db, co, price_cat, *, family, index_value, material,
                            treatment_band, coating_code, price):
    model = db.query(models.LensModel).filter(
        models.LensModel.company_id == co.id, models.LensModel.name == family,
        models.LensModel.category == models.LensCategory.SINGLE_VISION,
    ).first()
    if model is None:
        model = models.LensModel(company_id=co.id, name=family,
                                 category=models.LensCategory.SINGLE_VISION)
        db.add(model); db.commit(); db.refresh(model)
    variant = models.LensVariant(
        lens_model_id=model.id, material=material, index_value=index_value,
        design_type=models.DesignType.SPHERICAL, is_aspherical=False,
        treatment_band=treatment_band, availability=models.LensAvailability.RX,
        price=0.0, currency="EGP",
    )
    db.add(variant); db.commit(); db.refresh(variant)
    coating = models.Coating(code=coating_code, name=coating_code)
    db.add(coating); db.commit(); db.refresh(coating)
    vp = models.VariantPricing(
        variant_id=variant.id, coating_id=coating.id,
        availability=models.PricingAvailability.RX,
        power_eligibility=models.PowerEligibilityStatus.UNRESOLVED,
        price_pair=Decimal(str(price)), currency="EGP", source_catalog_id=price_cat.id,
        effective_from=datetime.utcnow(), effective_to=None,
        power_scope=None, market_scope=None,
    )
    db.add(vp); db.commit(); db.refresh(vp)
    return model, variant, vp


def _attach_all_proven(db, family=None):
    co = db.query(models.Company).filter(models.Company.name == "ZeissLike").first()
    cat = models.Catalog(company_id=co.id, filename="ev.pdf", file_path="/x",
                         status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)
    p = PDFHybridParser(use_vision=False)
    p.extracted_models = build_extracted_models(only_confidence="proven")
    p.save_extractions_to_db(cat.id, db)
    attached = []
    for e in _crud.get_extractions_by_catalog(db, cat.id):
        if e.status == "needs_review":
            continue
        if family is not None and e.extracted_name != family:
            continue
        _crud.confirm_extraction(db, e.id, "qa")
        res = _crud.attach_range_to_existing_pricing(db, e.id)
        attached.append((e, res))
    return attached


# ============================================================
# Section D - full V1.0.2 path with ZEISS-shaped proven G3 data
# range: ClearView RX 1.74 Clear/BlueGuard ø60-55, total [-20,16], maxcyl 6
# ============================================================
def _seed_cv174(db):
    co = _mk_company(db, "ZeissLike")
    price_cat = _mk_catalog(db, co, status=models.CatalogStatus.CONFIRMED)
    model, variant, vp = _seed_zeisslike_pricing(
        db, co, price_cat, family="ClearView RX", index_value=1.74,
        material="high_index_1.74", treatment_band="Clear",
        coating_code="DuraVision Plus Gold", price=17400,
    )
    attached = _attach_all_proven(db, family="ClearView RX")
    ok = [r for e, r in attached if "error" not in r]
    assert ok, [r for e, r in attached]
    return co, model, variant, vp


# -- A. both eyes eligible in a proven G3 range -> proven pair price --------
def test_4i_D_A_both_eyes_eligible_proven_pair(db):
    co, model, variant, vp = _seed_cv174(db)
    presc = _mk_presc(db, -14.0, -6.0, -14.0, -6.0)   # M1=-14, M2=-20 exact boundary, both eyes
    resp = _targeted(db, presc, model)
    bm = resp.best_match
    assert bm is not None
    assert bm.od.rx is True and bm.os.rx is True
    assert bm.pair_fulfillment.status in ("stock_egypt", "stock_outside", "rx")
    assert bm.pair_fulfillment.price_pair is not None


# -- B. one eye eligible, one eye outside all proven zones -> no proven pair
def test_4i_D_B_one_eye_outside_no_proven_pair(db):
    co, model, variant, vp = _seed_cv174(db)
    presc = _mk_presc(db, -14.0, -6.0, -30.0, 0.0)   # OS way outside [-20,16]
    resp = _targeted(db, presc, model)
    bm = resp.best_match
    assert bm is not None
    assert bm.od.rx is True
    assert bm.os.rx is False and bm.os.rx_unknown is False   # proven ineligible, not unknown
    assert bm.pair_fulfillment.status not in ("stock_egypt", "stock_outside", "rx")
    assert bm.pair_fulfillment.price_pair is None


# -- C. per-eye independence of a proven row's tri-state --------------------
# NOTE: honestly scoped. Task item C ("one eye eligible, other eye UNKNOWN")
# does not arise from a SINGLE row once it has real PowerRange data: has_range
# =True makes _row_eye_status deterministic (eligible/ineligible) for BOTH
# eyes off the same OR'd range set - "unknown" only exists for a row with NO
# PowerRange at all, which is then unknown for both eyes uniformly (see
# Phase 5's test_A/test_E, unchanged and still green). What IS proven here,
# specific to a real proven ZEISS G3 row, is that each eye is evaluated
# independently against it (an OD-only match does not imply OS matches, and
# vice versa) - the actual building block case C's pairing logic relies on.
def test_4i_D_C_per_eye_independence_on_proven_zeiss_row(db):
    co, model, variant, vp = _seed_cv174(db)
    pr = next(r for r in vp.power_ranges if r.total_power_min == -20.0)
    presc = _mk_presc(db, -14.0, -6.0, -30.0, 0.0)
    od_ok, _ = product_search.lens_matcher.check_power_range(pr, presc, "od")
    os_ok, _ = product_search.lens_matcher.check_power_range(pr, presc, "os")
    assert od_ok is True and os_ok is False


# -- D. both eyes UNKNOWN -> eligibility_unknown -----------------------------
def test_4i_D_D_both_eyes_unknown(db):
    co = _mk_company(db, "ZeissLike")
    cat = _mk_catalog(db, co)
    model = models.LensModel(company_id=co.id, name="UnresolvedZeissModel",
                             category=models.LensCategory.SINGLE_VISION)
    db.add(model); db.commit(); db.refresh(model)
    variant = models.LensVariant(
        lens_model_id=model.id, material=models.MaterialType.CR39, index_value=1.5,
        design_type=models.DesignType.SPHERICAL, is_aspherical=False, price=0.0, currency="EGP")
    db.add(variant); db.commit(); db.refresh(variant)
    vp = models.VariantPricing(
        variant_id=variant.id, availability=models.PricingAvailability.RX,
        power_eligibility=models.PowerEligibilityStatus.UNRESOLVED,
        price_pair=Decimal("9999.00"), currency="EGP", source_catalog_id=cat.id)
    db.add(vp); db.commit(); db.refresh(vp)
    presc = _mk_presc(db, -2.0, -0.5, -2.0, -0.5)

    resp = _targeted(db, presc, model)
    bm = resp.best_match
    assert bm is not None
    assert bm.pair_fulfillment.status == "eligibility_unknown"
    assert bm.pair_fulfillment.price_pair is None
    assert bm.od.rx is False and bm.od.rx_unknown is True
    assert bm.os.rx is False and bm.os.rx_unknown is True


# -- E. treatment A proven, B unresolved -> no cross-leak --------------------
def test_4i_D_E_treatment_isolation_at_search_layer(db):
    co, model, variant_cb, vp_cb = _seed_cv174(db)
    price_cat = db.query(models.Catalog).filter(
        models.Catalog.company_id == co.id, models.Catalog.status == models.CatalogStatus.CONFIRMED,
    ).first()
    # a second, POL-treatment variant/pricing that is NEVER attached (stays
    # power_eligibility=UNRESOLVED, no PowerRange)
    _model2, variant_pol, vp_pol = _seed_zeisslike_pricing(
        db, co, price_cat, family="ClearView RX", index_value=1.74,
        material="high_index_1.74", treatment_band="POL",
        coating_code="Sun Polarized", price=20000,
    )
    presc = _mk_presc(db, -14.0, -6.0, -14.0, -6.0)
    cb_status = product_search._row_eye_status(vp_cb, presc, "od")
    pol_status = product_search._row_eye_status(vp_pol, presc, "od")
    assert cb_status == "eligible"
    assert pol_status == "unknown"   # never inherits Clear/BlueGuard's proof


# -- F. multiple diameter PowerRange rows -> one commercial result only -----
def test_4i_D_F_multi_diameter_one_result(db):
    co = _mk_company(db, "ZeissLike")
    price_cat = _mk_catalog(db, co, status=models.CatalogStatus.CONFIRMED)
    model, variant, vp = _seed_zeisslike_pricing(
        db, co, price_cat, family="ClearView RX", index_value=1.67,
        material="high_index_1.67", treatment_band="Clear",
        coating_code="DuraVision Plus Gold", price=14600,
    )
    attached = _attach_all_proven(db, family="ClearView RX")
    ok = [r for e, r in attached if "error" not in r]
    assert ok
    db.refresh(vp)
    # ø80 (standalone "Clear"), ø70-75 and ø65-55 (from "Clear/BlueGuard"
    # merged rows) - three diameter zones, one pricing row.
    assert len(vp.power_ranges) == 3

    presc = _mk_presc(db, -11.0, -4.0, -11.0, -4.0)  # only the ø65-55 zone covers this
    resp = _targeted(db, presc, model)
    matches = [r for g in resp.groups for r in g.results if r.variant_id == variant.id]
    assert len(matches) == 1, "multiple diameter zones must not multiply search results"
    assert resp.best_match is not None


# -- G/H. alternatives: unresolved excluded, proven-eligible ZEISS included --
def test_4i_D_GH_alternatives_unresolved_excluded_proven_included(db):
    co, model, variant, vp = _seed_cv174(db)
    price_cat = db.query(models.Catalog).filter(
        models.Catalog.company_id == co.id, models.Catalog.status == models.CatalogStatus.CONFIRMED,
    ).first()
    _m2, _v2, vp_unresolved = _seed_zeisslike_pricing(
        db, co, price_cat, family="ClearView RX", index_value=1.6,
        material="high_index_1.60", treatment_band="POL",
        coating_code="Sun Tint", price=9000,
    )  # never attached - stays UNRESOLVED
    presc = _mk_presc(db, -14.0, -6.0, -14.0, -6.0)
    f = schemas.LensFilters(lens_model_id=999999)   # force alternatives path
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(
        mode="targeted", filters=f, include_alternatives=True))
    alt_ids = {a.result.source_pricing_id for a in resp.alternatives}
    assert vp_unresolved.id not in alt_ids, "unresolved ZEISS candidate leaked into alternatives"
    assert vp.id in alt_ids, "proven-eligible ZEISS candidate was wrongly excluded"


# -- /search == /match parity on a proven ZEISS G3 case ---------------------
def test_4i_search_match_parity_proven_zeiss(db):
    co, model, variant, vp = _seed_cv174(db)
    presc = _mk_presc(db, -14.0, -6.0, -14.0, -6.0)
    f = schemas.LensFilters(lens_model_id=model.id)
    search_resp = search_endpoint(prescription_id=presc.id,
                                  req=schemas.ProductSearchRequest(mode="targeted", filters=f),
                                  db=db)
    match_resp = match_endpoint(prescription_id=presc.id, filters=f,
                                prefer_stock=True, prefer_aspherical=True, db=db)
    for tag, resp in (("search", search_resp), ("match", match_resp)):
        bm = resp.best_match
        assert bm is not None, tag
        assert bm.pair_fulfillment.status in ("stock_egypt", "stock_outside", "rx"), tag
        assert bm.pair_fulfillment.price_pair is not None, tag
    assert search_resp.best_match.pair_fulfillment.status == match_resp.best_match.pair_fulfillment.status
    assert search_resp.exact_total == match_resp.exact_total


# ============================================================
# Section E - additive persistence function hidden-risk audit
# ============================================================
def test_4i_E_attach_cannot_touch_historical_pricing(db):
    co, model, variant, vp_current = _seed_cv174(db)
    # vp_current already received all 3 of ClearView RX 1.74's Clear/BlueGuard
    # diameter-zone ranges from _seed_cv174's own setup - record that count,
    # then close the pricing (simulate a superseded catalog) and open a NEW
    # current row. A fresh attach call afterwards must add to the NEW row
    # only; the OLD (closed) row's range count must not change.
    before_count = len(vp_current.power_ranges)
    assert before_count > 0
    vp_current.effective_to = datetime.utcnow()
    db.commit()
    price_cat = db.query(models.Catalog).filter(
        models.Catalog.company_id == co.id, models.Catalog.status == models.CatalogStatus.CONFIRMED,
    ).first()
    coating = db.query(models.Coating).first()
    vp_new = models.VariantPricing(
        variant_id=variant.id, coating_id=coating.id,
        availability=models.PricingAvailability.RX,
        power_eligibility=models.PowerEligibilityStatus.UNRESOLVED,
        price_pair=Decimal("18000.00"), currency="EGP", source_catalog_id=price_cat.id,
        effective_from=datetime.utcnow(), effective_to=None,
        power_scope=None, market_scope=None,
    )
    db.add(vp_new); db.commit(); db.refresh(vp_new)

    cat = models.Catalog(company_id=co.id, filename="ev2.pdf", file_path="/x",
                         status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)
    p = PDFHybridParser(use_vision=False)
    p.extracted_models = build_extracted_models(only_confidence="proven")
    p.save_extractions_to_db(cat.id, db)
    ext = next(
        e for e in _crud.get_extractions_by_catalog(db, cat.id)
        if e.extracted_name == "ClearView RX" and e.extracted_index == 1.74
        and e.extracted_treatment_band == "Clear"
        and e.extracted_total_power_min == -20.0 and e.status != "needs_review"
    )
    _crud.confirm_extraction(db, ext.id, "qa")
    res = _crud.attach_range_to_existing_pricing(db, ext.id)
    assert "error" not in res, res

    db.refresh(vp_current)
    assert len(vp_current.power_ranges) == before_count, (
        "historical (closed) pricing must never receive a NEW PowerRange")
    assert len(vp_new.power_ranges) == 1, "only the current pricing row may receive it"


def test_4i_E_attach_cannot_cross_company(db):
    co_a = _mk_company(db, "ZeissLike")
    price_cat_a = _mk_catalog(db, co_a, status=models.CatalogStatus.CONFIRMED)
    _seed_zeisslike_pricing(
        db, co_a, price_cat_a, family="ClearView RX", index_value=1.74,
        material="high_index_1.74", treatment_band="Clear",
        coating_code="DuraVision Plus Gold", price=17400,
    )
    co_b = _mk_company(db, "OtherCompany")
    price_cat_b = _mk_catalog(db, co_b, status=models.CatalogStatus.CONFIRMED)
    # Coating.code is globally unique - a different (but equally valid) code
    # is fine; the point of this test is company isolation, not coating reuse.
    _model_b, _variant_b, vp_b = _seed_zeisslike_pricing(
        db, co_b, price_cat_b, family="ClearView RX", index_value=1.74,
        material="high_index_1.74", treatment_band="Clear",
        coating_code="DuraVision Plus Gold (Other Co)", price=17400,
    )
    # an extraction filed under company A's catalog must NEVER attach to
    # company B's identically-named/shaped model+variant+pricing.
    cat_a2 = models.Catalog(company_id=co_a.id, filename="ev.pdf", file_path="/x",
                            status=models.CatalogStatus.DRAFT)
    db.add(cat_a2); db.commit(); db.refresh(cat_a2)
    p = PDFHybridParser(use_vision=False)
    p.extracted_models = build_extracted_models(only_confidence="proven")
    p.save_extractions_to_db(cat_a2.id, db)
    ext = next(
        e for e in _crud.get_extractions_by_catalog(db, cat_a2.id)
        if e.extracted_name == "ClearView RX" and e.extracted_index == 1.74
        and e.extracted_treatment_band == "Clear"
        and e.extracted_total_power_min == -20.0 and e.status != "needs_review"
    )
    _crud.confirm_extraction(db, ext.id, "qa")
    _crud.attach_range_to_existing_pricing(db, ext.id)
    db.refresh(vp_b)
    assert vp_b.power_ranges == [], "must never attach across companies"


def test_4i_E_attach_cannot_touch_inactive_model(db):
    co, model, variant, vp = _seed_cv174(db)
    model.is_active = False
    db.commit()
    # re-attach attempt on a fresh extraction of the same evidence must fail
    cat = models.Catalog(company_id=co.id, filename="ev3.pdf", file_path="/x",
                         status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)
    p = PDFHybridParser(use_vision=False)
    p.extracted_models = build_extracted_models(only_confidence="proven")
    p.save_extractions_to_db(cat.id, db)
    ext = next(
        e for e in _crud.get_extractions_by_catalog(db, cat.id)
        if e.extracted_name == "ClearView RX" and e.extracted_index == 1.74
        and e.extracted_treatment_band == "Clear"
        and e.extracted_total_power_min == -20.0 and e.status != "needs_review"
    )
    _crud.confirm_extraction(db, ext.id, "qa")
    res = _crud.attach_range_to_existing_pricing(db, ext.id)
    assert "error" in res and "ACTIVE" in res["error"]
