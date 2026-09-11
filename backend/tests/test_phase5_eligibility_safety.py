"""Phase 5 - permanent regression coverage for the ZEISS Phase 3/3B/3C power-
eligibility safety invariants.

Deliberately synthetic and minimal: builds Company -> LensModel -> LensVariant
-> VariantPricing (+ PowerRange where needed) directly via the ORM, with no
PDF parsing and no large E2E fixture, so this suite stays fast and focused on
ONE thing - that an UNRESOLVED (or genuinely ineligible) commercial option can
never be reported, anywhere in the prescription-matching surface, as a proven
compatible lens; and that the pre-existing UNRESTRICTED ("RX made-to-order")
behaviour a real catalog like HOYA relies on is completely unaffected.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from decimal import Decimal

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database import Base  # noqa: E402
from app import models, database, schemas, product_search  # noqa: E402
from app.pdf_hybrid_parser import ExtractedPowerRange  # noqa: E402
from app.routers.prescriptions import (  # noqa: E402
    match_lenses as match_endpoint,
    product_search as search_endpoint,
)


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


# --------------------------------------------------------------- fixtures
def _mk_company(db, name):
    co = models.Company(name=name, country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    return co


def _mk_catalog(db, company):
    cat = models.Catalog(company_id=company.id, filename="synthetic.pdf",
                         file_path="synthetic.pdf", status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)
    return cat


def _mk_variant(db, model, index_value=1.5):
    v = models.LensVariant(
        lens_model_id=model.id, material=models.MaterialType.CR39, index_value=index_value,
        design_type=models.DesignType.SPHERICAL, is_aspherical=False, price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    return v


def _mk_pricing(db, variant, catalog, *, availability, power_eligibility, price,
                power_scope=None):
    vp = models.VariantPricing(
        variant_id=variant.id, availability=availability, power_eligibility=power_eligibility,
        price_pair=Decimal(str(price)), currency="EGP", source_catalog_id=catalog.id,
        power_scope=power_scope)
    db.add(vp); db.commit(); db.refresh(vp)
    return vp


def _mk_range(db, model, variant, pricing, sph_min, sph_max, cyl_min=-4.0, cyl_max=0.0):
    pr = models.PowerRange(lens_model_id=model.id, variant_id=variant.id, pricing_id=pricing.id,
                           sph_min=sph_min, sph_max=sph_max, cyl_min=cyl_min, cyl_max=cyl_max)
    db.add(pr); db.commit()
    return pr


def _mk_presc(db, sph, cyl, name="p"):
    p = models.Prescription(
        customer_name=name, od_sph_original=sph, od_cyl_original=cyl, od_axis_original=90,
        od_sph=sph, od_cyl=cyl, od_axis=90, os_sph_original=sph, os_cyl_original=cyl,
        os_axis_original=90, os_sph=sph, os_cyl=cyl, os_axis=90, pd=63)
    db.add(p); db.commit(); db.refresh(p)
    return p


def _targeted(db, presc, model, **extra_filters):
    f = schemas.LensFilters(lens_model_id=model.id, **extra_filters)
    req = schemas.ProductSearchRequest(mode="targeted", filters=f)
    return product_search.search(db, presc, req)


# ===========================================================================
# A. power_eligibility=UNRESOLVED never becomes proven eligible in /search
# ===========================================================================
def test_A_unresolved_never_proven_in_search(db):
    co = _mk_company(db, "ZeissLike")
    cat = _mk_catalog(db, co)
    model = models.LensModel(company_id=co.id, name="UnresolvedModel",
                             category=models.LensCategory.SINGLE_VISION)
    db.add(model); db.commit(); db.refresh(model)
    variant = _mk_variant(db, model)
    _mk_pricing(db, variant, cat, availability=models.PricingAvailability.RX,
               power_eligibility=models.PowerEligibilityStatus.UNRESOLVED, price=17400)

    for label, presc in (("normal", _mk_presc(db, -2.0, -0.5)),
                        ("extreme", _mk_presc(db, -25.0, -9.0))):
        resp = _targeted(db, presc, model)
        bm = resp.best_match
        assert bm is not None, label
        assert bm.pair_fulfillment.status == "eligibility_unknown", label
        assert bm.pair_fulfillment.price_pair is None, label
        assert bm.od.rx is False and bm.od.rx_unknown is True, label
        assert bm.os.rx is False and bm.os.rx_unknown is True, label
        assert resp.availability_answer.title == (
            "المنتج موجود في الكتالوج، لكن توافقه مع هذه الوصفة غير مؤكد بسبب نطاق القوة."), label
        assert "متاح RX" not in resp.availability_answer.title, label


# ===========================================================================
# B. deprecated /match uses the same safe ProductSearch path -> same result
# ===========================================================================
def test_B_match_endpoint_matches_search_endpoint_safety(db):
    co = _mk_company(db, "ZeissLike")
    cat = _mk_catalog(db, co)
    model = models.LensModel(company_id=co.id, name="UnresolvedModel2",
                             category=models.LensCategory.SINGLE_VISION)
    db.add(model); db.commit(); db.refresh(model)
    variant = _mk_variant(db, model)
    _mk_pricing(db, variant, cat, availability=models.PricingAvailability.RX,
               power_eligibility=models.PowerEligibilityStatus.UNRESOLVED, price=9999)
    presc = _mk_presc(db, -2.0, -0.5)

    f = schemas.LensFilters(lens_model_id=model.id)
    search_resp = search_endpoint(prescription_id=presc.id,
                                  req=schemas.ProductSearchRequest(mode="targeted", filters=f),
                                  db=db)
    match_resp = match_endpoint(prescription_id=presc.id, filters=f,
                                prefer_stock=True, prefer_aspherical=True, db=db)

    for tag, resp in (("search", search_resp), ("match", match_resp)):
        bm = resp.best_match
        assert bm is not None, tag
        assert bm.pair_fulfillment.status == "eligibility_unknown", tag
        assert bm.pair_fulfillment.price_pair is None, tag

    assert search_resp.availability_answer.code == match_resp.availability_answer.code
    assert search_resp.exact_total == match_resp.exact_total
    assert search_resp.best_match.pair_fulfillment.status == match_resp.best_match.pair_fulfillment.status


# ===========================================================================
# C/D. alternatives pool: unresolved excluded, proven-eligible allowed
# ===========================================================================
def test_CD_alternatives_exclude_unresolved_but_allow_proven_eligible(db):
    co_z = _mk_company(db, "ZeissLike")
    cat_z = _mk_catalog(db, co_z)
    unresolved_model = models.LensModel(company_id=co_z.id, name="UnresolvedAlt",
                                        category=models.LensCategory.SINGLE_VISION)
    db.add(unresolved_model); db.commit(); db.refresh(unresolved_model)
    unresolved_variant = _mk_variant(db, unresolved_model, index_value=1.6)
    unresolved_vp = _mk_pricing(db, unresolved_variant, cat_z,
                               availability=models.PricingAvailability.RX,
                               power_eligibility=models.PowerEligibilityStatus.UNRESOLVED,
                               price=8800)

    co_h = _mk_company(db, "HoyaLike")
    cat_h = _mk_catalog(db, co_h)
    proven_model = models.LensModel(company_id=co_h.id, name="ProvenAlt",
                                    category=models.LensCategory.SINGLE_VISION)
    db.add(proven_model); db.commit(); db.refresh(proven_model)
    proven_variant = _mk_variant(db, proven_model, index_value=1.6)
    proven_vp = _mk_pricing(db, proven_variant, cat_h,
                           availability=models.PricingAvailability.RX,
                           power_eligibility=models.PowerEligibilityStatus.UNRESTRICTED,
                           price=4200)   # genuinely unrestricted RX, no range needed

    presc = _mk_presc(db, -2.0, -0.5)

    # targeted search for a THIRD, nonexistent product -> 0 exact identity
    # matches, no availability/market/price gate -> alternatives path fires
    # against the whole catalog.
    f = schemas.LensFilters(lens_model_id=999999)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(
        mode="targeted", filters=f, include_alternatives=True))

    alt_ids = {a.result.source_pricing_id for a in resp.alternatives}
    assert unresolved_vp.id not in alt_ids, "unresolved candidate leaked into alternatives"
    assert proven_vp.id in alt_ids, "proven-eligible candidate was wrongly excluded"


# ===========================================================================
# E. eligibility_unknown pair_fulfillment.price_pair is None / non-actionable
# ===========================================================================
def test_E_eligibility_unknown_never_actionable(db):
    co = _mk_company(db, "ZeissLike")
    cat = _mk_catalog(db, co)
    model = models.LensModel(company_id=co.id, name="UnknownActionable",
                             category=models.LensCategory.SINGLE_VISION)
    db.add(model); db.commit(); db.refresh(model)
    variant = _mk_variant(db, model)
    _mk_pricing(db, variant, cat, availability=models.PricingAvailability.RX,
               power_eligibility=models.PowerEligibilityStatus.UNRESOLVED, price=12345)
    presc = _mk_presc(db, -2.0, -0.5)

    resp = _targeted(db, presc, model)
    pf = resp.best_match.pair_fulfillment
    assert pf.status == "eligibility_unknown"
    assert pf.price_pair is None
    assert pf.currency is None
    assert pf.provenance == "none"
    assert pf.needs_review is True
    # never one of the tiers that a caller could treat as a proven, orderable route
    assert pf.status not in ("stock_egypt", "stock_outside", "rx")


# ===========================================================================
# F. a new ExtractedPowerRange construction without power_eligibility fails
#    loudly (fail-closed) instead of silently defaulting to UNRESTRICTED
# ===========================================================================
def test_F_extracted_power_range_requires_explicit_power_eligibility():
    with pytest.raises(TypeError):
        ExtractedPowerRange(sph_min=0.0, sph_max=0.0, price=100.0)   # no power_eligibility

    # explicit values are accepted and round-trip verbatim
    ok_unrestricted = ExtractedPowerRange(sph_min=0.0, sph_max=0.0, price=100.0,
                                          power_eligibility="unrestricted")
    ok_unresolved = ExtractedPowerRange(sph_min=0.0, sph_max=0.0, price=100.0,
                                        power_eligibility="unresolved")
    assert ok_unrestricted.power_eligibility == "unrestricted"
    assert ok_unresolved.power_eligibility == "unresolved"


# ===========================================================================
# G. HOYA-shaped UNRESTRICTED behaviour remains valid (unchanged)
# ===========================================================================
def test_G_unrestricted_still_eligible_like_hoya(db):
    co = _mk_company(db, "HoyaLike2")
    cat = _mk_catalog(db, co)
    model = models.LensModel(company_id=co.id, name="HoyaStyleRxMTO",
                             category=models.LensCategory.SINGLE_VISION)
    db.add(model); db.commit(); db.refresh(model)
    variant = _mk_variant(db, model)
    # RX made-to-order, no PowerRange, power_eligibility=UNRESTRICTED (the
    # default every pre-Phase-3 HOYA-shaped extraction path writes explicitly)
    _mk_pricing(db, variant, cat, availability=models.PricingAvailability.RX,
               power_eligibility=models.PowerEligibilityStatus.UNRESTRICTED, price=3500)

    for label, presc in (("normal", _mk_presc(db, -2.0, -0.5)),
                        ("extreme", _mk_presc(db, -25.0, -9.0))):
        resp = _targeted(db, presc, model)
        bm = resp.best_match
        assert bm is not None, label
        assert bm.pair_fulfillment.status == "rx", label
        assert bm.pair_fulfillment.price_pair == Decimal("3500.00"), label
        assert bm.od.rx is True and bm.od.rx_unknown is False, label
        assert bm.os.rx is True and bm.os.rx_unknown is False, label
