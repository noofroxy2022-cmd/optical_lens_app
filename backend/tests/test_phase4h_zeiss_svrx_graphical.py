"""Phase 4H - ZEISS SV-RX graphical power-range chart -> G3 PowerRange.

Proves the generic extraction/persistence path end-to-end using the real
chart evidence in app.zeiss_svrx_graphical_evidence, WITHOUT going through
confirm_catalog_commercial (which would supersede/close existing company
pricing and requires a price - wrong tool for range-only evidence). The
"already-confirmed 315 ZEISS price rows" this phase must link against are
represented here by a synthetic but structurally faithful fixture (this
suite has no access to a real ZEISS PDF price-table parse); the same
attach_range_to_existing_pricing() call path applies identically to the real
315 rows since nothing here is ZEISS-specific in code, only in evidence data.
"""
import os
import sys
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database import Base  # noqa: E402
from app import models, database, crud as _crud  # noqa: E402
from app.pdf_hybrid_parser import PDFHybridParser  # noqa: E402
from app.lens_matcher import lens_matcher as _matcher, TranspositionEngine as _TE  # noqa: E402
from app.zeiss_svrx_graphical_evidence import (  # noqa: E402
    build_extracted_models, ALL_ROWS, ChartRow,
)


def _row(family, index_value, treatment_band, diameter_zone):
    return next(
        r for r in ALL_ROWS
        if r.family == family and r.index_value == index_value
        and r.treatment_band == treatment_band and r.diameter_zone == diameter_zone
    )


def _rows(family, index_value, treatment_band):
    return [
        r for r in ALL_ROWS
        if r.family == family and r.index_value == index_value
        and r.treatment_band == treatment_band
    ]


def _synthetic_pr(row: ChartRow):
    """A lightweight PowerRange stand-in carrying only what
    _check_form_against_range reads - mirrors the existing G3 unit-test
    pattern (test_phase4_parser.py's _g3_pr) so the 50+ truth-set cases run
    against the real matcher formula without database overhead."""
    return type("PR", (), dict(
        sph_min=-40.0, sph_max=40.0, cyl_min=-10.0, cyl_max=0.0,
        add_min=None, add_max=None, max_cyl_for_high_sph=None, sph_threshold=None,
        total_power_min=row.total_power_min, total_power_max=row.total_power_max,
        max_cyl_abs=row.max_cyl_abs,
    ))()


def _eligible(row: ChartRow, sph: float, cyl: float) -> bool:
    issues = _matcher._check_form_against_range(_synthetic_pr(row), (sph, cyl, 0, 0.0))
    return issues == []


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


# ---------------------------------------------------------------------------
# Fixture builder: an "already-confirmed" ZEISS commercial identity, standing
# in for one row of the proven 315. Mirrors exactly what
# confirm_catalog_commercial would have written earlier: LensModel,
# LensVariant, and one CURRENT VariantPricing PER coating (coating varies
# commercially; the chart's power range never does).
# ---------------------------------------------------------------------------
def _seed_existing_pricing(
    db, *, family, index_value, material, treatment_band, coatings,
    design_tier=None, market_scope=None, base_price="10000.00",
):
    co = db.query(models.Company).filter(models.Company.name == "ZEISS").first()
    if co is None:
        co = models.Company(name="ZEISS", is_active=True, is_deleted=False)
        db.add(co); db.commit(); db.refresh(co)
    # stand-in for the ALREADY-CONFIRMED price catalog that produced the real
    # 315 rows - source_catalog_id is NOT NULL on VariantPricing. Only one
    # CONFIRMED catalog is allowed per company (uq_one_confirmed_catalog_per_company).
    price_cat = db.query(models.Catalog).filter(
        models.Catalog.company_id == co.id,
        models.Catalog.status == models.CatalogStatus.CONFIRMED,
    ).first()
    if price_cat is None:
        price_cat = models.Catalog(
            company_id=co.id, filename="zeiss-price-list.pdf", file_path="/x",
            status=models.CatalogStatus.CONFIRMED,
        )
        db.add(price_cat); db.commit(); db.refresh(price_cat)
    # reuse an existing LensModel for this (company, name, category) - mirrors
    # confirm_catalog_commercial's own lookup-or-create; never duplicate it.
    model = db.query(models.LensModel).filter(
        models.LensModel.company_id == co.id, models.LensModel.name == family,
        models.LensModel.category == models.LensCategory.SINGLE_VISION,
    ).first()
    if model is None:
        model = models.LensModel(
            company_id=co.id, name=family, category=models.LensCategory.SINGLE_VISION,
        )
        db.add(model); db.commit(); db.refresh(model)
    variant = models.LensVariant(
        lens_model_id=model.id, material=material, index_value=index_value,
        design_type=models.DesignType.SPHERICAL, is_aspherical=False,
        design_tier=design_tier, treatment_band=treatment_band,
        availability=models.LensAvailability.RX, price=0.0, currency="EGP",
    )
    db.add(variant); db.commit(); db.refresh(variant)
    pricings = []
    for i, coating_code in enumerate(coatings):
        coating = models.Coating(code=coating_code, name=coating_code)
        db.add(coating); db.commit(); db.refresh(coating)
        vp = models.VariantPricing(
            variant_id=variant.id, coating_id=coating.id,
            availability=models.PricingAvailability.RX,
            power_eligibility=models.PowerEligibilityStatus.UNRESOLVED,
            price_pair=f"{float(base_price) + i * 100:.2f}",
            currency="EGP", source_catalog_id=price_cat.id,
            effective_from=datetime.utcnow(),
            effective_to=None, power_scope=None, market_scope=market_scope,
        )
        db.add(vp)
        pricings.append(vp)
    db.commit()
    for vp in pricings:
        db.refresh(vp)
    return co, model, variant, pricings


