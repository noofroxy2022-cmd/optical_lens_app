"""Phase 4K-final - explicit optical-subtype search filter, response
traceability, and review-schema plumbing for applicability_key.

LensFilters.applicability_key is a NEW, generic, nullable identity-agnostic
filter: unlike treatment_band (which selects WHICH commercial option to
consider), it selects WHICH PowerRange(s) of an already-selected option are
evaluated for eligibility. None (default) never changes behavior - every
pre-existing row (HOYA, and the 28 non-split ZEISS attachments) is
completely unaffected regardless of this field's presence.
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
from app import models, database, schemas, product_search  # noqa: E402


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


def _seed_split_offer(db, *, family="ClearView RX", price="25500.00"):
    """One real-shaped "Polarized / AdaptiveSun" offer with clean,
    non-overlapping POL (-4/+4) and AdaptiveSun (+10/+20) ranges."""
    co = models.Company(name="ZeissLike", country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename="x.pdf", file_path="/x",
                         status=models.CatalogStatus.CONFIRMED)
    db.add(cat); db.commit(); db.refresh(cat)
    model = models.LensModel(company_id=co.id, name=family, category=models.LensCategory.SINGLE_VISION)
    db.add(model); db.commit(); db.refresh(model)
    variant = models.LensVariant(
        lens_model_id=model.id, material="high_index_1.67", index_value=1.67,
        design_type=models.DesignType.SPHERICAL, is_aspherical=False,
        treatment_band="Polarized / AdaptiveSun", availability=models.LensAvailability.RX,
        price=0.0, currency="EGP")
    db.add(variant); db.commit(); db.refresh(variant)
    coating = models.Coating(code="DuraVision Plus Gold", name="DuraVision Plus Gold")
    db.add(coating); db.commit(); db.refresh(coating)
    vp = models.VariantPricing(
        variant_id=variant.id, coating_id=coating.id, availability=models.PricingAvailability.RX,
        power_eligibility=models.PowerEligibilityStatus.UNRESOLVED, price_pair=Decimal(price),
        currency="EGP", source_catalog_id=cat.id, effective_from=datetime.utcnow(),
        effective_to=None, power_scope=None, market_scope=None)
    db.add(vp); db.commit(); db.refresh(vp)
    pol_pr = models.PowerRange(
        lens_model_id=model.id, variant_id=variant.id, pricing_id=vp.id,
        sph_min=-4.0, sph_max=4.0, cyl_min=-4.0, cyl_max=0.0,
        total_power_min=-4.0, total_power_max=4.0, max_cyl_abs=4.0, applicability_key="POL")
    as_pr = models.PowerRange(
        lens_model_id=model.id, variant_id=variant.id, pricing_id=vp.id,
        sph_min=10.0, sph_max=20.0, cyl_min=-4.0, cyl_max=0.0,
        total_power_min=10.0, total_power_max=20.0, max_cyl_abs=4.0, applicability_key="AdaptiveSun")
    db.add(pol_pr); db.add(as_pr); db.commit()
    db.refresh(vp)
    return co, model, variant, vp


# ============================================================
# A/B. explicit filter, both eyes eligible under the SAME requested subtype
# ============================================================
def test_A_pol_filter_both_eyes_pol_eligible_pair_allowed(db):
    co, model, variant, vp = _seed_split_offer(db)
    presc = _mk_presc(db, 0.0, -2.0, 0.0, -2.0)   # inside POL only
    f = schemas.LensFilters(lens_model_id=model.id, applicability_key="POL")
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(mode="targeted", filters=f))
    bm = resp.best_match
    assert bm is not None
    assert bm.pair_fulfillment.status == "rx"
    assert bm.pair_fulfillment.price_pair == Decimal("25500.00")
    assert bm.pair_fulfillment.applicability_key == "POL"


def test_B_adaptivesun_filter_both_eyes_adaptivesun_eligible_pair_allowed(db):
    co, model, variant, vp = _seed_split_offer(db)
    presc = _mk_presc(db, 15.0, -2.0, 15.0, -2.0)   # inside AdaptiveSun only
    f = schemas.LensFilters(lens_model_id=model.id, applicability_key="AdaptiveSun")
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(mode="targeted", filters=f))
    bm = resp.best_match
    assert bm is not None
    assert bm.pair_fulfillment.status == "rx"
    assert bm.pair_fulfillment.price_pair == Decimal("25500.00")
    assert bm.pair_fulfillment.applicability_key == "AdaptiveSun"


# ============================================================
# C/D. explicit filter must NOT use the OTHER subtype's range
# ============================================================
def test_C_pol_filter_when_only_adaptivesun_covers_is_ineligible(db):
    co, model, variant, vp = _seed_split_offer(db)
    presc = _mk_presc(db, 15.0, -2.0, 15.0, -2.0)   # only AdaptiveSun covers this
    f = schemas.LensFilters(lens_model_id=model.id, applicability_key="POL")
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(mode="targeted", filters=f))
    bm = resp.best_match
    assert bm is not None
    assert bm.od.rx is False and bm.od.rx_unknown is False   # proven ineligible, not unknown
    assert bm.pair_fulfillment.price_pair is None
    assert bm.pair_fulfillment.status not in ("stock_egypt", "stock_outside", "rx")


def test_D_adaptivesun_filter_when_only_pol_covers_is_ineligible(db):
    co, model, variant, vp = _seed_split_offer(db)
    presc = _mk_presc(db, 0.0, -2.0, 0.0, -2.0)   # only POL covers this
    f = schemas.LensFilters(lens_model_id=model.id, applicability_key="AdaptiveSun")
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(mode="targeted", filters=f))
    bm = resp.best_match
    assert bm is not None
    assert bm.od.rx is False and bm.od.rx_unknown is False
    assert bm.pair_fulfillment.price_pair is None


# ============================================================
# E. no subtype filter, disjoint per-eye subtype -> no proven pair
# ============================================================
def test_E_no_filter_disjoint_per_eye_subtype_no_proven_pair(db):
    co, model, variant, vp = _seed_split_offer(db)
    presc = _mk_presc(db, 0.0, -2.0, 15.0, -2.0)   # OD only POL, OS only AdaptiveSun
    f = schemas.LensFilters(lens_model_id=model.id)   # no applicability_key
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(mode="targeted", filters=f))
    bm = resp.best_match
    assert bm is not None
    assert bm.od.rx is True and bm.os.rx is True   # each eye genuinely eligible on its own
    assert bm.pair_fulfillment.price_pair is None   # but never a silently-proven mixed pair
    assert bm.pair_fulfillment.applicability_key is None


# ============================================================
# F. normal HOYA rows (applicability_key=NULL everywhere) unchanged
# ============================================================
def test_F_hoya_rows_unaffected_by_new_filter_field(db):
    co = models.Company(name="HOYA", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename="x", file_path="/x",
                         status=models.CatalogStatus.CONFIRMED)
    db.add(cat); db.commit(); db.refresh(cat)
    model = models.LensModel(company_id=co.id, name="Nulux", category=models.LensCategory.SINGLE_VISION)
    db.add(model); db.commit(); db.refresh(model)
    variant = models.LensVariant(
        lens_model_id=model.id, material=models.MaterialType.CR39, index_value=1.5,
        design_type=models.DesignType.SPHERICAL, is_aspherical=False, price=0.0, currency="EGP")
    db.add(variant); db.commit(); db.refresh(variant)
    pricing = models.VariantPricing(
        variant_id=variant.id, availability=models.PricingAvailability.RX,
        power_eligibility=models.PowerEligibilityStatus.UNRESOLVED, price_pair=Decimal("100.00"),
        currency="EGP", source_catalog_id=cat.id)
    db.add(pricing); db.commit(); db.refresh(pricing)
    pr = models.PowerRange(lens_model_id=model.id, variant_id=variant.id, pricing_id=pricing.id,
                           sph_min=-4.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0)
    db.add(pr); db.commit()
    presc = _mk_presc(db, -2.0, -0.5, -2.0, -0.5)

    # WITHOUT the new filter (baseline)
    f0 = schemas.LensFilters(lens_model_id=model.id)
    resp0 = product_search.search(db, presc, schemas.ProductSearchRequest(mode="targeted", filters=f0))
    # WITH the new filter set to something that has no meaning for this
    # never-split row - must be a complete no-op (see _applicable_ranges)
    f1 = schemas.LensFilters(lens_model_id=model.id, applicability_key="POL")
    resp1 = product_search.search(db, presc, schemas.ProductSearchRequest(mode="targeted", filters=f1))

    assert resp0.best_match.pair_fulfillment.status == resp1.best_match.pair_fulfillment.status == "rx"
    assert resp0.best_match.pair_fulfillment.price_pair == resp1.best_match.pair_fulfillment.price_pair
    assert resp1.best_match.pair_fulfillment.applicability_key is None


# ============================================================
# Response traceability: PairFulfillment.applicability_key + power_range
# schema both carry it
# ============================================================
def test_proving_subtype_exposed_on_powerrange_schema():
    prs = schemas.PowerRangeBase(sph_min=-4.0, sph_max=4.0, applicability_key="POL")
    assert prs.applicability_key == "POL"


def test_pair_fulfillment_schema_has_applicability_key_field():
    pf = schemas.PairFulfillment(status="rx", reason="x")
    assert hasattr(pf, "applicability_key")
    assert pf.applicability_key is None   # default


# ============================================================
# Review/API plumbing: CatalogExtraction schemas carry
# extracted_applicability_key end to end
# ============================================================
def test_extraction_response_schema_carries_applicability_key():
    assert "extracted_applicability_key" in schemas.CatalogExtractionResponse.model_fields


def test_extraction_update_schema_lets_reviewer_correct_applicability_key():
    upd = schemas.CatalogExtractionUpdate(extracted_applicability_key="AdaptiveSun")
    assert upd.extracted_applicability_key == "AdaptiveSun"
    # exclude_unset semantics (what crud.update_extraction actually applies)
    dumped = upd.model_dump(exclude_unset=True)
    assert dumped == {"extracted_applicability_key": "AdaptiveSun"}


def test_extraction_to_powerrange_reviewer_correction_flows_through(db):
    """A human reviewer can SEE and CORRECT extracted_applicability_key, and
    that correction is what attach_range_to_existing_pricing actually uses -
    the full extraction -> review -> confirmation -> PowerRange path."""
    from app import crud
    from app.pdf_hybrid_parser import PDFHybridParser, ExtractedLensModel, ExtractedPowerRange

    co, model, variant, vp = _seed_split_offer(db, price="9999.00")
    cat = models.Catalog(company_id=co.id, filename="ev.pdf", file_path="/x",
                         status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)

    # simulate a parser that got the wrong applicability_key ("AdaptiveSun"
    # for what is really a POL range) - the reviewer must be able to fix it.
    pr = ExtractedPowerRange(
        sph_min=-4.0, sph_max=4.0, cyl_min=-4.0, cyl_max=0.0,
        index_value=1.67, material="high_index_1.67", availability="rx",
        treatment_band="Polarized / AdaptiveSun", applicability_key="AdaptiveSun",
        power_eligibility="unresolved", has_range=True,
        total_power_min=-4.0, total_power_max=4.0, max_cyl_abs=4.0,
    )
    p = PDFHybridParser(use_vision=False)
    p.extracted_models = [ExtractedLensModel(name="ClearView RX", category="single_vision", power_ranges=[pr])]
    p.save_extractions_to_db(cat.id, db)
    ext = crud.get_extractions_by_catalog(db, cat.id)[0]
    assert ext.extracted_applicability_key == "AdaptiveSun"   # visible to a reviewer

    # reviewer corrects it to "POL"
    crud.update_extraction(db, ext.id, schemas.CatalogExtractionUpdate(extracted_applicability_key="POL"))
    db.refresh(ext)
    assert ext.extracted_applicability_key == "POL"           # correction persisted

    crud.confirm_extraction(db, ext.id, "qa")
    res = crud.attach_range_to_existing_pricing(db, ext.id)
    assert "error" not in res, res
    created = db.query(models.PowerRange).filter(models.PowerRange.id.in_(res["created"])).all()
    assert all(p.applicability_key == "POL" for p in created), "reviewer's correction must be what gets persisted"
