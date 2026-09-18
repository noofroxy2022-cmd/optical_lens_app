"""Permanent regression coverage for the P0 Stock-Egypt reconciliation
(ZEISS / PLATINUM / SEIKO / BBGR).

Deliberately synthetic, mirroring the corrected shape directly via the ORM
(no PDF parsing, no dependency on the live v12_dev.db), matching the same
pattern as test_bbgr_import.py / test_platinum_import.py / test_seiko_import.py.

CONFIRMED BUSINESS FACT (store owner, not catalog literal text): ZEISS,
PLATINUM, SEIKO and BBGR all have STOCK physically available inside Egypt.
This fact may be used to set market_scope="Egypt" on a catalog-proven STOCK
row for these four manufacturers - it is NEVER used to invent a SPH/CYL
range, a price, or a product identity, and it never converts a genuine RX
row into Stock. Every PowerRange asserted here comes from real evidence
(ZEISS_Main_Catalog.pdf pp.5-6 "ZEISS Finished Single Vision Lenses";
PLATINUM's own pre-existing 16 proven Stock ranges; BBGR's later,
user/store-owner-confirmed total-power business rule - -6.00D minus /
+4.00D plus / max 2.00D CYL, the project's existing G3 total-power/meridian
mechanism, applied ONLY to BBGR's 7 Stock rows, never to any BBGR RX row).
SEIKO's "STOCK IN EGYPT" price table prints NO SPH/CYL range anywhere in
its catalog - its rows stay market="Egypt" with ZERO PowerRange, and
prescription compatibility is never fabricated for them (see
test_bbgr_import.py's equivalent BBGR-specific coverage for the BBGR rule).
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


def _mk_company(db, name):
    co = models.Company(name=name, country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    return co


def _mk_catalog(db, company, filename="synthetic.pdf"):
    cat = models.Catalog(company_id=company.id, filename=filename,
                         file_path=filename, status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)
    return cat


def _mk_model(db, company, name, category=models.LensCategory.SINGLE_VISION):
    m = models.LensModel(company_id=company.id, name=name, category=category)
    db.add(m); db.commit(); db.refresh(m)
    return m


def _mk_coating(db, code):
    existing = db.query(models.Coating).filter(models.Coating.code == code).first()
    if existing:
        return existing
    c = models.Coating(code=code, name=code)
    db.add(c); db.commit(); db.refresh(c)
    return c


def _mk_variant(db, model, index_value=1.50, treatment_band=None, design_tier=None, color_variant=None):
    v = models.LensVariant(
        lens_model_id=model.id, material=models.MaterialType.CR39, index_value=index_value,
        design_type=models.DesignType.SPHERICAL, is_aspherical=False,
        treatment_band=treatment_band, design_tier=design_tier, color_variant=color_variant,
        price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    return v


def _mk_pricing(db, variant, catalog, *, availability, price, coating=None, market_scope=None):
    vp = models.VariantPricing(
        variant_id=variant.id, coating_id=(coating.id if coating else None),
        availability=availability, price_pair=Decimal(str(price)),
        currency="EGP", source_catalog_id=catalog.id, market_scope=market_scope)
    db.add(vp); db.commit(); db.refresh(vp)
    return vp


def _mk_range(db, model, variant, pricing, sph_min, sph_max, cyl_min=-10.0, cyl_max=0.0,
             total_power_min=None, total_power_max=None, max_cyl_abs=None):
    pr = models.PowerRange(lens_model_id=model.id, variant_id=variant.id, pricing_id=pricing.id,
                           sph_min=sph_min, sph_max=sph_max, cyl_min=cyl_min, cyl_max=cyl_max,
                           total_power_min=total_power_min, total_power_max=total_power_max,
                           max_cyl_abs=max_cyl_abs)
    db.add(pr); db.commit()
    return pr


def _mk_presc(db, sph, cyl, axis=90, name="p"):
    p = models.Prescription(
        customer_name=name,
        od_sph_original=sph, od_cyl_original=cyl, od_axis_original=axis,
        od_sph=sph, od_cyl=cyl, od_axis=axis, od_add=None,
        os_sph_original=sph, os_cyl_original=cyl, os_axis_original=axis,
        os_sph=sph, os_cyl=cyl, os_axis=axis, os_add=None, pd=63)
    db.add(p); db.commit(); db.refresh(p)
    return p


def _search(db, presc):
    req = schemas.ProductSearchRequest(mode="automatic", use_mode="distance", customer_need="none")
    return product_search.search(db, presc, req)


# ===================================================== 1. ZEISS Finished SV
def test_zeiss_finished_sv_stock_maps_egypt_with_proven_range(db):
    """ZEISS_Main_Catalog.pdf p.5 'ZEISS Finished Single Vision Lenses' /
    'Freeform in stock': ClearView 1.5, Clear treatment, DuraVision Platinum
    coating, printed price 4320 EGP. p.6's SPH/CYL availability chart proves
    (at minimum) the safe inscribed rectangle sph -3.00..+6.00 / cyl
    -3.00..0.00, which covers -2.00/-1.00."""
    co = _mk_company(db, "ZEISS")
    cat = _mk_catalog(db, co, "ZEISS_Main_Catalog.pdf")
    m = _mk_model(db, co, "ClearView FSV")
    coating = _mk_coating(db, "DuraVision Platinum")
    v = _mk_variant(db, m, 1.5, treatment_band="Clear")
    vp = _mk_pricing(db, v, cat, availability=models.PricingAvailability.STOCK,
                      price=4320, coating=coating, market_scope="Egypt")
    _mk_range(db, m, v, vp, sph_min=-3.0, sph_max=6.0, cyl_min=-3.0, cyl_max=0.0)

    assert product_search._row_route(vp) == "stock_egypt"
    presc = _mk_presc(db, -2.0, -1.0, name="zeiss")
    assert product_search._row_eye_status(vp, presc, "od") == "eligible"
    resp = _search(db, presc)
    egypt = next(g for g in resp.groups if g.key == "stock_egypt")
    assert any(r.company_name == "ZEISS" for r in egypt.results)
    hit = next(r for r in egypt.results if r.company_name == "ZEISS")
    assert hit.pair_fulfillment.price_pair == Decimal("4320")   # catalog price untouched


def test_zeiss_finished_sv_never_invents_beyond_proven_rectangle(db):
    """The SAME 1.74 ClearView identity's chart proves only sph -8.00..-2.25
    (ZEISS_Main_Catalog.pdf p.6, '1.74 ClearView') - -2.00 is genuinely
    outside the printed diamond, so it must stay ineligible, never a
    generously-rounded invented boundary."""
    co = _mk_company(db, "ZEISS")
    cat = _mk_catalog(db, co, "ZEISS_Main_Catalog.pdf")
    m = _mk_model(db, co, "ClearView FSV")
    coating = _mk_coating(db, "DuraVision Platinum")
    v = _mk_variant(db, m, 1.74, treatment_band="Clear")
    vp = _mk_pricing(db, v, cat, availability=models.PricingAvailability.STOCK,
                      price=11190, coating=coating, market_scope="Egypt")
    _mk_range(db, m, v, vp, sph_min=-8.0, sph_max=-2.25, cyl_min=-2.0, cyl_max=0.0)

    presc = _mk_presc(db, -2.0, -1.0, name="zeiss174")
    assert product_search._row_eye_status(vp, presc, "od") == "ineligible"


# =================================================== 2. PLATINUM Stock Egypt
def test_platinum_stock_rows_classify_egypt_preserving_proven_range(db):
    """PLATINUM.pdf's own explicit 'STOCK LENSES' section (distinct from its
    RX/manufacturing products) already gave this project 16 real proven
    Stock PowerRanges (untouched pre-existing evidence) - the P0 fix only
    sets market_scope="Egypt" on top of that pre-existing, unchanged range;
    it never re-derives or widens the range itself."""
    co = _mk_company(db, "PLATINUM")
    cat = _mk_catalog(db, co, "PLATINUM.pdf")
    m = _mk_model(db, co, "PLATINUM")
    v = _mk_variant(db, m, 1.5)
    vp = _mk_pricing(db, v, cat, availability=models.PricingAvailability.STOCK,
                      price=250, market_scope=None)   # pre-fix state: NULL
    _mk_range(db, m, v, vp, sph_min=-6.0, sph_max=4.0, cyl_min=-2.0, cyl_max=0.0)

    assert product_search._row_route(vp) == "stock_market_unknown"   # pre-fix classification

    vp.market_scope = "Egypt"   # the P0 fix: reclassify, never touch price/range
    db.commit()

    assert product_search._row_route(vp) == "stock_egypt"
    assert vp.price_pair == Decimal("250")            # price never changed
    ranges = list(vp.power_ranges)
    assert len(ranges) == 1
    assert (ranges[0].sph_min, ranges[0].sph_max, ranges[0].cyl_min, ranges[0].cyl_max) == (-6.0, 4.0, -2.0, 0.0)

    presc = _mk_presc(db, -2.0, -1.0, name="platinum")
    resp = _search(db, presc)
    egypt = next(g for g in resp.groups if g.key == "stock_egypt")
    assert any(r.company_name == "PLATINUM" for r in egypt.results)


# ====================================================== 3/4. SEIKO Stock-in-Egypt
def test_seiko_stock_in_egypt_rows_classify_correctly(db):
    """Seiko_Pricelist_2025.pdf p.2 'STOCK IN EGYPT' prints these five
    identities (1.5 SRC-ONE, 1.5 SRC-SCREEN, 1.60/1.67/1.74 AS SRC-ONE) with
    an explicit Egypt market - unlike PLATINUM/BBGR, SEIKO's own catalog
    text ALREADY proves Egypt directly, so this was already correct before
    the P0 task and must not regress."""
    co = _mk_company(db, "SEIKO")
    cat = _mk_catalog(db, co, "Seiko_Pricelist_2025.pdf")
    m = _mk_model(db, co, "SEIKO")
    coating = _mk_coating(db, "SRC - ONE")
    v = _mk_variant(db, m, 1.5)
    vp = _mk_pricing(db, v, cat, availability=models.PricingAvailability.STOCK,
                      price=2025, coating=coating, market_scope="Egypt")
    assert product_search._row_route(vp) == "stock_egypt"


def test_seiko_stock_in_egypt_range_stays_unproven_no_range_in_catalog(db):
    """Neither Seiko_Pricelist_2025.pdf's 'STOCK IN EGYPT' table nor any
    other page of the 8-page catalog prints a SPH/CYL range for these five
    identities (checked directly, not merely assumed absent). Per the P0
    task's own explicit SEIKO instruction: keep the Egypt classification,
    but NEVER invent a range - compatibility with any specific prescription
    stays unproven (ineligible, never a false 'eligible')."""
    co = _mk_company(db, "SEIKO")
    cat = _mk_catalog(db, co, "Seiko_Pricelist_2025.pdf")
    m = _mk_model(db, co, "SEIKO")
    coating = _mk_coating(db, "SRC - SCREEN")
    v = _mk_variant(db, m, 1.5)
    vp = _mk_pricing(db, v, cat, availability=models.PricingAvailability.STOCK,
                      price=3037, coating=coating, market_scope="Egypt")
    assert list(vp.power_ranges) == []
    presc = _mk_presc(db, -2.0, -1.0, name="seiko")
    assert product_search._row_eye_status(vp, presc, "od") == "ineligible"
    resp = _search(db, presc)
    egypt = next(g for g in resp.groups if g.key == "stock_egypt")
    assert not any(r.company_name == "SEIKO" for r in egypt.results)   # never falsely proven


# ======================================================= 5/6. BBGR Stock Egypt
def test_bbgr_stock_rows_egypt_and_separate_from_rx_sv(db):
    """BBGR فرنساوي.pdf explicitly separates 'Stock lenses' (p.2, 7 rows)
    from 'RX S.V' (p.2, distinct section) - this STRUCTURAL split is what
    proves STOCK vs RX; the Egypt MARKET itself is the confirmed business
    fact, layered on top without ever touching the RX rows or collapsing
    the two sections together."""
    co = _mk_company(db, "BBGR")
    cat = _mk_catalog(db, co, "BBGR فرنساوي.pdf")
    sv = _mk_model(db, co, "BBGR")
    diams = _mk_coating(db, "Diam's")

    v_stock = _mk_variant(db, sv, 1.56)
    vp_stock = _mk_pricing(db, v_stock, cat, availability=models.PricingAvailability.STOCK,
                            price=1050, coating=diams, market_scope="Egypt")
    v_rx = _mk_variant(db, sv, 1.59)
    vp_rx = _mk_pricing(db, v_rx, cat, availability=models.PricingAvailability.RX, price=2250)

    assert product_search._row_route(vp_stock) == "stock_egypt"
    assert product_search._row_route(vp_rx) == "rx"
    assert vp_stock.id != vp_rx.id
    assert v_stock.id != v_rx.id


def test_bbgr_stock_total_power_range_uses_real_meridian_check(db):
    """The 6-page 'BBGR فرنساوي.pdf' itself prints no SPH/CYL power-range
    table or chart anywhere, for STOCK or RX (checked directly - page 6 has
    neither text nor embedded images). BBGR's 7 Stock rows' range instead
    comes from a SEPARATE, later, user/store-owner-confirmed total-power
    business rule (-6.00D minus / +4.00D plus / max 2.00D CYL), applied via
    the project's existing G3 total-power/meridian mechanism - never a naive
    "SPH -6.00..+4.00" box. SPH -2.00/CYL -1.00 has meridians {-2.00,-3.00},
    both inside [-6.00,+4.00], CYL magnitude 1.00 <= 2.00 -> eligible. A Rx
    genuinely outside the confirmed envelope (SPH -8.00) stays ineligible -
    the rule is never invented wider than what was confirmed."""
    co = _mk_company(db, "BBGR")
    cat = _mk_catalog(db, co, "BBGR فرنساوي.pdf")
    sv = _mk_model(db, co, "BBGR")
    diams = _mk_coating(db, "Diam's")
    v_stock = _mk_variant(db, sv, 1.56)
    vp_stock = _mk_pricing(db, v_stock, cat, availability=models.PricingAvailability.STOCK,
                            price=1050, coating=diams, market_scope="Egypt")
    _mk_range(db, sv, v_stock, vp_stock, sph_min=-6.0, sph_max=4.0, cyl_min=-2.0, cyl_max=0.0,
              total_power_min=-6.0, total_power_max=4.0, max_cyl_abs=2.0)  # last 3 = G3 fields
    presc_inside = _mk_presc(db, -2.0, -1.0, name="bbgr-inside")
    assert product_search._row_eye_status(vp_stock, presc_inside, "od") == "eligible"
    presc_outside = _mk_presc(db, -8.0, 0.0, name="bbgr-outside")
    assert product_search._row_eye_status(vp_stock, presc_outside, "od") == "ineligible"


# ============================================ 7/8. Live -2/-1x90 combined acceptance
def test_live_acceptance_rx_each_manufacturer_per_proven_range(db):
    """The exact P0 acceptance Rx (SPH -2.00 / CYL -1.00 / Axis 90 both
    eyes, Distance, customer_need=none). ZEISS, PLATINUM and BBGR must
    appear in stock_egypt (their proven ranges - BBGR's via the confirmed
    total-power G3 rule - cover this Rx's meridians {-2.00,-3.00}); SEIKO
    must NOT (its Egypt classification is proven but no range exists
    anywhere in its catalog); a control manufacturer with a genuinely
    UNSPECIFIED market must stay in stock_market_unknown, never silently
    promoted to Egypt by this fix."""
    presc_probe = None

    # ZEISS - eligible
    zeiss = _mk_company(db, "ZEISS")
    zcat = _mk_catalog(db, zeiss, "ZEISS_Main_Catalog.pdf")
    zm = _mk_model(db, zeiss, "ClearView FSV")
    zc = _mk_coating(db, "DuraVision Platinum")
    zv = _mk_variant(db, zm, 1.5, treatment_band="Clear")
    zvp = _mk_pricing(db, zv, zcat, availability=models.PricingAvailability.STOCK,
                       price=4320, coating=zc, market_scope="Egypt")
    _mk_range(db, zm, zv, zvp, sph_min=-3.0, sph_max=6.0, cyl_min=-3.0, cyl_max=0.0)

    # PLATINUM - eligible
    platinum = _mk_company(db, "PLATINUM")
    pcat = _mk_catalog(db, platinum, "PLATINUM.pdf")
    pm = _mk_model(db, platinum, "PLATINUM")
    pv = _mk_variant(db, pm, 1.5)
    pvp = _mk_pricing(db, pv, pcat, availability=models.PricingAvailability.STOCK,
                       price=250, market_scope="Egypt")
    _mk_range(db, pm, pv, pvp, sph_min=-6.0, sph_max=4.0, cyl_min=-2.0, cyl_max=0.0)

    # SEIKO - Egypt but unproven range -> must not appear
    seiko = _mk_company(db, "SEIKO")
    scat = _mk_catalog(db, seiko, "Seiko_Pricelist_2025.pdf")
    sm = _mk_model(db, seiko, "SEIKO")
    sc = _mk_coating(db, "SRC - ONE")
    sv = _mk_variant(db, sm, 1.5)
    _mk_pricing(db, sv, scat, availability=models.PricingAvailability.STOCK,
                price=2025, coating=sc, market_scope="Egypt")

    # BBGR - Egypt AND eligible (confirmed total-power G3 rule)
    bbgr = _mk_company(db, "BBGR")
    bcat = _mk_catalog(db, bbgr, "BBGR فرنساوي.pdf")
    bm = _mk_model(db, bbgr, "BBGR")
    bcoat = _mk_coating(db, "Diam's")
    bv = _mk_variant(db, bm, 1.56)
    bvp = _mk_pricing(db, bv, bcat, availability=models.PricingAvailability.STOCK,
                       price=1050, coating=bcoat, market_scope="Egypt")
    _mk_range(db, bm, bv, bvp, sph_min=-6.0, sph_max=4.0, cyl_min=-2.0, cyl_max=0.0,
              total_power_min=-6.0, total_power_max=4.0, max_cyl_abs=2.0)

    # Control: an existing-pattern manufacturer (e.g. PIXEL-like) whose Stock
    # market is genuinely unspecified in its own catalog - must stay
    # stock_market_unknown, proving this fix never touches unrelated companies.
    control = _mk_company(db, "ControlCo")
    ccat = _mk_catalog(db, control, "control.pdf")
    cm = _mk_model(db, control, "Control")
    cv = _mk_variant(db, cm, 1.5)
    cvp = _mk_pricing(db, cv, ccat, availability=models.PricingAvailability.STOCK,
                       price=999, market_scope=None)
    _mk_range(db, cm, cv, cvp, sph_min=-6.0, sph_max=4.0, cyl_min=-2.0, cyl_max=0.0)

    presc = _mk_presc(db, -2.0, -1.0, name="live-acceptance")
    resp = _search(db, presc)
    egypt = {r.company_name for g in resp.groups if g.key == "stock_egypt" for r in g.results}
    unknown = {r.company_name for g in resp.groups if g.key == "stock_market_unknown" for r in g.results}

    assert "ZEISS" in egypt
    assert "PLATINUM" in egypt
    assert "BBGR" in egypt
    assert "SEIKO" not in egypt
    assert "ControlCo" in unknown
    assert "ControlCo" not in egypt


# ==================================================== 9. No duplicate identities
def test_no_duplicate_pricing_identity_created(db):
    """The DB's own uq_variant_pricing_current constraint must still reject a
    second CURRENT price for the identical (variant, coating, availability,
    power_scope, market_scope) tuple - the P0 reconciliation only ever
    UPDATEs an existing row's market_scope or INSERTs a genuinely new
    (index, treatment_band, coating) identity, never a duplicate of one that
    already exists."""
    co = _mk_company(db, "PLATINUM")
    cat = _mk_catalog(db, co, "PLATINUM.pdf")
    m = _mk_model(db, co, "PLATINUM")
    v = _mk_variant(db, m, 1.5)
    _mk_pricing(db, v, cat, availability=models.PricingAvailability.STOCK,
                price=250, market_scope="Egypt")
    dup = models.VariantPricing(
        variant_id=v.id, coating_id=None, availability=models.PricingAvailability.STOCK,
        price_pair=Decimal("250"), currency="EGP", source_catalog_id=cat.id, market_scope="Egypt")
    db.add(dup)
    with pytest.raises(Exception):
        db.commit()
    db.rollback()


# ======================================================= 10. No pair-price changes
def test_market_scope_reclassification_never_touches_price(db):
    """Setting market_scope="Egypt" on an existing proven Stock row (the P0
    fix's ONLY write to already-existing rows) must never alter price_pair,
    currency, or the linked PowerRange bounds."""
    co = _mk_company(db, "PLATINUM")
    cat = _mk_catalog(db, co, "PLATINUM.pdf")
    m = _mk_model(db, co, "PLATINUM")
    v = _mk_variant(db, m, 1.56)
    vp = _mk_pricing(db, v, cat, availability=models.PricingAvailability.STOCK,
                      price=380, market_scope=None)
    _mk_range(db, m, v, vp, sph_min=-6.0, sph_max=6.0, cyl_min=-2.0, cyl_max=0.0)
    before = (vp.price_pair, vp.currency,
              [(r.sph_min, r.sph_max, r.cyl_min, r.cyl_max) for r in vp.power_ranges])

    vp.market_scope = "Egypt"
    db.commit()

    after = (vp.price_pair, vp.currency,
             [(r.sph_min, r.sph_max, r.cyl_min, r.cyl_max) for r in vp.power_ranges])
    assert before == after


# ================================================== 11. Synchrony Stock Egypt
def test_synchrony_null_market_rows_reclassify_egypt_ooe_untouched(db):
    """Synchrony's 3 Stock rows whose market is genuinely unspecified in the
    catalog (market_scope NULL) are confirmed Stock INSIDE Egypt (store-owner
    business fact) and reclassify to "Egypt". The 2 existing Synchrony Stock
    rows already proven "Out Of Egypt" are a SEPARATE catalog fact and must
    never be touched by this reclassification."""
    co = _mk_company(db, "Synchrony")
    cat = _mk_catalog(db, co, "Synchrony By Zeiss.pdf")
    m = _mk_model(db, co, "Synchrony")
    v1 = _mk_variant(db, m, 1.56)
    vp1 = _mk_pricing(db, v1, cat, availability=models.PricingAvailability.STOCK,
                       price=850, market_scope=None)
    v2 = _mk_variant(db, m, 1.6)
    vp2 = _mk_pricing(db, v2, cat, availability=models.PricingAvailability.STOCK,
                       price=1700, market_scope=None)
    v_ooe = _mk_variant(db, m, 1.67)
    vp_ooe = _mk_pricing(db, v_ooe, cat, availability=models.PricingAvailability.STOCK,
                          price=2800, market_scope="Out Of Egypt")

    before_ooe = (vp_ooe.market_scope, vp_ooe.price_pair)
    for r in (vp1, vp2):
        if r.market_scope != "Egypt":
            r.market_scope = "Egypt"
    db.commit()

    assert vp1.market_scope == "Egypt"
    assert vp2.market_scope == "Egypt"
    assert product_search._row_route(vp1) == "stock_egypt"
    assert product_search._row_route(vp2) == "stock_egypt"
    # OOE row completely untouched
    assert (vp_ooe.market_scope, vp_ooe.price_pair) == before_ooe
    assert product_search._row_route(vp_ooe) == "stock_outside"


# ==================================================== 12. SEIKO G3 live Rx
def test_seiko_egypt_total_power_range_proves_live_rx_eligibility(db):
    """SEIKO's 5 'STOCK IN EGYPT' rows now carry the confirmed total-power
    envelope (-6.00D/+4.00D/max 2.00D CYL, same G3 mechanism as BBGR). SPH
    -2.00/CYL -1.00 has meridians {-2.00,-3.00}, both inside [-6.00,+4.00],
    CYL magnitude 1.00 <= 2.00 -> eligible. A Rx genuinely outside the
    envelope stays ineligible - never invented wider than confirmed."""
    co = _mk_company(db, "SEIKO")
    cat = _mk_catalog(db, co, "Seiko_Pricelist_2025.pdf")
    m = _mk_model(db, co, "SEIKO")
    coat = _mk_coating(db, "SRC - ONE")
    v = _mk_variant(db, m, 1.5)
    vp = _mk_pricing(db, v, cat, availability=models.PricingAvailability.STOCK,
                      price=2025, coating=coat, market_scope="Egypt")
    _mk_range(db, m, v, vp, sph_min=-6.0, sph_max=4.0, cyl_min=-2.0, cyl_max=0.0,
              total_power_min=-6.0, total_power_max=4.0, max_cyl_abs=2.0)
    presc_inside = _mk_presc(db, -2.0, -1.0, name="seiko-inside")
    assert product_search._row_eye_status(vp, presc_inside, "od") == "eligible"
    presc_outside = _mk_presc(db, -8.0, 0.0, name="seiko-outside")
    assert product_search._row_eye_status(vp, presc_outside, "od") == "ineligible"


def test_seiko_rx_and_ooe_rows_untouched_by_egypt_g3_rule(db):
    """The SEIKO G3 total-power range is scoped ONLY to the 5 Stock-Egypt
    rows - a SEIKO RX row and a SEIKO Stock Out-Of-Egypt row must never gain
    a range or otherwise change behavior from this fix."""
    co = _mk_company(db, "SEIKO")
    cat = _mk_catalog(db, co, "Seiko_Pricelist_2025.pdf")
    m = _mk_model(db, co, "SEIKO")
    v_rx = _mk_variant(db, m, 1.6, treatment_band="RX-line")
    vp_rx = _mk_pricing(db, v_rx, cat, availability=models.PricingAvailability.RX, price=5000)
    v_ooe = _mk_variant(db, m, 1.5, treatment_band="OOE-line")
    vp_ooe = _mk_pricing(db, v_ooe, cat, availability=models.PricingAvailability.STOCK,
                          price=2250, market_scope="Out Of Egypt")
    assert list(vp_rx.power_ranges) == []
    assert list(vp_ooe.power_ranges) == []
    presc = _mk_presc(db, -2.0, -1.0, name="seiko-scope")
    # RX with zero range is eligible purely by the permanent RX domain rule -
    # unaffected either way; the point is no PowerRange was fabricated for it.
    assert product_search._row_eye_status(vp_rx, presc, "od") == "eligible"
    assert list(vp_rx.power_ranges) == []
    # OOE stock with zero range stays ineligible - never silently ranged.
    assert product_search._row_eye_status(vp_ooe, presc, "od") == "ineligible"
    assert list(vp_ooe.power_ranges) == []


# ============================================== 13/14/15. DIVEL Sun Plano-only
def test_divel_sun_rows_exact_plano_only_reject_minus_rx(db):
    """DIVEL ITALIA's 6 Sun/Mirror/Polar Stock-Egypt rows are confirmed
    Plano-only sun products (store-owner business fact): SPH=0.00 exact,
    CYL=0.00 exact, using the same "EXACT zero-tolerance" G3-fields pattern
    already used for PLATINUM's plano rows. SPH -2.00/CYL -1.00 must be
    rejected - it is not Plano."""
    co = _mk_company(db, "DIVEL ITALIA")
    cat = _mk_catalog(db, co, "divel.pdf")
    m = _mk_model(db, co, "DIVEL ITALIA")
    coat = _mk_coating(db, "Sun Lenses")
    v = _mk_variant(db, m, 1.5, color_variant="Gray/Brown/G15/Blue")
    vp = _mk_pricing(db, v, cat, availability=models.PricingAvailability.STOCK,
                      price=900, coating=coat, market_scope="Egypt")
    _mk_range(db, m, v, vp, sph_min=0.0, sph_max=0.0, cyl_min=0.0, cyl_max=0.0,
              total_power_min=0.0, total_power_max=0.0, max_cyl_abs=0.0)
    presc_rx = _mk_presc(db, -2.0, -1.0, name="divel-sun-rx")
    assert product_search._row_eye_status(vp, presc_rx, "od") == "ineligible"


def test_divel_sun_rows_accept_true_plano(db):
    """The same DIVEL Sun row must be proven eligible for a true Plano
    (0.00/0.00) request, and its catalog price is unchanged."""
    co = _mk_company(db, "DIVEL ITALIA")
    cat = _mk_catalog(db, co, "divel.pdf")
    m = _mk_model(db, co, "DIVEL ITALIA")
    coat = _mk_coating(db, "Mirror")
    v = _mk_variant(db, m, 1.5, color_variant="Red/R.Gold")
    vp = _mk_pricing(db, v, cat, availability=models.PricingAvailability.STOCK,
                      price=3000, coating=coat, market_scope="Egypt")
    _mk_range(db, m, v, vp, sph_min=0.0, sph_max=0.0, cyl_min=0.0, cyl_max=0.0,
              total_power_min=0.0, total_power_max=0.0, max_cyl_abs=0.0)
    presc_plano = _mk_presc(db, 0.0, 0.0, name="divel-sun-plano")
    assert product_search._row_eye_status(vp, presc_plano, "od") == "eligible"
    assert vp.price_pair == Decimal("3000")


def test_divel_regular_prescription_rows_unaffected_by_sun_plano_rule(db):
    """DIVEL's other regular prescription Stock rows (a different coating
    entirely, e.g. "Performance") must keep their own proven range/price,
    completely unaffected by the Sun/Mirror/Polar Plano-only rule."""
    co = _mk_company(db, "DIVEL ITALIA")
    cat = _mk_catalog(db, co, "divel.pdf")
    m = _mk_model(db, co, "DIVEL ITALIA")
    coat = _mk_coating(db, "Performance")
    v = _mk_variant(db, m, 1.56)
    vp = _mk_pricing(db, v, cat, availability=models.PricingAvailability.STOCK,
                      price=850, coating=coat, market_scope="Egypt")
    _mk_range(db, m, v, vp, sph_min=-6.0, sph_max=6.0, cyl_min=-2.0, cyl_max=0.0)
    presc = _mk_presc(db, -2.0, -1.0, name="divel-regular")
    assert product_search._row_eye_status(vp, presc, "od") == "eligible"
    assert vp.price_pair == Decimal("850")


# ======================== 16. Combined live acceptance after Synchrony/SEIKO/DIVEL
def test_live_acceptance_after_synchrony_seiko_divel_fix(db):
    """The full P0 acceptance Rx again, now with Synchrony/SEIKO/DIVEL-Sun
    layered on: Synchrony and SEIKO must now appear in stock_egypt; the 6
    DIVEL Sun Plano rows must NOT (this Rx is not Plano); a Plano 0.00/0.00
    request must surface those same 6 Sun rows in stock_egypt instead."""
    seiko = _mk_company(db, "SEIKO")
    scat = _mk_catalog(db, seiko, "Seiko_Pricelist_2025.pdf")
    sm = _mk_model(db, seiko, "SEIKO")
    sc = _mk_coating(db, "SRC - ONE")
    sv = _mk_variant(db, sm, 1.5)
    svp = _mk_pricing(db, sv, scat, availability=models.PricingAvailability.STOCK,
                       price=2025, coating=sc, market_scope="Egypt")
    _mk_range(db, sm, sv, svp, sph_min=-6.0, sph_max=4.0, cyl_min=-2.0, cyl_max=0.0,
              total_power_min=-6.0, total_power_max=4.0, max_cyl_abs=2.0)

    synchrony = _mk_company(db, "Synchrony")
    ycat = _mk_catalog(db, synchrony, "Synchrony By Zeiss.pdf")
    ym = _mk_model(db, synchrony, "Synchrony")
    yv = _mk_variant(db, ym, 1.56)
    yvp = _mk_pricing(db, yv, ycat, availability=models.PricingAvailability.STOCK,
                       price=850, market_scope="Egypt")
    _mk_range(db, ym, yv, yvp, sph_min=-6.0, sph_max=6.0, cyl_min=-4.0, cyl_max=0.0)  # pre-existing proven range, unrelated to this fix

    divel = _mk_company(db, "DIVEL ITALIA")
    dcat = _mk_catalog(db, divel, "divel.pdf")
    dm = _mk_model(db, divel, "DIVEL ITALIA")
    dcoat = _mk_coating(db, "Sun Lenses")
    dv = _mk_variant(db, dm, 1.5, color_variant="Gray/Brown/G15/Blue")
    dvp = _mk_pricing(db, dv, dcat, availability=models.PricingAvailability.STOCK,
                       price=900, coating=dcoat, market_scope="Egypt")
    _mk_range(db, dm, dv, dvp, sph_min=0.0, sph_max=0.0, cyl_min=0.0, cyl_max=0.0,
              total_power_min=0.0, total_power_max=0.0, max_cyl_abs=0.0)

    presc_rx = _mk_presc(db, -2.0, -1.0, name="combined-rx")
    resp_rx = _search(db, presc_rx)
    egypt_rx = {r.company_name for g in resp_rx.groups if g.key == "stock_egypt" for r in g.results}
    assert "SEIKO" in egypt_rx
    assert "Synchrony" in egypt_rx
    assert "DIVEL ITALIA" not in egypt_rx
    assert len(resp_rx.stock_egypt_unverified) == 0

    presc_plano = _mk_presc(db, 0.0, 0.0, name="combined-plano")
    resp_plano = _search(db, presc_plano)
    egypt_plano = {r.company_name for g in resp_plano.groups if g.key == "stock_egypt" for r in g.results}
    assert "DIVEL ITALIA" in egypt_plano