def _build_and_confirm(db, catalog_name="zeiss-svrx", only_confidence=None):
    """Run the full generic pipeline: evidence -> ExtractedLensModel ->
    save_extractions_to_db -> confirm every extraction whose evidence is
    "proven" (review_status stays pending -> confirm_extraction is simply
    never called for those, so they can never be attached - fail closed by
    construction, not by an extra check)."""
    co = db.query(models.Company).filter(models.Company.name == "ZEISS").first()
    assert co is not None, "seed existing pricing before building extractions"
    cat = models.Catalog(
        company_id=co.id, filename=catalog_name, file_path="/x",
        status=models.CatalogStatus.DRAFT,
    )
    db.add(cat); db.commit(); db.refresh(cat)
    p = PDFHybridParser(use_vision=False)
    p.extracted_models = build_extracted_models(only_confidence=only_confidence)
    p.save_extractions_to_db(cat.id, db)
    exts = _crud.get_extractions_by_catalog(db, cat.id)
    confirmed, held = [], []
    for e in exts:
        if e.status == "needs_review":
            held.append(e)
            continue
        _crud.confirm_extraction(db, e.id, "qa")
        confirmed.append(e)
    return cat, confirmed, held


# ============================================================
# Source-map coverage (sanity, not eligibility)
# ============================================================
def test_4h_source_map_covers_all_three_families():
    families = {r.family for r in ALL_ROWS}
    assert families == {"ClearMind", "ClearView RX", "SPH RX"}


def test_4h_source_map_covers_multiple_indexes_treatments_diameters():
    for fam in ("ClearMind", "ClearView RX", "SPH RX"):
        rows = [r for r in ALL_ROWS if r.family == fam]
        assert len({r.index_value for r in rows}) >= 2, fam
        assert len({r.treatment_band for r in rows}) >= 2, fam
        assert len({r.diameter_zone for r in rows}) >= 2, fam


def test_4h_review_rows_never_silently_proven():
    reviewed = [r for r in ALL_ROWS if r.confidence == "review"]
    assert reviewed, "expected at least one flagged row from the dense/anomalous blocks"
    assert all(r.review_reason for r in reviewed)


