"""HOYA "Mineral" / "Mineral Summit Progressive" split (owner-confirmed,
2026-09-20) - see app/hoya_mineral_summit_evidence.py's own module docstring
for the full citation (Hoya_Price_List_2025_Updated.pdf p.28, "Mineral
Lenses (RX)": 4 plain rows = Single Vision, 6 "Summit Progressive" rows =
genuine Progressive, all material=GLASS/RX/Out Of Egypt, all price/
PowerRange data proven unchanged by the prior read-only audit).

Deliberately synthetic - replicates the EXACT pre-split live-DB shape
(one mixed "Mineral" LensModel, three shared variants at indexes 1.52,
1.52-Photo, 1.81) directly via the ORM, mirroring
test_special_lenses_subtypes_evidence.py's own pattern. The live db result
is verified separately.
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
from app import hoya_mineral_summit_evidence as hms  # noqa: E402
from app import progressive_add_evidence  # noqa: E402

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


def _mk_variant(db, model, index_value, color_variant=None):
    v = models.LensVariant(lens_model_id=model.id, material=models.MaterialType.GLASS,
                           index_value=index_value, design_type=models.DesignType.SPHERICAL,
                           is_aspherical=False, color_variant=color_variant, price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    return v


def _mk_pricing(db, variant, catalog, coating, price, sph_min, sph_max, max_cyl_abs):
    vp = models.VariantPricing(variant_id=variant.id, coating_id=coating.id,
                               availability=models.PricingAvailability.RX, price_pair=price,
                               currency="EGP", source_catalog_id=catalog.id, market_scope="Out Of Egypt",
                               power_eligibility=models.PowerEligibilityStatus.UNRESTRICTED)
    db.add(vp); db.commit(); db.refresh(vp)
    pr = models.PowerRange(lens_model_id=variant.lens_model_id, variant_id=variant.id, pricing_id=vp.id,
                           sph_min=min(sph_min, sph_max), sph_max=max(sph_min, sph_max),
                           cyl_min=-max_cyl_abs, cyl_max=0.0,
                           total_power_min=sph_min, total_power_max=sph_max, max_cyl_abs=max_cyl_abs)
    db.add(pr); db.commit()
    return vp, pr


@pytest.fixture()
def mixed_mineral(db):
    co = models.Company(name="HOYA", country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename="Hoya_Price_List_2025_Updated.pdf",
                         file_path="Hoya_Price_List_2025_Updated.pdf", status=models.CatalogStatus.CONFIRMED)
    db.add(cat); db.commit(); db.refresh(cat)
    mineral = models.LensModel(company_id=co.id, name="Mineral", category=models.LensCategory.PROGRESSIVE)
    db.add(mineral); db.commit(); db.refresh(mineral)
    mc = models.Coating(code="Multi Coat", name="Multi Coat")
    pmc = models.Coating(code="Progressive Multi Coat", name="Progressive Multi Coat")
    db.add_all([mc, pmc]); db.commit()

    reg = {}
    # shared variants (plain + Summit both attached)
    v152 = _mk_variant(db, mineral, 1.52)
    reg["plain_152"] = _mk_pricing(db, v152, cat, mc, 7350, -14.0, 8.0, 4.0)
    reg["summit_152"] = _mk_pricing(db, v152, cat, pmc, 12200, -5.5, 6.0, 4.0)

    v152p = _mk_variant(db, mineral, 1.52, color_variant="Photo")
    reg["plain_152p"] = _mk_pricing(db, v152p, cat, mc, 12400, -8.0, 6.0, 4.0)
    reg["summit_152p"] = _mk_pricing(db, v152p, cat, pmc, 14700, -5.5, 6.0, 4.0)

    v181 = _mk_variant(db, mineral, 1.81)
    reg["plain_181"] = _mk_pricing(db, v181, cat, mc, 24150, -26.0, 15.0, 4.0)
    reg["summit_181"] = _mk_pricing(db, v181, cat, pmc, 26050, -20.0, -2.0, 4.0)

    # plain-only
    v19 = _mk_variant(db, mineral, 1.9)
    reg["plain_19"] = _mk_pricing(db, v19, cat, mc, 31400, -30.0, -2.25, 4.0)

    # Summit-only
    v16 = _mk_variant(db, mineral, 1.6)
    reg["summit_16"] = _mk_pricing(db, v16, cat, pmc, 13900, -7.5, 6.0, 4.0)
    v17 = _mk_variant(db, mineral, 1.7)
    reg["summit_17"] = _mk_pricing(db, v17, cat, pmc, 16200, -16.0, 8.0, 4.0)
    v16p = _mk_variant(db, mineral, 1.6, color_variant="Photo")
    reg["summit_16p"] = _mk_pricing(db, v16p, cat, pmc, 20200, -7.5, 6.0, 4.0)

    return {"company": co, "catalog": cat, "mineral": mineral, "mc": mc, "pmc": pmc, "registry": reg}


def _mk_sentinel_hoya_products(db, co, cat):
    """Bi-Focal + an Occupational product, to prove the split leaves them alone."""
    bifocal = models.LensModel(company_id=co.id, name="Bi-Focal", category=models.LensCategory.BIFOCAL)
    occ = models.LensModel(company_id=co.id, name="WorkSmart", category=models.LensCategory.OFFICE)
    db.add_all([bifocal, occ]); db.commit(); db.refresh(bifocal); db.refresh(occ)
    return bifocal, occ


# --------------------------------------------------------------- 1-5: identity/category
def test_split_produces_correct_categories_and_company(db, mixed_mineral):
    co = mixed_mineral["company"]
    hms.reconcile(db)
    mineral = db.query(models.LensModel).filter_by(company_id=co.id, name="Mineral").one()
    summit = db.query(models.LensModel).filter_by(company_id=co.id, name="Mineral Summit Progressive").one()
    assert mineral.id != summit.id
    assert mineral.category == models.LensCategory.SINGLE_VISION
    assert summit.category == models.LensCategory.PROGRESSIVE
    assert mineral.company_id == co.id and summit.company_id == co.id
    for lm in (mineral, summit):
        for v in db.query(models.LensVariant).filter_by(lens_model_id=lm.id).all():
            assert v.material == models.MaterialType.GLASS


# --------------------------------------------------------------- 6/7: row counts
def test_exactly_4_plain_and_6_summit_pricing_rows(db, mixed_mineral):
    co = mixed_mineral["company"]
    hms.reconcile(db)
    mineral = db.query(models.LensModel).filter_by(company_id=co.id, name="Mineral").one()
    summit = db.query(models.LensModel).filter_by(company_id=co.id, name="Mineral Summit Progressive").one()

    def _pricing_for(model):
        return (db.query(models.VariantPricing)
                .join(models.LensVariant, models.LensVariant.id == models.VariantPricing.variant_id)
                .filter(models.LensVariant.lens_model_id == model.id).all())

    assert len(_pricing_for(mineral)) == 4
    assert len(_pricing_for(summit)) == 6


# --------------------------------------------------------------- 8/9: exact prices preserved
def test_plain_and_summit_prices_preserved_exactly(db, mixed_mineral):
    co = mixed_mineral["company"]
    hms.reconcile(db)
    mineral = db.query(models.LensModel).filter_by(company_id=co.id, name="Mineral").one()
    summit = db.query(models.LensModel).filter_by(company_id=co.id, name="Mineral Summit Progressive").one()

    def _prices_by_index(model):
        rows = (db.query(models.VariantPricing)
                .join(models.LensVariant, models.LensVariant.id == models.VariantPricing.variant_id)
                .filter(models.LensVariant.lens_model_id == model.id).all())
        return sorted(float(r.price_pair) for r in rows)

    assert _prices_by_index(mineral) == sorted([7350, 12400, 24150, 31400])
    assert _prices_by_index(summit) == sorted([12200, 13900, 16200, 26050, 14700, 20200])


# --------------------------------------------------------------- 10: RX / Out Of Egypt
def test_all_ten_rows_remain_rx_out_of_egypt(db, mixed_mineral):
    hms.reconcile(db)
    rows = (db.query(models.VariantPricing)
            .join(models.Coating, models.Coating.id == models.VariantPricing.coating_id)
            .filter(models.Coating.code.in_(["Multi Coat", "Progressive Multi Coat"])).all())
    assert len(rows) == 10
    for r in rows:
        assert r.availability == models.PricingAvailability.RX
        assert r.market_scope == "Out Of Egypt"


# --------------------------------------------------------------- 11: G3 PowerRange unchanged
def test_g3_power_range_values_unchanged_by_split(db, mixed_mineral):
    reg = mixed_mineral["registry"]
    before = {key: (pr.total_power_min, pr.total_power_max, pr.max_cyl_abs) for key, (vp, pr) in reg.items()}
    hms.reconcile(db)
    for key, (vp, pr) in reg.items():
        db.refresh(pr)
        assert (pr.total_power_min, pr.total_power_max, pr.max_cyl_abs) == before[key], key


# --------------------------------------------------------------- 12/13: Progressive ADD
def test_plain_mineral_never_receives_progressive_add(db, mixed_mineral):
    co = mixed_mineral["company"]
    hms.reconcile(db)
    progressive_add_evidence.reconcile(db)
    mineral = db.query(models.LensModel).filter_by(company_id=co.id, name="Mineral").one()
    ranges = (db.query(models.PowerRange)
              .join(models.LensVariant, models.LensVariant.id == models.PowerRange.variant_id)
              .filter(models.LensVariant.lens_model_id == mineral.id).all())
    assert len(ranges) == 4
    for pr in ranges:
        assert pr.add_min is None and pr.add_max is None


def test_summit_progressive_receives_the_general_add_rule(db, mixed_mineral):
    co = mixed_mineral["company"]
    hms.reconcile(db)
    progressive_add_evidence.reconcile(db)
    summit = db.query(models.LensModel).filter_by(company_id=co.id, name="Mineral Summit Progressive").one()
    ranges = (db.query(models.PowerRange)
              .join(models.LensVariant, models.LensVariant.id == models.PowerRange.variant_id)
              .filter(models.LensVariant.lens_model_id == summit.id).all())
    assert len(ranges) == 6
    for pr in ranges:
        assert pr.add_min == 0.75 and pr.add_max == 3.50


# --------------------------------------------------------------- 14: strict negatives
def test_bifocal_and_occupational_hoya_products_unaffected(db, mixed_mineral):
    co, cat = mixed_mineral["company"], mixed_mineral["catalog"]
    bifocal, occ = _mk_sentinel_hoya_products(db, co, cat)
    hms.reconcile(db)
    progressive_add_evidence.reconcile(db)
    db.refresh(bifocal); db.refresh(occ)
    assert bifocal.category == models.LensCategory.BIFOCAL
    assert occ.category == models.LensCategory.OFFICE


# --------------------------------------------------------------- 15: shared variants separated
def test_shared_variants_are_safely_separated(db, mixed_mineral):
    co = mixed_mineral["company"]
    reg = mixed_mineral["registry"]
    plain_variant_152_id = reg["plain_152"][0].variant_id
    hms.reconcile(db)
    summit = db.query(models.LensModel).filter_by(company_id=co.id, name="Mineral Summit Progressive").one()
    db.refresh(reg["plain_152"][0])
    db.refresh(reg["summit_152"][0])
    # plain pricing still on the ORIGINAL variant, which stays under Mineral
    assert reg["plain_152"][0].variant_id == plain_variant_152_id
    original_variant = db.query(models.LensVariant).get(plain_variant_152_id)
    assert original_variant.lens_model_id == mixed_mineral["mineral"].id
    # summit pricing now points to a DIFFERENT (twin) variant, under Summit
    assert reg["summit_152"][0].variant_id != plain_variant_152_id
    twin_variant = db.query(models.LensVariant).get(reg["summit_152"][0].variant_id)
    assert twin_variant.lens_model_id == summit.id
    assert twin_variant.index_value == 1.52 and twin_variant.material == models.MaterialType.GLASS


# --------------------------------------------------------------- 16/17/18: no dup/orphan rows
def test_no_duplicate_or_orphan_rows_after_split(db, mixed_mineral):
    hms.reconcile(db)
    all_pricing = (db.query(models.VariantPricing)
                   .join(models.Coating, models.Coating.id == models.VariantPricing.coating_id)
                   .filter(models.Coating.code.in_(["Multi Coat", "Progressive Multi Coat"])).all())
    assert len(all_pricing) == 10  # never duplicated
    all_ranges = (db.query(models.PowerRange)
                  .filter(models.PowerRange.pricing_id.in_([p.id for p in all_pricing])).all())
    assert len(all_ranges) == 10  # never duplicated
    variant_ids = {p.variant_id for p in all_pricing}
    existing_variant_ids = {v.id for v in db.query(models.LensVariant).filter(models.LensVariant.id.in_(variant_ids)).all()}
    assert variant_ids == existing_variant_ids  # no orphan variant_id references
    for pr in all_ranges:
        assert db.query(models.LensVariant).get(pr.variant_id) is not None
        assert db.query(models.LensModel).get(pr.lens_model_id) is not None


# --------------------------------------------------------------- 19: idempotency
def test_reconcile_is_idempotent(db, mixed_mineral):
    result1 = hms.reconcile(db)
    assert result1["model_created"] == 1
    assert result1["category_fixed"] == 1
    assert result1["pricing_moved"] == 6
    assert result1["twin_variants_created"] == 3
    result2 = hms.reconcile(db)
    assert result2 == {"category_fixed": 0, "model_created": 0, "pricing_moved": 0, "twin_variants_created": 0}


# --------------------------------------------------------------- search behavior A-G
def test_A_plain_mineral_reachable_in_single_vision_search(db, mixed_mineral):
    hms.reconcile(db)
    presc = _mk_presc(db, -6.0, -1.0)  # inside plain 1.52's -14/8/4 band
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="distance"))
    names = {(r.model_name, r.coating_code) for g in resp.groups for r in g.results}
    assert ("Mineral", "Multi Coat") in names


def test_B_plain_mineral_absent_from_progressive_results(db, mixed_mineral):
    hms.reconcile(db)
    progressive_add_evidence.reconcile(db)
    presc = _mk_presc(db, -3.0, -1.0, od_add=2.0, os_add=2.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="progressive"))
    coatings = {r.coating_code for g in resp.groups for r in g.results if r.model_name == "Mineral"}
    assert "Multi Coat" not in coatings


def test_C_summit_progressive_reachable_with_valid_add(db, mixed_mineral):
    hms.reconcile(db)
    progressive_add_evidence.reconcile(db)
    presc = _mk_presc(db, -3.0, -1.0, od_add=2.0, os_add=2.0)  # inside summit 1.52's -5.5/6/4 band
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="progressive"))
    names = {(r.model_name, r.coating_code) for g in resp.groups for r in g.results}
    assert ("Mineral Summit Progressive", "Progressive Multi Coat") in names


def test_D_summit_progressive_absent_from_ordinary_single_vision(db, mixed_mineral):
    hms.reconcile(db)
    progressive_add_evidence.reconcile(db)
    presc = _mk_presc(db, -3.0, -1.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="distance"))
    names = {r.model_name for g in resp.groups for r in g.results}
    assert "Mineral Summit Progressive" not in names


@pytest.mark.parametrize("add,eligible", [(0.50, False), (0.75, True), (3.50, True), (3.75, False)])
def test_E_F_add_boundaries_enforced_for_summit(db, mixed_mineral, add, eligible):
    hms.reconcile(db)
    progressive_add_evidence.reconcile(db)
    presc = _mk_presc(db, -3.0, -1.0, od_add=add, os_add=add)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="progressive"))
    names = {r.model_name for g in resp.groups for r in g.results if r.coating_code == "Progressive Multi Coat"}
    assert ("Mineral Summit Progressive" in names) == eligible


def test_G_prices_stay_tied_to_the_correct_row(db, mixed_mineral):
    hms.reconcile(db)
    progressive_add_evidence.reconcile(db)
    presc = _mk_presc(db, -3.0, -1.0, od_add=2.0, os_add=2.0)
    resp = product_search.search(db, presc, schemas.ProductSearchRequest(use_mode="progressive"))
    for g in resp.groups:
        for r in g.results:
            if r.model_name == "Mineral Summit Progressive" and r.index_value == 1.52 and r.color_variant is None:
                assert r.pair_fulfillment.price_pair == 12200
            if r.model_name == "Mineral Summit Progressive" and r.index_value == 1.52 and r.color_variant == "Photo":
                assert r.pair_fulfillment.price_pair == 14700
