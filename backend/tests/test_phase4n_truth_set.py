"""
Phase 4N: fresh truth set derived from the NEW canonical ZEISS SV-RX
graphical evidence (backend/app/zeiss_svrx_graphical_evidence.ALL_ROWS),
not from the old (89-row-short) table it replaced.

Exercises app.lens_matcher.LensMatcher.check_power_range directly (the same
function product_search relies on for per-eye eligibility) against
PowerRange objects built from real, proven catalog values, plus a handful
of DB-level cases for no-SKU / partial-mapping / applicability-key /
unresolved-anomaly behavior that need the full attach path.

Acceptance: false eligible = 0, false ineligible = 0 on every row whose
confidence is "proven" (the two known "review" anomalies are deliberately
tested as fail-closed, not as eligible/ineligible facts).
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
from app import models, database, crud  # noqa: E402
from app.lens_matcher import lens_matcher as MATCHER, TranspositionEngine  # noqa: E402
from app.zeiss_svrx_graphical_evidence import ALL_ROWS, build_extracted_models, _INDEX_MATERIAL  # noqa: E402
from app.pdf_hybrid_parser import PDFHybridParser  # noqa: E402

PROVEN_ROWS = [r for r in ALL_ROWS if r.confidence == "proven"]


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


def _presc(sph, cyl, axis=90):
    return models.Prescription(
        customer_name="t",
        od_sph_original=sph, od_cyl_original=cyl, od_axis_original=axis,
        od_sph=sph, od_cyl=cyl, od_axis=axis,
        os_sph_original=sph, os_cyl_original=cyl, os_axis_original=axis,
        os_sph=sph, os_cyl=cyl, os_axis=axis, pd=63,
    )


def _range_from_row(row):
    # cyl_min must comfortably clear this row's own max_cyl_abs (the G3
    # clause is what actually enforces the cyl cap via max_cyl_abs; this
    # plain cyl_min/cyl_max pair only needs to not itself become the
    # binding constraint in these tests).
    return models.PowerRange(
        lens_model_id=1, sph_min=-25.0, sph_max=25.0,
        cyl_min=-min(row.max_cyl_abs + 2.0, 10.0), cyl_max=0.0,
        total_power_min=row.total_power_min, total_power_max=row.total_power_max,
        max_cyl_abs=row.max_cyl_abs,
    )


# -- 1-2xN: exact boundary eligible + 0.25 outside ineligible, for every
# proven row in the new canonical set (spans all 3 families, every
# available index, every treatment band, many diameters) --------------------
@pytest.mark.parametrize("row", PROVEN_ROWS, ids=[
    f"{r.family}-{r.index_value}-{r.treatment_band}-{r.diameter_zone}-{i}"
    for i, r in enumerate(PROVEN_ROWS)
])
def test_4n_exact_boundary_eligible(row):
    pr = _range_from_row(row)
    # A plano-cyl Rx sitting exactly at sph_min or sph_max must be eligible.
    for sph in (row.total_power_min, row.total_power_max):
        ok, _ = MATCHER.check_power_range(pr, _presc(sph, 0.0), "od")
        assert ok, f"{row.family} {row.index_value} {row.treatment_band} {row.diameter_zone}: exact boundary {sph} must be eligible"


@pytest.mark.parametrize("row", PROVEN_ROWS, ids=[
    f"{r.family}-{r.index_value}-{r.treatment_band}-{r.diameter_zone}-{i}"
    for i, r in enumerate(PROVEN_ROWS)
])
def test_4n_quarter_diopter_outside_ineligible(row):
    pr = _range_from_row(row)
    below = row.total_power_min - 0.25
    above = row.total_power_max + 0.25
    ok_below, _ = MATCHER.check_power_range(pr, _presc(below, 0.0), "od")
    ok_above, _ = MATCHER.check_power_range(pr, _presc(above, 0.0), "od")
    assert not ok_below, f"{row.family} {row.index_value} {row.treatment_band}: 0.25 below min must be ineligible"
    assert not ok_above, f"{row.family} {row.index_value} {row.treatment_band}: 0.25 above max must be ineligible"


# -- cyl cap exact + 0.25 beyond, for every proven row with a real cyl cap --
CYL_ROWS = [r for r in PROVEN_ROWS if r.max_cyl_abs > 0]


@pytest.mark.parametrize("row", CYL_ROWS, ids=[
    f"{r.family}-{r.index_value}-{r.treatment_band}-{r.diameter_zone}-{i}"
    for i, r in enumerate(CYL_ROWS)
])
def test_4n_cyl_cap_exact_eligible_quarter_beyond_ineligible(row):
    pr = _range_from_row(row)
    # Anchor M1 at the row's own total_power_max (a boundary already proven
    # eligible by test_4n_exact_boundary_eligible) so M2 = M1 - cyl always
    # lands inside [total_power_min, total_power_max] for every row in this
    # catalog (max_cyl_abs never exceeds a row's own total-power span -
    # verified directly against ALL_ROWS), isolating the cyl-cap check from
    # any sph-boundary interaction.
    sph = row.total_power_max
    at_cap = models.Prescription(
        customer_name="t",
        od_sph_original=sph, od_cyl_original=-row.max_cyl_abs, od_axis_original=90,
        od_sph=sph, od_cyl=-row.max_cyl_abs, od_axis=90,
        os_sph_original=sph, os_cyl_original=-row.max_cyl_abs, os_axis_original=90,
        os_sph=sph, os_cyl=-row.max_cyl_abs, os_axis=90, pd=63,
    )
    beyond_cap = models.Prescription(
        customer_name="t",
        od_sph_original=sph, od_cyl_original=-(row.max_cyl_abs + 0.25), od_axis_original=90,
        od_sph=sph, od_cyl=-(row.max_cyl_abs + 0.25), od_axis=90,
        os_sph_original=sph, os_cyl_original=-(row.max_cyl_abs + 0.25), os_axis_original=90,
        os_sph=sph, os_cyl=-(row.max_cyl_abs + 0.25), os_axis=90, pd=63,
    )
    ok_cap, _ = MATCHER.check_power_range(pr, at_cap, "od")
    ok_beyond, _ = MATCHER.check_power_range(pr, beyond_cap, "od")
    assert ok_cap, f"{row.family} {row.index_value} {row.treatment_band}: exact cyl cap must be eligible"
    assert not ok_beyond, f"{row.family} {row.index_value} {row.treatment_band}: 0.25 beyond cyl cap must be ineligible"


# -- M1/M2 disagreement: mixed astigmatism where one meridian is inside the
# range and the other is not must be ineligible (both must pass) -----------
def test_4n_m1_m2_disagreement_mixed_astigmatism_ineligible():
    row = next(r for r in PROVEN_ROWS if r.family == "SPH RX" and r.treatment_band == "Clear/BlueGuard"
               and r.diameter_zone == "70 - 50")  # -12.00 / +8.00, cyl 6.00
    pr = _range_from_row(row)
    # M1 = sph = +8.00 (at the boundary), M2 = sph+cyl = 8 - 6.5 = +1.5 - fine
    # for M2, but push M1 just past the max: sph=+8.25, cyl=-6.0 -> M2=+2.25.
    p = _presc(8.25, -6.0)
    ok, reason = MATCHER.check_power_range(pr, p, "od")
    assert not ok, "one meridian (+8.25) exceeding total_power_max must fail the whole eye, even though the other meridian is comfortably inside"


# -- transposition equivalence: a doctor's raw plus-cyl prescription, once
# normalized by TranspositionEngine.transpose (as happens before storage),
# must produce the exact same stored minus-cyl values - and therefore the
# same eligibility result - as the doctor writing it directly in minus-cyl
# form. This is the real invariant this catalog relies on: PowerRange rows
# are always evaluated in the stored minus form (see _range_convention). ---
def test_4n_transposition_invariant_same_physical_rx():
    row = next(r for r in PROVEN_ROWS if r.family == "ClearMind" and r.treatment_band == "PhotoFusion X"
               and r.diameter_zone == "70 - 75")  # -10.00 / +7.00 cyl 6.00 (1.74)
    pr = _range_from_row(row)
    # Doctor writes the SAME physical Rx in minus-cyl form directly...
    direct_sph, direct_cyl, direct_axis = -4.00, -6.00, 90
    # ...and, equivalently, in plus-cyl form - transposition must normalize
    # it back to the identical stored minus-cyl values.
    raw_plus_sph, raw_plus_cyl, raw_plus_axis = -10.00, 6.00, 0
    normalized_sph, normalized_cyl, normalized_axis = TranspositionEngine.transpose(
        raw_plus_sph, raw_plus_cyl, raw_plus_axis)
    assert (normalized_sph, normalized_cyl, normalized_axis) == (direct_sph, direct_cyl, direct_axis)
    ok_direct, _ = MATCHER.check_power_range(pr, _presc(direct_sph, direct_cyl, direct_axis), "od")
    ok_normalized, _ = MATCHER.check_power_range(
        pr, _presc(normalized_sph, normalized_cyl, normalized_axis), "od")
    assert ok_direct == ok_normalized, "transposed-equivalent prescriptions must agree on eligibility"


# -- multiple-diameter OR: two PowerRanges under one offer, Rx fails the
# narrower zone but passes the wider one -> overall proven-eligible --------
def test_4n_multiple_diameter_or_together_one_result():
    wide = next(r for r in PROVEN_ROWS if r.family == "ClearMind" and r.treatment_band == "Clear/BlueGuard"
                and r.diameter_zone == "55 - 60")  # -20.00/+16.00 cyl 6.00 (1.74)
    narrow = next(r for r in PROVEN_ROWS if r.family == "ClearMind" and r.treatment_band == "Clear/BlueGuard"
                  and r.diameter_zone == "70 - 75")  # -10.00/+7.00 cyl 6.00 (1.74)
    p = _presc(-18.00, 0.0)  # inside the wide zone, outside the narrow one
    ok_wide, _ = MATCHER.check_power_range(_range_from_row(wide), p, "od")
    ok_narrow, _ = MATCHER.check_power_range(_range_from_row(narrow), p, "od")
    assert ok_wide and not ok_narrow, "OR semantics: eligible via the wide zone even though ineligible via the narrow one"


# -- POL vs AdaptiveSun distinct applicability under one merged real SKU ---
def _seed_zeiss_offer(db, *, family, index_value, treatment_band, tier=None):
    co = models.Company(name="ZEISS", country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename="x.pdf", file_path="/x",
                         status=models.CatalogStatus.CONFIRMED)
    db.add(cat); db.commit(); db.refresh(cat)
    model = models.LensModel(company_id=co.id, name=family, category=models.LensCategory.SINGLE_VISION)
    db.add(model); db.commit(); db.refresh(model)
    variant = models.LensVariant(
        lens_model_id=model.id, material=_INDEX_MATERIAL[index_value],
        index_value=index_value, design_tier=tier,
        design_type=models.DesignType.SPHERICAL, is_aspherical=False,
        treatment_band=treatment_band, availability=models.LensAvailability.RX,
        price=0.0, currency="EGP")
    db.add(variant); db.commit(); db.refresh(variant)
    coating = models.Coating(code="DuraVision Plus Gold", name="DuraVision Plus Gold")
    db.add(coating); db.commit(); db.refresh(coating)
    vp = models.VariantPricing(
        variant_id=variant.id, coating_id=coating.id, availability=models.PricingAvailability.RX,
        power_eligibility=models.PowerEligibilityStatus.UNRESOLVED, price_pair=Decimal("20000.00"),
        currency="EGP", source_catalog_id=cat.id, effective_from=datetime.utcnow(),
        effective_to=None)
    db.add(vp); db.commit(); db.refresh(vp)
    return co, cat, model, variant, vp


def _attach_proven_row_by_key(db, cat_id, family, index_value, treatment_band, total_power_min, total_power_max):
    p = PDFHybridParser(use_vision=False)
    p.extracted_models = build_extracted_models(only_confidence="proven")
    p.save_extractions_to_db(cat_id, db)
    exts = crud.get_extractions_by_catalog(db, cat_id)
    target = next(
        e for e in exts if e.extracted_name == family and e.extracted_index == index_value
        and e.extracted_total_power_min == total_power_min
        and e.extracted_total_power_max == total_power_max
        and (e.extracted_treatment_band == treatment_band
             or e.extracted_applicability_key == treatment_band)
    )
    crud.confirm_extraction(db, target.id, "qa")
    return crud.attach_range_to_existing_pricing(db, target.id)


def test_4n_pol_and_adaptivesun_stay_distinct_under_merged_offer(db):
    # ClearMind 1.67's "Polarized / AdaptiveSun" is a real merged SKU; POL
    # and AdaptiveSun keep their own, different ranges under it.
    co, cat, model, variant, vp = _seed_zeiss_offer(
        db, family="ClearMind", index_value=1.67, treatment_band="Polarized / AdaptiveSun")
    r1 = _attach_proven_row_by_key(db, cat.id, "ClearMind", 1.67, "POL", -12.0, 11.0)
    assert "created" in r1 and len(r1["created"]) == 1
    ranges = db.query(models.PowerRange).filter(models.PowerRange.pricing_id == vp.id).all()
    assert len(ranges) == 1
    assert ranges[0].applicability_key == "POL"
    assert (ranges[0].total_power_min, ranges[0].total_power_max) == (-12.0, 11.0)


def test_4n_adaptivesun_pol_maps_to_distinct_real_sku_not_merged_offer(db):
    # ClearMind 1.6's "AdaptiveSun POL" evidence (clean, proven - NOT the
    # 1.5 anomaly) must map to "AdaptiveSun Polarized", never to "Polarized
    # / AdaptiveSun", and must carry no applicability_key (it is its own,
    # fully distinct commercial identity, not a shared-price subtype).
    co, cat, model, variant, vp = _seed_zeiss_offer(
        db, family="ClearMind", index_value=1.6, treatment_band="AdaptiveSun Polarized")
    r = _attach_proven_row_by_key(db, cat.id, "ClearMind", 1.6, "AdaptiveSun Polarized", -4.0, 4.0)
    assert "created" in r and len(r["created"]) == 1
    ranges = db.query(models.PowerRange).filter(models.PowerRange.pricing_id == vp.id).all()
    assert len(ranges) == 1
    assert ranges[0].applicability_key is None
    assert (ranges[0].total_power_min, ranges[0].total_power_max) == (-4.0, 4.0)


def test_4n_no_sku_sph_rx_167_stays_unattached(db):
    # SPH RX has no real commercial pricing at 1.67 at all (confirmed via
    # the real 315-row price grid: blank cells for SPH RX at 1.67/1.74) -
    # graphical evidence there must never be force-attached to something
    # else, and must never fabricate a SKU.
    co = models.Company(name="ZEISS", country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename="x.pdf", file_path="/x",
                         status=models.CatalogStatus.CONFIRMED)
    db.add(cat); db.commit(); db.refresh(cat)
    p = PDFHybridParser(use_vision=False)
    p.extracted_models = build_extracted_models(only_confidence="proven")
    p.save_extractions_to_db(cat.id, db)
    exts = crud.get_extractions_by_catalog(db, cat.id)
    target = next(e for e in exts if e.extracted_name == "SPH RX" and e.extracted_index == 1.67
                  and e.extracted_treatment_band == "Clear")
    crud.confirm_extraction(db, target.id, "qa")
    result = crud.attach_range_to_existing_pricing(db, target.id)
    assert "error" in result
    assert db.query(models.PowerRange).count() == 0


def test_4n_partial_mapping_sph_rx_153_clear_attaches_blueguard_does_not(db):
    # SPH RX 1.53 commercially sells only as "Clear" (no separate
    # "BlueGuard" SKU) - the chart's Clear/BlueGuard swatch there expands to
    # both labels, but only the real one may attach.
    co, cat, model, variant, vp = _seed_zeiss_offer(
        db, family="SPH RX", index_value=1.53, treatment_band="Clear")
    r_clear = _attach_proven_row_by_key(db, cat.id, "SPH RX", 1.53, "Clear", -3.0, 7.0)
    assert "created" in r_clear and len(r_clear["created"]) == 1
    exts = crud.get_extractions_by_catalog(db, cat.id)
    bg = next(e for e in exts if e.extracted_name == "SPH RX" and e.extracted_index == 1.53
              and e.extracted_treatment_band == "BlueGuard"
              and e.extracted_total_power_min == -3.0 and e.extracted_total_power_max == 7.0)
    r_bg = crud.attach_range_to_existing_pricing(db, bg.id)
    assert "error" in r_bg, "no real BlueGuard SKU exists for SPH RX 1.53 - must stay unattached"


def test_4n_unresolved_anomaly_never_becomes_eligible(db):
    # ClearMind 1.5's POL anomaly normalizes to the real merged offer
    # "Polarized / AdaptiveSun" (same precedent as every other POL row at a
    # combo in _POL_ADAPTIVESUN_REAL_COMBOS) - but its "review" confidence
    # must still fail-close the attachment regardless of that normalization.
    co, cat, model, variant, vp = _seed_zeiss_offer(
        db, family="ClearMind", index_value=1.5, treatment_band="Polarized / AdaptiveSun")
    p = PDFHybridParser(use_vision=False)
    p.extracted_models = build_extracted_models()  # include review rows too
    p.save_extractions_to_db(cat.id, db)
    exts = crud.get_extractions_by_catalog(db, cat.id)
    anomaly = next(e for e in exts if e.extracted_name == "ClearMind" and e.extracted_index == 1.5
                   and e.extracted_applicability_key == "POL" and e.status == "needs_review")
    result = crud.attach_range_to_existing_pricing(db, anomaly.id)
    assert "error" in result and "not review-approved" in result["error"]
    assert db.query(models.PowerRange).count() == 0