# ============================================================
# Extraction -> confirmation -> attach -> PowerRange, end to end
# ============================================================
def test_4h_extraction_to_powerrange_e2e_preserves_price_identity(db):
    co, model, variant, pricings = _seed_existing_pricing(
        db, family="ClearView RX", index_value=1.74, material="high_index_1.74",
        treatment_band="Clear",
        coatings=["DuraVision Plus Gold", "DuraVision Plus Platinum"],
    )
    before = [(vp.id, vp.price_pair, vp.effective_from, vp.effective_to) for vp in pricings]

    cat, confirmed, held = _build_and_confirm(db)
    target = next(
        e for e in confirmed
        if e.extracted_name == "ClearView RX" and e.extracted_index == 1.74
        and e.extracted_treatment_band == "Clear"
        and e.extracted_total_power_min == -20.0
    )
    result = _crud.attach_range_to_existing_pricing(db, target.id)
    assert "error" not in result, result
    assert len(result["created"]) == 2          # one PowerRange per coating

    db.expire_all()
    after = [(vp.id, vp.price_pair, vp.effective_from, vp.effective_to)
             for vp in db.query(models.VariantPricing).filter(
                 models.VariantPricing.id.in_([vp.id for vp in pricings])).all()]
    assert sorted(after) == sorted(before), "VariantPricing identity must be untouched"

    ranges = db.query(models.PowerRange).filter(
        models.PowerRange.pricing_id.in_([vp.id for vp in pricings])).all()
    assert len(ranges) == 2
    assert {r.total_power_min for r in ranges} == {-20.0}
    assert {r.total_power_max for r in ranges} == {16.0}
    assert {r.max_cyl_abs for r in ranges} == {6.0}


def test_4h_idempotent_reattach_no_duplicate_powerrange(db):
    _seed_existing_pricing(
        db, family="ClearView RX", index_value=1.74, material="high_index_1.74",
        treatment_band="Clear", coatings=["DuraVision Plus Gold"],
    )
    cat, confirmed, held = _build_and_confirm(db)
    target = next(
        e for e in confirmed
        if e.extracted_name == "ClearView RX" and e.extracted_index == 1.74
        and e.extracted_treatment_band == "Clear"
        and e.extracted_total_power_min == -20.0
    )
    r1 = _crud.attach_range_to_existing_pricing(db, target.id)
    r2 = _crud.attach_range_to_existing_pricing(db, target.id)
    assert len(r1["created"]) == 1 and len(r2["created"]) == 0
    assert r2["reused"] == r1["created"]
    total = db.query(models.PowerRange).count()
    assert total == 1


def test_4h_review_row_cannot_be_attached_fail_closed(db):
    # "AdaptiveSun POL" (the distinct 3rd band, never remapped by the Phase
    # 4K POL/AdaptiveSun merge - see _POL_ADAPTIVESUN_REAL_COMBOS) carries
    # this anomaly and stays literal, unaffected by that remap.
    _seed_existing_pricing(
        db, family="ClearMind", index_value=1.5, material="CR39",
        treatment_band="AdaptiveSun POL", coatings=["DuraVision Plus Gold"],
    )
    cat, confirmed, held = _build_and_confirm(db)
    assert held, "the ClearMind 1.5 AdaptiveSun POL anomaly row must stay needs_review"
    flagged = next(e for e in held if e.extracted_treatment_band == "AdaptiveSun POL"
                   and e.extracted_name == "ClearMind" and e.extracted_index == 1.5)
    result = _crud.attach_range_to_existing_pricing(db, flagged.id)
    assert "error" in result and "not review-approved" in result["error"]
    assert db.query(models.PowerRange).count() == 0


