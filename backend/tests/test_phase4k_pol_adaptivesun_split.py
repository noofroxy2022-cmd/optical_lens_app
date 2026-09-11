"""Phase 4K - one commercial price, two optically distinct sub-options.

The real ZEISS SV-RX price grid (Phase 4J) prices "POL" and "AdaptiveSun"
together as ONE commercial offer literally named "Polarized / AdaptiveSun"
(confirmed: one LensVariant, one price_pair per coating/index), while the
graphical power-range chart proves POL and AdaptiveSun have DIFFERENT power
ranges. This is a real grain mismatch, resolved with a nullable
PowerRange.applicability_key (Option A - smallest schema extension, no new
table, no duplicated price/SKU) plus a pair-fulfillment same-subtype
requirement in product_search._pair_fulfillment (a bare "one row covers both
eyes" check is not enough once a row can carry more than one optical
sub-option under one price).

Generic, not ZEISS-specific: applicability_key is a plain nullable string
column; NULL (every pre-existing row, HOYA included) behaves exactly as
before. Nothing here branches on manufacturer/family/treatment name in
lens_matcher.py or product_search.py - "POL"/"AdaptiveSun" only ever appear
as catalog-specific EVIDENCE data (zeiss_svrx_graphical_evidence.py).
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
from app.lens_matcher import lens_matcher as _matcher  # noqa: E402
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


def _seed_merged_offer(db, *, family="ClearView RX", index_value=1.67,
                       material="high_index_1.67", price="25500.00"):
    """One real-shaped "Polarized / AdaptiveSun" priced offer, matching the
    Phase 4J-reconstructed real identity exactly (one LensModel, one
    LensVariant, one VariantPricing - no fake second SKU)."""
    co = models.Company(name="ZeissLike", country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    price_cat = models.Catalog(company_id=co.id, filename="synthetic.pdf",
                               file_path="/x", status=models.CatalogStatus.CONFIRMED)
    db.add(price_cat); db.commit(); db.refresh(price_cat)
    model = models.LensModel(company_id=co.id, name=family, category=models.LensCategory.SINGLE_VISION)
    db.add(model); db.commit(); db.refresh(model)
    variant = models.LensVariant(
        lens_model_id=model.id, material=material, index_value=index_value,
        design_type=models.DesignType.SPHERICAL, is_aspherical=False,
        treatment_band="Polarized / AdaptiveSun", availability=models.LensAvailability.RX,
        price=0.0, currency="EGP",
    )
    db.add(variant); db.commit(); db.refresh(variant)
    coating = models.Coating(code="DuraVision Plus Gold", name="DuraVision Plus Gold")
    db.add(coating); db.commit(); db.refresh(coating)
    vp = models.VariantPricing(
        variant_id=variant.id, coating_id=coating.id,
        availability=models.PricingAvailability.RX,
        power_eligibility=models.PowerEligibilityStatus.UNRESOLVED,
        price_pair=Decimal(price), currency="EGP", source_catalog_id=price_cat.id,
        effective_from=datetime.utcnow(), effective_to=None,
        power_scope=None, market_scope=None,
    )
    db.add(vp); db.commit(); db.refresh(vp)
    return co, model, variant, vp


def _attach_pol_adaptivesun(db, *, family="ClearView RX"):
    """Confirm and attach every proven evidence row for `family` - only the
    real POL/AdaptiveSun combos remap; everything else is untouched."""
    co = db.query(models.Company).filter(models.Company.name == "ZeissLike").first()
    cat = models.Catalog(company_id=co.id, filename="ev.pdf", file_path="/x",
                         status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)
    p = PDFHybridParser(use_vision=False)
    p.extracted_models = build_extracted_models(only_confidence="proven")
    p.save_extractions_to_db(cat.id, db)
    results = []
    for e in _crud.get_extractions_by_catalog(db, cat.id):
        if e.status == "needs_review" or e.extracted_name != family:
            continue
        _crud.confirm_extraction(db, e.id, "qa")
        results.append((e, _crud.attach_range_to_existing_pricing(db, e.id)))
    return results


# ============================================================
# 1. one price, two optical-subtype ranges - both attach to the ONE offer
# ============================================================
def test_4k_one_price_two_subtype_ranges_attach_to_one_offer(db):
    co, model, variant, vp = _seed_merged_offer(db)
    _attach_pol_adaptivesun(db)
    db.refresh(vp)
    keys = {pr.applicability_key for pr in vp.power_ranges}
    assert "POL" in keys and "AdaptiveSun" in keys
    # exactly one VariantPricing row, one price, no fake second SKU
    assert db.query(models.VariantPricing).filter(
        models.VariantPricing.variant_id == variant.id).count() == 1
    assert vp.price_pair == Decimal("25500.00")


def _seed_synthetic_split_offer(db):
    """A clean, hand-crafted "one price, two NON-OVERLAPPING sub-option
    ranges" offer - isolates the discrimination mechanism itself from the
    incidental geometry of ClearView RX 1.67's real printed numbers (whose
    POL/AdaptiveSun zones happen to nest inside each other in places)."""
    co, model, variant, vp = _seed_merged_offer(db, index_value=1.99, price="12345.00")
    pol_pr = models.PowerRange(
        lens_model_id=model.id, variant_id=variant.id, pricing_id=vp.id,
        sph_min=-4.0, sph_max=4.0, cyl_min=-4.0, cyl_max=0.0,
        total_power_min=-4.0, total_power_max=4.0, max_cyl_abs=4.0,
        applicability_key="POL",
    )
    as_pr = models.PowerRange(
        lens_model_id=model.id, variant_id=variant.id, pricing_id=vp.id,
        sph_min=10.0, sph_max=20.0, cyl_min=-4.0, cyl_max=0.0,
        total_power_min=10.0, total_power_max=20.0, max_cyl_abs=4.0,
        applicability_key="AdaptiveSun",
    )
    db.add(pol_pr); db.add(as_pr); db.commit()
    db.refresh(vp)
    return co, model, variant, vp


# ============================================================
# 2/3. POL eligible & AdaptiveSun ineligible, and the reverse
# ============================================================
def test_4k_pol_eligible_adaptivesun_ineligible(db):
    co, model, variant, vp = _seed_synthetic_split_offer(db)
    pol_pr = next(pr for pr in vp.power_ranges if pr.applicability_key == "POL")
    as_pr = next(pr for pr in vp.power_ranges if pr.applicability_key == "AdaptiveSun")
    presc = _mk_presc(db, 0.0, -2.0, 0.0, -2.0)   # M1=0, M2=-2: inside POL, outside AdaptiveSun
    assert _matcher.check_power_range(pol_pr, presc, "od")[0] is True
    assert _matcher.check_power_range(as_pr, presc, "od")[0] is False


def test_4k_adaptivesun_eligible_pol_ineligible(db):
    co, model, variant, vp = _seed_synthetic_split_offer(db)
    pol_pr = next(pr for pr in vp.power_ranges if pr.applicability_key == "POL")
    as_pr = next(pr for pr in vp.power_ranges if pr.applicability_key == "AdaptiveSun")
    presc = _mk_presc(db, 15.0, -2.0, 15.0, -2.0)   # M1=15, M2=13: inside AdaptiveSun, outside POL
    assert _matcher.check_power_range(as_pr, presc, "od")[0] is True
    assert _matcher.check_power_range(pol_pr, presc, "od")[0] is False


# ============================================================
# 4. same subtype both eyes -> pair allowed (proven, catalog price)
# ============================================================
def test_4k_same_subtype_both_eyes_pair_allowed(db):
    co, model, variant, vp = _seed_synthetic_split_offer(db)
    # both eyes squarely inside POL only
    presc = _mk_presc(db, 0.0, -2.0, 0.0, -2.0)
    od_keys = product_search._row_eye_proving_keys(vp, presc, "od")
    os_keys = product_search._row_eye_proving_keys(vp, presc, "os")
    assert od_keys == os_keys == frozenset({"POL"})
    routes = {"stock_egypt": [], "stock_outside": [], "rx": [vp]}
    od_avail = product_search._eye_availability(routes, presc, "od")
    os_avail = product_search._eye_availability(routes, presc, "os")
    pf = product_search._pair_fulfillment(routes, od_avail, os_avail, presc)
    assert pf.status == "rx"
    assert pf.price_pair == Decimal("12345.00")
    assert pf.provenance == "single_route"


# ============================================================
# 5. different subtype per eye -> no silent pair mixing
# ============================================================
def test_4k_mixed_subtype_per_eye_no_silent_pair(db):
    co, model, variant, vp = _seed_synthetic_split_offer(db)
    # OD inside POL only (0,-2); OS inside AdaptiveSun only (15,-2)
    presc = _mk_presc(db, 0.0, -2.0, 15.0, -2.0)
    od_keys = product_search._row_eye_proving_keys(vp, presc, "od")
    os_keys = product_search._row_eye_proving_keys(vp, presc, "os")
    assert od_keys == frozenset({"POL"})
    assert os_keys == frozenset({"AdaptiveSun"})
    assert od_keys & os_keys == frozenset()   # disjoint - the danger case
    routes = {"stock_egypt": [], "stock_outside": [], "rx": [vp]}
    od_avail = product_search._eye_availability(routes, presc, "od")
    os_avail = product_search._eye_availability(routes, presc, "os")
    assert od_avail.rx is True and os_avail.rx is True   # each eye genuinely eligible...
    pf = product_search._pair_fulfillment(routes, od_avail, os_avail, presc)
    # ...but NEVER a silently-proven same-price pair across mismatched subtypes
    assert pf.price_pair is None
    assert pf.provenance != "single_route"
    assert pf.needs_review is True


# ============================================================
# 6. targeted subtype filter (LensFilters.treatment_band) still strict AND
# ============================================================
def test_4k_targeted_treatment_band_filter_finds_merged_offer(db):
    co, model, variant, vp = _seed_merged_offer(db)
    _attach_pol_adaptivesun(db)
    f = schemas.LensFilters(lens_model_id=model.id, treatment_band="Polarized / AdaptiveSun")
    presc = _mk_presc(db, 0.0, -2.0, 0.0, -2.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(mode="targeted", filters=f))
    assert resp.best_match is not None
    assert resp.best_match.treatment_band == "Polarized / AdaptiveSun"


# ============================================================
# 7/8. automatic search: no duplicate commercial result, price shown once
# ============================================================
def test_4k_no_duplicate_commercial_result_price_shown_once(db):
    co, model, variant, vp = _seed_merged_offer(db)
    _attach_pol_adaptivesun(db)
    presc = _mk_presc(db, 0.0, -2.0, 0.0, -2.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(
        mode="targeted", filters=schemas.LensFilters(lens_model_id=model.id)))
    matches = [r for g in resp.groups for r in g.results if r.variant_id == variant.id]
    assert len(matches) == 1, "two PowerRanges under one price must not multiply results"
    prices = {m.pair_fulfillment.price_pair for m in matches if m.pair_fulfillment.price_pair}
    assert prices in ({Decimal("25500.00")}, set())  # never multiplied/split


# ============================================================
# 9. alternatives respect subtype (proven-eligible offer appears once)
# ============================================================
def test_4k_alternatives_show_merged_offer_once(db):
    co, model, variant, vp = _seed_merged_offer(db)
    _attach_pol_adaptivesun(db)
    presc = _mk_presc(db, 0.0, -2.0, 0.0, -2.0)
    f = schemas.LensFilters(lens_model_id=999999)   # force alternatives path
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(
        mode="targeted", filters=f, include_alternatives=True))
    alt_ids = [a.result.source_pricing_id for a in resp.alternatives if a.result.source_pricing_id == vp.id]
    assert len(alt_ids) <= 1, "the merged offer must not appear twice in alternatives"


# ============================================================
# 10. unresolved subtype (SPH RX @ 1.67 - no real merged SKU) fail-closed
# ============================================================
def test_4k_no_real_sku_combo_stays_unattached_fail_closed(db):
    # SPH RX @ 1.67 is deliberately excluded from the merge map
    # (_POL_ADAPTIVESUN_REAL_COMBOS - Phase 4J confirmed no "Polarized /
    # AdaptiveSun" SKU exists there, only at 1.5/1.6). Seed the MERGED name
    # anyway (what a buggy implementation might wrongly expect to receive
    # the POL range) and confirm it never gets fabricated a match: the
    # evidence for SPH RX @ 1.67 POL stays literal "POL", never becomes
    # "Polarized / AdaptiveSun", so this variant must receive nothing.
    co = models.Company(name="ZeissLike", country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    price_cat = models.Catalog(company_id=co.id, filename="x", file_path="/x",
                               status=models.CatalogStatus.CONFIRMED)
    db.add(price_cat); db.commit(); db.refresh(price_cat)
    model = models.LensModel(company_id=co.id, name="SPH RX", category=models.LensCategory.SINGLE_VISION)
    db.add(model); db.commit(); db.refresh(model)
    variant = models.LensVariant(
        lens_model_id=model.id, material="high_index_1.67", index_value=1.67,
        design_type=models.DesignType.SPHERICAL, is_aspherical=False,
        treatment_band="Polarized / AdaptiveSun", availability=models.LensAvailability.RX,
        price=0.0, currency="EGP")
    db.add(variant); db.commit(); db.refresh(variant)
    coating = models.Coating(code="C1", name="C1")
    db.add(coating); db.commit(); db.refresh(coating)
    vp = models.VariantPricing(
        variant_id=variant.id, coating_id=coating.id, availability=models.PricingAvailability.RX,
        power_eligibility=models.PowerEligibilityStatus.UNRESOLVED, price_pair=Decimal("9999.00"),
        currency="EGP", source_catalog_id=price_cat.id, effective_from=datetime.utcnow(),
        effective_to=None, power_scope=None, market_scope=None)
    db.add(vp); db.commit(); db.refresh(vp)

    _attach_pol_adaptivesun(db, family="SPH RX")
    db.refresh(vp)
    assert vp.power_ranges == []


# ============================================================
# 11. retry/idempotency across the split attach
# ============================================================
def test_4k_idempotent_retry_no_duplicate_powerrange(db):
    co, model, variant, vp = _seed_merged_offer(db)
    r1 = _attach_pol_adaptivesun(db)
    r2 = _attach_pol_adaptivesun(db)
    created1 = sum(len(r["created"]) for _e, r in r1 if "error" not in r)
    created2 = sum(len(r["created"]) for _e, r in r2 if "error" not in r)
    assert created1 > 0
    assert created2 == 0, "second attach pass must reuse, never duplicate"
    db.refresh(vp)
    # exactly one PowerRange per (bound, key) - counted once regardless of
    # how many times attach ran
    seen = {(pr.total_power_min, pr.total_power_max, pr.applicability_key) for pr in vp.power_ranges}
    assert len(seen) == len(vp.power_ranges)


# ============================================================
# 12. HOYA unchanged - no PowerRange gets a non-null applicability_key
# ============================================================
def test_4k_hoya_power_ranges_have_null_applicability_key(db):
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
    assert pr.applicability_key is None
    presc = _mk_presc(db, -2.0, -0.5, -2.0, -0.5)
    ok, _ = _matcher.check_power_range(pr, presc, "od")
    assert ok is True
    keys = product_search._row_eye_proving_keys(pricing, presc, "od")
    assert keys == frozenset({None})