def test_4h_no_matching_identity_parks_never_fabricates(db):
    # Simulate the realistic case: company exists but this exact
    # model/treatment_band never got a confirmed price (no LensModel at all).
    co = models.Company(name="ZEISS", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat2 = models.Catalog(company_id=co.id, filename="x", file_path="/x",
                          status=models.CatalogStatus.DRAFT)
    db.add(cat2); db.commit(); db.refresh(cat2)
    p = PDFHybridParser(use_vision=False)
    p.extracted_models = build_extracted_models(only_confidence="proven")
    p.save_extractions_to_db(cat2.id, db)
    ext = next(
        e for e in _crud.get_extractions_by_catalog(db, cat2.id)
        if e.extracted_name == "ClearView RX" and e.status != "needs_review"
    )
    _crud.confirm_extraction(db, ext.id, "qa")
    result = _crud.attach_range_to_existing_pricing(db, ext.id)
    assert "error" in result
    assert "no existing ACTIVE LensModel" in result["error"]
    assert db.query(models.PowerRange).count() == 0


# ============================================================
# Multiple diameter zones OR together under one commercial identity
# ============================================================
def test_4h_multiple_diameter_zones_or_together_one_result(db):
    # 1.67 "Clear" ends up with THREE proven diameter-zone rows once attached:
    # the standalone ø80 "Clear" row (-6/+6 cyl6) plus the two "Clear/
    # BlueGuard" merged rows that expand to include "Clear" (ø70-75: total
    # [-10,8] cyl6, and ø65-55: total [-17,11] cyl6 - the one this test's
    # OR-behavior check below actually exercises).
    _seed_existing_pricing(
        db, family="ClearView RX", index_value=1.67, material="high_index_1.67",
        treatment_band="Clear", coatings=["DuraVision Plus Gold"],
    )
    cat, confirmed, held = _build_and_confirm(db)
    rows = [e for e in confirmed if e.extracted_name == "ClearView RX"
            and e.extracted_index == 1.67 and e.extracted_treatment_band == "Clear"]
    assert len(rows) == 3
    for e in rows:
        res = _crud.attach_range_to_existing_pricing(db, e.id)
        assert "error" not in res, res

    pricing = db.query(models.VariantPricing).join(models.LensVariant).filter(
        models.LensVariant.treatment_band == "Clear",
        models.LensVariant.index_value == 1.67,
    ).first()
    ranges = list(pricing.power_ranges)
    assert len(ranges) == 3      # all three diameter zones preserved, not flattened

    # a prescription covered by the SECOND zone (-17/+11, cyl6) but NOT the
    # first (-10/+8) must still be eligible (OR across diameter zones):
    # SPH=-11, CYL=-4 -> M1=-11, M2=-15. Zone1 (tp_min=-10) rejects (-15<-10);
    # zone2 (tp_min=-17) accepts (-15>=-17, high=-11<=11, cyl 4<=6).
    presc = models.Prescription(
        od_sph_original=-11.0, os_sph_original=-11.0, od_sph=-11.0, os_sph=-11.0,
        od_cyl_original=-4.0, os_cyl_original=-4.0, od_cyl=-4.0, os_cyl=-4.0,
        od_axis=90, os_axis=90, od_add=0.0, os_add=0.0,
    )
    db.add(presc); db.commit(); db.refresh(presc)
    ok, _ = _matcher.check_power_range(pricing.power_ranges[0], presc, "od")
    ok2, _ = _matcher.check_power_range(pricing.power_ranges[1], presc, "od")
    assert not (ok and ok2), "sanity: the two zones must not both trivially cover this Rx"
    assert any(_matcher.check_power_range(pr, presc, "od")[0] for pr in ranges)


# ============================================================
# Treatment separation: proving one treatment does not leak eligibility
# into an unresolved/different one
# ============================================================
def test_4h_treatment_band_separation_no_cross_leakage(db):
    # "Clear" and "PhotoFusion X" at 1.74 - both stay LITERAL (1.74 is not in
    # the Phase 4K POL/AdaptiveSun merge set), so this exercises ordinary
    # treatment_band separation, untouched by that remap.
    _seed_existing_pricing(
        db, family="ClearView RX", index_value=1.74, material="high_index_1.74",
        treatment_band="Clear", coatings=["DuraVision Plus Gold"],
    )
    _seed_existing_pricing(
        db, family="ClearView RX", index_value=1.74, material="high_index_1.74",
        treatment_band="PhotoFusion X", coatings=["DuraVision Plus Platinum"],
    )
    cat, confirmed, held = _build_and_confirm(db)
    for e in confirmed:
        if e.extracted_name == "ClearView RX" and e.extracted_index == 1.74:
            _crud.attach_range_to_existing_pricing(db, e.id)

    cb_pricing = db.query(models.VariantPricing).join(models.LensVariant).filter(
        models.LensVariant.treatment_band == "Clear",
        models.LensVariant.index_value == 1.74,
    ).first()
    pf_pricing = db.query(models.VariantPricing).join(models.LensVariant).filter(
        models.LensVariant.treatment_band == "PhotoFusion X",
        models.LensVariant.index_value == 1.74,
    ).first()
    assert cb_pricing.id != pf_pricing.id
    # each pricing carries exactly its OWN evidence rows - never merged /
    # never leaking the other treatment_band's diameter zones onto it.
    assert {(r.total_power_min, r.total_power_max) for r in cb_pricing.power_ranges} == {
        (-12.0, 9.0), (-15.0, 13.0), (-20.0, 16.0)}
    assert {(r.total_power_min, r.total_power_max) for r in pf_pricing.power_ranges} == {
        (-10.0, 9.0), (-14.0, 11.25)}

    # SPH=-11, CYL=-4 -> M1=-11, M2=-15: covered by Clear's widest -20/+16
    # zone, but outside PhotoFusion X's widest zone (-14/+11.25, M2=-15<-14)
    # - proves one treatment's eligibility never unlocks another's.
    presc = models.Prescription(
        od_sph_original=-11.0, os_sph_original=-11.0, od_sph=-11.0, os_sph=-11.0,
        od_cyl_original=-4.0, os_cyl_original=-4.0, od_cyl=-4.0, os_cyl=-4.0,
        od_axis=90, os_axis=90, od_add=0.0, os_add=0.0,
    )
    db.add(presc); db.commit(); db.refresh(presc)
    cb_ok = any(_matcher.check_power_range(pr, presc, "od")[0] for pr in cb_pricing.power_ranges)
    pf_ok = any(_matcher.check_power_range(pr, presc, "od")[0] for pr in pf_pricing.power_ranges)
    assert cb_ok is True
    assert pf_ok is False, "PhotoFusion X must not inherit Clear's eligibility"


# ============================================================
# Family-level sharing across design tiers (ClearMind: Individual 3 / Superb)
# ============================================================
def test_4h_family_level_range_shared_across_clearmind_tiers(db):
    co = models.Company(name="ZEISS", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    price_cat = models.Catalog(company_id=co.id, filename="zeiss-price-list.pdf",
                               file_path="/x", status=models.CatalogStatus.CONFIRMED)
    db.add(price_cat); db.commit(); db.refresh(price_cat)
    model = models.LensModel(company_id=co.id, name="ClearMind",
                             category=models.LensCategory.SINGLE_VISION)
    db.add(model); db.commit(); db.refresh(model)
    pricing_ids = []
    for tier in ("Individual 3", "Superb"):
        variant = models.LensVariant(
            lens_model_id=model.id, material="high_index_1.74", index_value=1.74,
            design_type=models.DesignType.SPHERICAL, is_aspherical=False,
            design_tier=tier, treatment_band="Clear",
            availability=models.LensAvailability.RX, price=0.0, currency="EGP",
        )
        db.add(variant); db.commit(); db.refresh(variant)
        coating = models.Coating(code=f"Gold-{tier}", name=f"Gold-{tier}")
        db.add(coating); db.commit(); db.refresh(coating)
        vp = models.VariantPricing(
            variant_id=variant.id, coating_id=coating.id,
            availability=models.PricingAvailability.RX,
            power_eligibility=models.PowerEligibilityStatus.UNRESOLVED,
            price_pair="9999.00", currency="EGP", source_catalog_id=price_cat.id,
            effective_from=datetime.utcnow(), effective_to=None,
            power_scope=None, market_scope=None,
        )
        db.add(vp); db.commit(); db.refresh(vp)
        pricing_ids.append(vp.id)

    cat, confirmed, held = _build_and_confirm(db)
    ext = next(
        e for e in confirmed
        if e.extracted_name == "ClearMind" and e.extracted_index == 1.74
        and e.extracted_treatment_band == "Clear"
        and e.extracted_total_power_min == -20.0
    )
    result = _crud.attach_range_to_existing_pricing(db, ext.id)
    assert "error" not in result, result
    # the SAME family-level (design_tier=None) evidence row attaches to BOTH
    # tiers' pricing - proven shared, never invented as tier-specific.
    assert len(result["created"]) == 2
    for pid in pricing_ids:
        vp = db.query(models.VariantPricing).get(pid)
        assert len(vp.power_ranges) == 1
        assert vp.power_ranges[0].total_power_min == -20.0


# ============================================================
# Transposition invariance through the real persisted objects
# ============================================================
def test_4h_transposition_invariant_through_persisted_range(db):
    _seed_existing_pricing(
        db, family="ClearView RX", index_value=1.74, material="high_index_1.74",
        treatment_band="Clear", coatings=["DuraVision Plus Gold"],
    )
    cat, confirmed, held = _build_and_confirm(db)
    ext = next(
        e for e in confirmed
        if e.extracted_name == "ClearView RX" and e.extracted_index == 1.74
        and e.extracted_treatment_band == "Clear"
        and e.extracted_total_power_min == -20.0
    )
    res = _crud.attach_range_to_existing_pricing(db, ext.id)
    assert "error" not in res, res
    pr = db.query(models.PowerRange).filter(models.PowerRange.id == res["created"][0]).first()

    # range is total_power [-20, 16], max_cyl_abs 6 (ClearView RX 1.74
    # Clear/BlueGuard, ø60-55). SPH=-14, CYL=-6 (minus notation) -> M1=-14,
    # M2=-20 (exact tp_min boundary), |CYL|=6 (exact cap). The SAME Rx entered
    # in plus-cyl notation (SPH=-20, CYL=+6, axis=180) must normalize, via the
    # real prescription-creation transposition path, to the identical stored
    # minus form - and therefore reach the identical G3 verdict.
    minus_entry = _TE.transpose(-14.0, -6.0, 90)
    plus_entry = _TE.transpose(-20.0, 6.0, 180)
    assert minus_entry == plus_entry == (-14.0, -6.0, 90)
    ok_minus = _matcher._check_form_against_range(pr, (*minus_entry, 0.0))
    ok_plus = _matcher._check_form_against_range(pr, (*plus_entry, 0.0))
    assert ok_minus == ok_plus == []


# ============================================================
# TRUTH SET (>= 50 cases) - every case below is driven by REAL chart numbers
# in ALL_ROWS (a "proven" row unless noted), run directly against the exact
# G3 matcher formula (_check_form_against_range). Grouped by the required
# category; each entry is
#   (case_id, family, index, treatment_band, diameter_zone, sph, cyl, expected)
# expected True/False = eligible/ineligible; None = must stay UNKNOWN
# (source evidence is a flagged "review" row, never silently resolved).
# ============================================================

_CV = "ClearView RX"
_CM = "ClearMind"
_SR = "SPH RX"

TRUTH_SET = [
    # -- 1/2/3: obvious inside / obvious negative outside / obvious positive outside
    ("T01_obvious_inside", _CV, 1.74, "Clear/BlueGuard", "60 - 55", 0.0, 0.0, True),
    ("T02_obvious_neg_outside", _CV, 1.74, "Clear/BlueGuard", "60 - 55", -30.0, 0.0, False),
    ("T03_obvious_pos_outside", _CV, 1.74, "Clear/BlueGuard", "60 - 55", 30.0, 0.0, False),
    ("T04_obvious_inside_cm", _CM, 1.53, "Clear/BlueGuard", "65/70 - 55/60", 0.0, -2.0, True),
    ("T05_obvious_neg_outside_sr", _SR, 1.53, "Clear/BlueGuard", "65 - 55", -20.0, 0.0, False),
    # -- 4/5: exact Total Power min / max
    ("T06_exact_tp_min", _CV, 1.74, "Clear/BlueGuard", "60 - 55", -20.0, 0.0, True),
    ("T07_exact_tp_max", _CV, 1.74, "Clear/BlueGuard", "60 - 55", 16.0, 0.0, True),
    ("T08_exact_tp_min_cm", _CM, 1.74, "Clear/BlueGuard", "55 - 60", -20.0, 0.0, True),
    ("T09_exact_tp_min_sr", _SR, 1.67, "Clear/BlueGuard", "70 - 50", -12.0, 0.0, True),
    # -- 6/7: 0.25D outside min / max
    ("T10_quarter_outside_min", _CV, 1.74, "Clear/BlueGuard", "60 - 55", -20.25, 0.0, False),
    ("T11_quarter_outside_max", _CV, 1.74, "Clear/BlueGuard", "60 - 55", 16.25, 0.0, False),
    ("T12_quarter_outside_min_cm", _CM, 1.74, "Clear/BlueGuard", "55 - 60", -20.25, 0.0, False),
    ("T13_quarter_outside_max_sr", _SR, 1.67, "Clear/BlueGuard", "70 - 50", 8.25, 0.0, False),
    # -- 8/9: exact Max.Cyl / 0.25D beyond Max.Cyl
    ("T14_exact_max_cyl", _CV, 1.74, "Clear/BlueGuard", "60 - 55", 0.0, -6.0, True),
    ("T15_quarter_beyond_max_cyl", _CV, 1.74, "Clear/BlueGuard", "60 - 55", 0.0, -6.25, False),
    ("T16_exact_max_cyl_cm53", _CM, 1.53, "Clear/BlueGuard", "65/70 - 55/60", 0.0, -4.0, True),
    ("T17_quarter_beyond_max_cyl_cm53", _CM, 1.53, "Clear/BlueGuard", "65/70 - 55/60", 0.0, -4.25, False),
    # -- 10/11: M1 inside / M2 outside; M2 exact boundary
    ("T18_m1_in_m2_out", _CV, 1.74, "Clear/BlueGuard", "60 - 55", -15.0, -6.0, False),  # M1=-15 in, M2=-21 out
    ("T19_m2_exact_boundary", _CV, 1.74, "Clear/BlueGuard", "60 - 55", -14.0, -6.0, True),  # M1=-14, M2=-20 exact
    ("T20_m1_in_m2_out_167", _CV, 1.67, "Clear/BlueGuard", "65 - 55", -12.0, -6.0, False),  # M1=-12 in [-17,11], M2=-18 out
    ("T21_m2_exact_boundary_167", _CV, 1.67, "Clear/BlueGuard", "65 - 55", -11.0, -6.0, True),  # M1=-11, M2=-17 exact
    # -- 12: mixed astigmatism (moderate, well inside)
    ("T22_mixed_astig_inside", _CV, 1.74, "Clear/BlueGuard", "60 - 55", -5.0, -3.0, True),
    ("T23_mixed_astig_inside_cm", _CM, 1.5, "Clear/BlueGuard", "75/80 - 50/55", -2.0, -2.0, True),
    # -- 13: high plus sphere + minus cyl
    ("T24_high_plus_sph_minus_cyl", _CV, 1.74, "Clear/BlueGuard", "60 - 55", 15.0, -5.0, True),   # M1=15,M2=10
    ("T25_high_plus_sph_minus_cyl_fail", _CV, 1.74, "Clear/BlueGuard", "60 - 55", 17.0, -1.0, False),  # M1=17 > 16
    # -- 14: high minus sphere + minus cyl
    ("T26_high_minus_sph_minus_cyl_fail", _CV, 1.74, "Clear/BlueGuard", "60 - 55", -19.0, -2.0, False),  # M2=-21
    ("T27_high_minus_sph_minus_cyl_pass", _CV, 1.74, "Clear/BlueGuard", "60 - 55", -19.0, -1.0, True),   # M2=-20 exact
    # -- 15: plus-cylinder transposed equivalent (same Rx, both notations agree)
    ("T28_transposed_minus_entry", _CV, 1.74, "Clear/BlueGuard", "60 - 55", *_TE.transpose(-14.0, -6.0, 90)[:2], True),
    ("T29_transposed_plus_entry", _CV, 1.74, "Clear/BlueGuard", "60 - 55", *_TE.transpose(-20.0, 6.0, 180)[:2], True),
    # -- 16: asymmetric total-power min/max (|min| != |max|)
    ("T30_asymmetric_exact_min", _CV, 1.67, "Clear/BlueGuard", "65 - 55", -17.0, 0.0, True),
    ("T31_asymmetric_exact_max", _CV, 1.67, "Clear/BlueGuard", "65 - 55", 11.0, 0.0, True),
    ("T32_asymmetric_exact_min_sr", _SR, 1.67, "PhotoFusion X", "75", -12.0, 0.0, True),
    ("T33_asymmetric_exact_max_sr", _SR, 1.67, "PhotoFusion X", "75", 8.0, 0.0, True),
    # -- 17: one diameter zone fails, another passes (checked individually here;
    #    the OR-across-zones behavior itself is proven at the DB layer above)
    ("T34_zone1_fails_70_75", _CV, 1.67, "Clear/BlueGuard", "70 - 75", -11.0, -4.0, False),
    ("T35_zone2_passes_65_55", _CV, 1.67, "Clear/BlueGuard", "65 - 55", -11.0, -4.0, True),
    # -- 18: treatment A passes / B fails at the identical Rx
    ("T36_treatment_cb_passes", _CV, 1.67, "Clear/BlueGuard", "65 - 55", -11.0, -4.0, True),
    ("T37_treatment_pol_fails_75_55", _CV, 1.67, "POL", "75 - 55", -11.0, -4.0, False),
    ("T38_treatment_pol_fails_80", _CV, 1.67, "POL", "80", -11.0, -4.0, False),
    # -- more exact/near-boundary spread across ClearMind and SPH RX --
    ("T39_cm_exact_min_174", _CM, 1.74, "Clear/BlueGuard", "70 - 75", -10.0, 0.0, True),
    ("T40_cm_exact_max_174", _CM, 1.74, "Clear/BlueGuard", "70 - 75", 7.0, 0.0, True),
    ("T41_cm_quarter_outside_max_174", _CM, 1.74, "Clear/BlueGuard", "70 - 75", 7.25, 0.0, False),
    ("T42_cm_photofusion_exact_max", _CM, 1.74, "PhotoFusion X", "65/70 - 55/60", 9.0, 0.0, True),
    ("T43_cm_photofusion_quarter_outside", _CM, 1.74, "PhotoFusion X", "65/70 - 55/60", 9.25, 0.0, False),
    ("T44_sr_trivex_exact_min", _SR, 1.53, "Clear/BlueGuard", "65 - 55", -7.0, 0.0, True),
    ("T45_sr_trivex_exact_max", _SR, 1.53, "Clear/BlueGuard", "65 - 55", 7.0, 0.0, True),
    ("T46_sr_trivex_quarter_outside_min", _SR, 1.53, "Clear/BlueGuard", "65 - 55", -7.25, 0.0, False),
    ("T47_sr_trivex_cyl_exact_cap", _SR, 1.53, "Clear/BlueGuard", "65 - 55", 0.0, -4.0, True),
    ("T48_sr_trivex_cyl_quarter_beyond", _SR, 1.53, "Clear/BlueGuard", "65 - 55", 0.0, -4.25, False),
    ("T49_cm_trivex_exact_min", _CM, 1.53, "Clear/BlueGuard", "75/80", -3.0, 0.0, True),
    ("T50_cm_trivex_exact_max", _CM, 1.53, "Clear/BlueGuard", "75/80", 7.0, 0.0, True),
    ("T51_cm_trivex_quarter_outside_max", _CM, 1.53, "Clear/BlueGuard", "75/80", 7.25, 0.0, False),
    ("T52_cv_adaptivesun_exact_min", _CV, 1.67, "AdaptiveSun", "70 - 75", -10.0, 0.0, True),
    ("T53_cv_adaptivesun_exact_max", _CV, 1.67, "AdaptiveSun", "70 - 75", 8.0, 0.0, True),
    ("T54_cv_adaptivesun_cyl_cap_exact", _CV, 1.67, "AdaptiveSun", "70 - 75", 0.0, -4.0, True),
    ("T55_cv_adaptivesun_cyl_cap_beyond", _CV, 1.67, "AdaptiveSun", "70 - 75", 0.0, -4.25, False),
]


@pytest.mark.parametrize("case_id,family,index,band,diam,sph,cyl,expected", TRUTH_SET, ids=[c[0] for c in TRUTH_SET])
def test_4h_truth_set(case_id, family, index, band, diam, sph, cyl, expected):
    row = _row(family, index, band, diam)
    assert row.confidence == "proven", f"{case_id} must be driven by a proven row"
    assert _eligible(row, sph, cyl) is expected, (
        f"{case_id}: {family} {index} {band} @{diam} sph={sph} cyl={cyl} "
        f"tp=[{row.total_power_min},{row.total_power_max}] maxcyl={row.max_cyl_abs}"
    )


def test_4h_truth_set_has_at_least_50_cases():
    assert len(TRUTH_SET) >= 50


# -- 19: unresolved treatment stays UNKNOWN (never silently resolved) -------
def test_4h_unresolved_treatment_stays_unknown_not_eligible_or_ineligible():
    reviewed = _row(_CM, 1.5, "POL", "80/85")
    assert reviewed.confidence == "review"
    assert reviewed.review_reason is not None
    # the ONLY correct disposition for a review row is "stays out of the
    # confirmed/attached commercial graph" - proven end-to-end in
    # test_4h_review_row_cannot_be_attached_fail_closed above.


# -- 20: footnote-driven exclusion (BlueGuard not available at this cell) --
def test_4h_footnote_exclusion_blueguard_absent_at_167_diameter_80():
    # "*1.67, 1.6: ø80 not available in BlueGuard design" - only "Clear" (not
    # "Clear/BlueGuard" and not a standalone "BlueGuard") may exist at this cell.
    cell_rows = [r for r in ALL_ROWS if r.family == _CV and r.index_value == 1.67
                and r.diameter_zone == "80"]
    bands = {r.treatment_band for r in cell_rows}
    assert "Clear" in bands
    assert "BlueGuard" not in bands and "Clear/BlueGuard" not in bands


def test_4h_footnote_exclusion_blueguard_absent_at_sphrx_15_diameter_80():
    # "*1.5: Not available in ø80 BlueGuard design" (SPH RX footnote)
    cell_rows = [r for r in ALL_ROWS if r.family == _SR and r.index_value == 1.5
                and r.diameter_zone == "80"]
    bands = {r.treatment_band for r in cell_rows}
    assert "BlueGuard" not in bands and "Clear/BlueGuard" not in bands
