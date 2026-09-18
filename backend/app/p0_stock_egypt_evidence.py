"""P0 Stock-Egypt reconciliation: ZEISS / PLATINUM / SEIKO / BBGR / Synchrony
/ DIVEL ITALIA.

CONFIRMED BUSINESS FACT (store owner, not catalog literal text): ZEISS,
PLATINUM, SEIKO, BBGR and Synchrony all have STOCK physically available
inside Egypt. This fact is used ONLY to set VariantPricing.market_scope=
"Egypt" on a catalog-proven STOCK row for these manufacturers - it never
invents a SPH/CYL range, a price, or a product identity, and it never
converts a genuine RX row into Stock, and it never touches a row already
proven "Out Of Egypt".

Also confirmed (store owner): BBGR's and SEIKO's Stock-Egypt total-power
envelope (see reconcile_bbgr/reconcile_seiko), and that DIVEL ITALIA's 6
Sun/Mirror/Polar Stock-Egypt rows are PLANO-ONLY sun products, never
unresolved prescription ranges (see reconcile_divel_sun_plano).

This module is the durable, re-runnable source for that correction (the
project's evidence-module + apply-function pattern already used by
bbgr_addons_evidence.py / seiko_addons_evidence.py / technology_evidence.py),
intentionally NOT routed through crud.confirm_catalog_commercial(), which
closes and replaces a company's ENTIRE current pricing atomically - the
wrong tool for a targeted correction that must leave every other ZEISS /
PLATINUM / SEIKO / BBGR row (RX included) completely untouched.

Idempotent by construction: every write first checks whether the target
state already holds (existing VariantPricing identity, current market_scope)
before touching the DB, so re-running this module against an
already-reconciled database is always a safe no-op.

Evidence sources (already-supplied project PDFs):
  ZEISS_Main_Catalog.pdf   pp.5-6  "ZEISS Finished Single Vision Lenses"
                                    ("Freeform in stock") - prices p.5,
                                    SPH/CYL availability charts p.6.
  PLATINUM.pdf             its own "STOCK LENSES" section - the 16 rows'
                                    prices/ranges were already correctly
                                    imported; this module only reclassifies
                                    their market.
  Seiko_Pricelist_2025.pdf p.2   "STOCK IN EGYPT" - already prints an
                                    explicit Egypt market for its 5 rows
                                    (no change needed here); no SPH/CYL range
                                    is printed anywhere in the 8-page catalog
                                    for them.
  BBGR فرنساوي.pdf         p.2   "Stock lenses" (distinct from "RX S.V") -
                                    7 rows; no SPH/CYL/total-power table is
                                    printed anywhere in the 6-page catalog.
                                    Their range comes instead from a
                                    user/store-owner-confirmed total-power
                                    business rule (-6.00D / +4.00D / max
                                    2.00D CYL, G3 mechanism - see
                                    reconcile_bbgr below); applied ONLY to
                                    these 7 Stock rows, never to BBGR RX.
  Synchrony (imported earlier)   3 of its 5 Stock rows have market_scope
                                    NULL (genuinely unspecified); the other 2
                                    already print "Out Of Egypt" and are
                                    never touched. Prices/ranges/identities
                                    unchanged - only market_scope is set.
  DIVEL ITALIA (imported earlier)  6 of its Stock-Egypt rows (coating name
                                    Sun Lenses/Mirror/Polar, index 1.5) are
                                    confirmed Plano-only sun products - a
                                    SEPARATE business fact from any catalog
                                    range. Never widened beyond exact 0.00/
                                    0.00; never applied to DIVEL's other 7
                                    regular prescription Stock rows.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app import models, crud


@dataclass(frozen=True)
class ZeissFsvRow:
    model_name: str          # "ClearView FSV" | "AS FSV" | "SPH FSV"
    index_value: float
    treatment_band: str
    coating_code: str
    price: Decimal
    sph_min: float
    sph_max: float
    cyl_min: float
    cyl_max: float


# Verified safe-inscribed-rectangle SPH/CYL bounds read directly from
# ZEISS_Main_Catalog.pdf p.6's per-index availability charts (dark/blue
# cells only - the diagonal-cutoff corners are deliberately excluded, never
# rounded outward). Prices read directly from p.5's price tables.
_CLEARVIEW_RANGE = {
    1.5:  (-3.0, 6.0,  -3.0, 0.0),
    1.6:  (-6.0, 0.25, -3.0, 0.0),
    1.67: (-6.0, -0.25, -4.0, 0.0),
    1.74: (-8.0, -2.25, -2.0, 0.0),
}

ZEISS_FSV_ROWS = [
    # Clear / DuraVision Platinum
    ZeissFsvRow("ClearView FSV", 1.5, "Clear", "DuraVision Platinum", Decimal("4320"), *_CLEARVIEW_RANGE[1.5]),
    ZeissFsvRow("ClearView FSV", 1.6, "Clear", "DuraVision Platinum", Decimal("6690"), *_CLEARVIEW_RANGE[1.6]),
    ZeissFsvRow("ClearView FSV", 1.67, "Clear", "DuraVision Platinum", Decimal("9500"), *_CLEARVIEW_RANGE[1.67]),
    ZeissFsvRow("ClearView FSV", 1.74, "Clear", "DuraVision Platinum", Decimal("11190"), *_CLEARVIEW_RANGE[1.74]),
    # Clear / DuraVision Chrome
    ZeissFsvRow("ClearView FSV", 1.5, "Clear", "DuraVision Chrome", Decimal("2320"), *_CLEARVIEW_RANGE[1.5]),
    ZeissFsvRow("ClearView FSV", 1.6, "Clear", "DuraVision Chrome", Decimal("4380"), *_CLEARVIEW_RANGE[1.6]),
    ZeissFsvRow("ClearView FSV", 1.67, "Clear", "DuraVision Chrome", Decimal("6750"), *_CLEARVIEW_RANGE[1.67]),
    ZeissFsvRow("ClearView FSV", 1.74, "Clear", "DuraVision Chrome", Decimal("9820"), *_CLEARVIEW_RANGE[1.74]),
    # BlueGuard / DuraVision Platinum
    ZeissFsvRow("ClearView FSV", 1.5, "BlueGuard", "DuraVision Platinum", Decimal("4940"), *_CLEARVIEW_RANGE[1.5]),
    ZeissFsvRow("ClearView FSV", 1.6, "BlueGuard", "DuraVision Platinum", Decimal("7200"), *_CLEARVIEW_RANGE[1.6]),
    ZeissFsvRow("ClearView FSV", 1.67, "BlueGuard", "DuraVision Platinum", Decimal("10070"), *_CLEARVIEW_RANGE[1.67]),
    ZeissFsvRow("ClearView FSV", 1.74, "BlueGuard", "DuraVision Platinum", Decimal("14440"), *_CLEARVIEW_RANGE[1.74]),
    # PhotoFusion X / DuraVision Platinum (only 1.5, 1.6 offered - 1.67/1.74 print "-")
    ZeissFsvRow("ClearView FSV", 1.5, "PhotoFusion X", "DuraVision Platinum", Decimal("12880"), *_CLEARVIEW_RANGE[1.5]),
    ZeissFsvRow("ClearView FSV", 1.6, "PhotoFusion X", "DuraVision Platinum", Decimal("16190"), *_CLEARVIEW_RANGE[1.6]),
    # PhotoFusion X / DuraVision Chrome (only 1.5 offered - others print "-")
    ZeissFsvRow("ClearView FSV", 1.5, "PhotoFusion X", "DuraVision Chrome", Decimal("11690"), *_CLEARVIEW_RANGE[1.5]),
    # AS FSV / DuraVision DriveSafe (only 1.6, 1.67 offered)
    ZeissFsvRow("AS FSV", 1.6, "Clear", "DuraVision DriveSafe", Decimal("6940"), -6.0, -0.25, -2.0, 0.0),
    ZeissFsvRow("AS FSV", 1.67, "Clear", "DuraVision DriveSafe", Decimal("9820"), -6.0, -2.0, -2.0, 0.0),
    # SPH FSV / DuraVision DriveSafe (only 1.5 offered here - chart verified through -1.50)
    ZeissFsvRow("SPH FSV", 1.5, "Clear", "DuraVision DriveSafe", Decimal("4690"), -4.0, -1.5, -2.0, 0.0),
]


def _get_company(db: Session, name: str) -> models.Company:
    co = db.query(models.Company).filter(models.Company.name == name).one_or_none()
    if co is None:
        raise LookupError(f"company {name!r} not found - P0 reconciliation expects it to "
                           f"already exist from the manufacturer's normal catalog import")
    return co


def _get_or_create_catalog(db: Session, company: models.Company, filename: str) -> models.Catalog:
    cat = (db.query(models.Catalog)
           .filter(models.Catalog.company_id == company.id, models.Catalog.filename == filename)
           .order_by(models.Catalog.id.asc()).first())
    if cat is not None:
        return cat
    cat = models.Catalog(company_id=company.id, filename=filename, file_path=filename,
                          status=models.CatalogStatus.CONFIRMED)
    db.add(cat); db.commit(); db.refresh(cat)
    return cat


def _get_or_create_model(db: Session, company: models.Company, name: str) -> models.LensModel:
    m = (db.query(models.LensModel)
         .filter(models.LensModel.company_id == company.id, models.LensModel.name == name)
         .first())
    if m is not None:
        return m
    m = models.LensModel(company_id=company.id, name=name, category=models.LensCategory.SINGLE_VISION)
    db.add(m); db.commit(); db.refresh(m)
    return m


def _get_or_create_variant(db: Session, model: models.LensModel, index_value: float,
                            treatment_band: str) -> models.LensVariant:
    v = (db.query(models.LensVariant)
         .filter(models.LensVariant.lens_model_id == model.id,
                 models.LensVariant.index_value == index_value,
                 models.LensVariant.material == models.MaterialType.CR39,
                 models.LensVariant.design_type == models.DesignType.SPHERICAL,
                 models.LensVariant.is_aspherical.is_(False),
                 models.LensVariant.treatment_band == treatment_band)
         .first())
    if v is not None:
        return v
    v = models.LensVariant(
        lens_model_id=model.id, material=models.MaterialType.CR39, index_value=index_value,
        design_type=models.DesignType.SPHERICAL, is_aspherical=False,
        treatment_band=treatment_band, price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    return v


def _ensure_stock_pricing(db: Session, variant: models.LensVariant, catalog: models.Catalog,
                           coating: models.Coating, price: Decimal, market_scope: str,
                           range_bounds: Optional[tuple]) -> models.VariantPricing:
    """Idempotent: returns the existing current row for this exact identity
    if one already exists (never a duplicate); otherwise creates it (+ its
    PowerRange, only when range_bounds is given)."""
    existing = (db.query(models.VariantPricing)
                .filter(models.VariantPricing.variant_id == variant.id,
                        models.VariantPricing.coating_id == coating.id,
                        models.VariantPricing.availability == models.PricingAvailability.STOCK,
                        models.VariantPricing.effective_to.is_(None))
                .first())
    if existing is not None:
        if existing.market_scope != market_scope:
            existing.market_scope = market_scope
            db.commit()
        return existing
    vp = models.VariantPricing(
        variant_id=variant.id, coating_id=coating.id,
        availability=models.PricingAvailability.STOCK,
        price_pair=price, currency="EGP", source_catalog_id=catalog.id,
        effective_from=datetime.utcnow(), market_scope=market_scope)
    db.add(vp); db.commit(); db.refresh(vp)
    if range_bounds is not None:
        sph_min, sph_max, cyl_min, cyl_max = range_bounds
        pr = models.PowerRange(lens_model_id=variant.lens_model_id, variant_id=variant.id,
                                pricing_id=vp.id, sph_min=sph_min, sph_max=sph_max,
                                cyl_min=cyl_min, cyl_max=cyl_max)
        db.add(pr); db.commit()
    return vp


def reconcile_zeiss(db: Session) -> int:
    """Create (idempotently) the 18 ZEISS Finished-SV Stock Egypt rows.
    Never touches any existing ZEISS RX row."""
    company = _get_company(db, "ZEISS")
    catalog = _get_or_create_catalog(db, company, "ZEISS_Main_Catalog.pdf")
    written = 0
    for row in ZEISS_FSV_ROWS:
        model = _get_or_create_model(db, company, row.model_name)
        variant = _get_or_create_variant(db, model, row.index_value, row.treatment_band)
        coating = crud.get_or_create_coating(db, row.coating_code, name=row.coating_code)
        before = (db.query(models.VariantPricing)
                  .filter(models.VariantPricing.variant_id == variant.id,
                          models.VariantPricing.coating_id == coating.id,
                          models.VariantPricing.availability == models.PricingAvailability.STOCK,
                          models.VariantPricing.effective_to.is_(None)).first())
        _ensure_stock_pricing(db, variant, catalog, coating, row.price, "Egypt",
                               (row.sph_min, row.sph_max, row.cyl_min, row.cyl_max))
        if before is None:
            written += 1
    return written


def reconcile_platinum(db: Session) -> int:
    """Reclassify PLATINUM's existing 16 proven Stock rows to market_scope
    "Egypt" - their price and PowerRange (already correctly imported from
    PLATINUM.pdf's own "STOCK LENSES" section) are read, never rewritten."""
    company = _get_company(db, "PLATINUM")
    rows = (db.query(models.VariantPricing)
            .join(models.LensVariant, models.LensVariant.id == models.VariantPricing.variant_id)
            .join(models.LensModel, models.LensModel.id == models.LensVariant.lens_model_id)
            .filter(models.LensModel.company_id == company.id,
                    models.VariantPricing.availability == models.PricingAvailability.STOCK,
                    models.VariantPricing.effective_to.is_(None))
            .all())
    changed = 0
    for r in rows:
        if r.market_scope != "Egypt":
            r.market_scope = "Egypt"
            changed += 1
    if changed:
        db.commit()
    return len(rows)


# BBGR Stock total-power business rule (user/store-owner confirmed, not a
# catalog-printed number - the 6-page catalog itself prints no SPH/CYL/total-
# power table anywhere for these 7 rows, Stock or RX; this is the SAME kind
# of explicit domain confirmation PLATINUM's own G3 rows already rely on).
# Applies ONLY to the 7 existing BBGR STOCK rows, never to any BBGR RX S.V.
# row. Total minus power limit -6.00D, total plus power limit +4.00D, max
# cylinder magnitude 2.00D - evaluated via the project's existing G3
# authoritative total-power/meridian mechanism (total_power_min/
# total_power_max/max_cyl_abs in lens_matcher._check_form_against_range),
# NEVER as a naive "SPH -6.00..+4.00" box: both principal meridians
# {SPH, SPH+CYL} must fall within [-6.00, +4.00], and abs(CYL) <= 2.00. The
# sph/cyl fields below are only the coarse prefilter box (the true outer
# envelope any valid meridian pair can reach) - the G3 fields are what
# actually decide eligibility.
_BBGR_STOCK_TOTAL_POWER_MIN = -6.0
_BBGR_STOCK_TOTAL_POWER_MAX = 4.0
_BBGR_STOCK_MAX_CYL_ABS = 2.0


def reconcile_bbgr(db: Session) -> int:
    """Reclassify BBGR's existing 7 proven Stock rows ('Stock lenses', p.2 -
    structurally distinct from 'RX S.V') to market_scope "Egypt", and attach
    the confirmed total-power G3 range (see _BBGR_STOCK_* above) to each -
    never touching any BBGR RX row. Idempotent: a row that already has a
    PowerRange is left alone."""
    company = _get_company(db, "BBGR")
    rows = (db.query(models.VariantPricing)
            .join(models.LensVariant, models.LensVariant.id == models.VariantPricing.variant_id)
            .join(models.LensModel, models.LensModel.id == models.LensVariant.lens_model_id)
            .filter(models.LensModel.company_id == company.id,
                    models.VariantPricing.availability == models.PricingAvailability.STOCK,
                    models.VariantPricing.effective_to.is_(None))
            .all())
    changed = 0
    for r in rows:
        if r.market_scope != "Egypt":
            r.market_scope = "Egypt"
            changed += 1
        if not list(r.power_ranges):
            pr = models.PowerRange(
                lens_model_id=r.variant.lens_model_id, variant_id=r.variant_id, pricing_id=r.id,
                sph_min=_BBGR_STOCK_TOTAL_POWER_MIN, sph_max=_BBGR_STOCK_TOTAL_POWER_MAX,
                cyl_min=-_BBGR_STOCK_MAX_CYL_ABS, cyl_max=0.0,
                total_power_min=_BBGR_STOCK_TOTAL_POWER_MIN,
                total_power_max=_BBGR_STOCK_TOTAL_POWER_MAX,
                max_cyl_abs=_BBGR_STOCK_MAX_CYL_ABS)
            db.add(pr)
            changed += 1
    if changed:
        db.commit()
    return len(rows)


# SEIKO Stock-in-Egypt total-power business rule (user/store-owner
# confirmed, not a catalog-printed number - Seiko_Pricelist_2025.pdf prints
# no SPH/CYL/total-power table anywhere for any identity). Applies ONLY to
# the 5 existing SEIKO "STOCK IN EGYPT" rows - never to SEIKO's Stock OOE
# rows, RX rows, or Freeform SV products (all excluded by construction: the
# query below filters on availability=STOCK AND market_scope=="Egypt").
_SEIKO_EGYPT_TOTAL_POWER_MIN = -6.0
_SEIKO_EGYPT_TOTAL_POWER_MAX = 4.0
_SEIKO_EGYPT_MAX_CYL_ABS = 2.0


def reconcile_seiko(db: Session) -> int:
    """SEIKO's 5 'STOCK IN EGYPT' rows (Seiko_Pricelist_2025.pdf p.2) already
    print an explicit Egypt market and were already correctly imported - this
    function never touches market_scope. It attaches the confirmed
    total-power G3 range (see _SEIKO_EGYPT_* above) to each of the 5, using
    the project's existing G3 total-power/meridian mechanism - never a naive
    SPH -6.00..+4.00 box. Idempotent: a row that already has a PowerRange is
    left alone."""
    company = _get_company(db, "SEIKO")
    rows = (db.query(models.VariantPricing)
            .join(models.LensVariant, models.LensVariant.id == models.VariantPricing.variant_id)
            .join(models.LensModel, models.LensModel.id == models.LensVariant.lens_model_id)
            .filter(models.LensModel.company_id == company.id,
                    models.VariantPricing.availability == models.PricingAvailability.STOCK,
                    models.VariantPricing.market_scope == "Egypt",
                    models.VariantPricing.effective_to.is_(None))
            .all())
    changed = 0
    for r in rows:
        if not list(r.power_ranges):
            pr = models.PowerRange(
                lens_model_id=r.variant.lens_model_id, variant_id=r.variant_id, pricing_id=r.id,
                sph_min=_SEIKO_EGYPT_TOTAL_POWER_MIN, sph_max=_SEIKO_EGYPT_TOTAL_POWER_MAX,
                cyl_min=-_SEIKO_EGYPT_MAX_CYL_ABS, cyl_max=0.0,
                total_power_min=_SEIKO_EGYPT_TOTAL_POWER_MIN,
                total_power_max=_SEIKO_EGYPT_TOTAL_POWER_MAX,
                max_cyl_abs=_SEIKO_EGYPT_MAX_CYL_ABS)
            db.add(pr)
            changed += 1
    if changed:
        db.commit()
    return len(rows)


def reconcile_synchrony(db: Session) -> int:
    """Reclassify Synchrony's 3 Stock rows whose market is genuinely
    unspecified in the catalog (market_scope NULL) to market_scope "Egypt"
    (confirmed store-owner business fact: this Stock IS physically inside
    Egypt). Never touches the 2 existing Synchrony Stock rows already marked
    "Out Of Egypt", never touches price/PowerRange/identity, never touches
    any Synchrony RX row (excluded by construction: availability=STOCK
    only)."""
    company = _get_company(db, "Synchrony")
    rows = (db.query(models.VariantPricing)
            .join(models.LensVariant, models.LensVariant.id == models.VariantPricing.variant_id)
            .join(models.LensModel, models.LensModel.id == models.LensVariant.lens_model_id)
            .filter(models.LensModel.company_id == company.id,
                    models.VariantPricing.availability == models.PricingAvailability.STOCK,
                    models.VariantPricing.market_scope.is_(None),
                    models.VariantPricing.effective_to.is_(None))
            .all())
    changed = 0
    for r in rows:
        r.market_scope = "Egypt"
        changed += 1
    if changed:
        db.commit()
    return changed


# DIVEL ITALIA's 6 Sun/Mirror/Polar Stock-Egypt rows (color_variant Sun
# Lenses/Mirror/Polar at index 1.5) are confirmed PLANO-ONLY sun products
# (user/store-owner confirmed) - never an unresolved prescription range.
# SPH=0.00 exactly, CYL=0.00 exactly; never widened to any non-zero value.
_DIVEL_SUN_COLOR_VARIANTS = frozenset({
    "Gray/Brown/G15/Blue", "Gray/Brown/G15", "Red/R.Gold", "Blue/Silver",
    "Gray/Brown/G15/Purple",
})
_DIVEL_SUN_COATING_NAMES = frozenset({"Sun Lenses", "Mirror", "Polar"})


def reconcile_divel_sun_plano(db: Session) -> int:
    """Attach an exact zero-tolerance Plano-only PowerRange to DIVEL ITALIA's
    Stock-Egypt Sun/Mirror/Polar rows - identified structurally by their
    coating name being one of Sun Lenses/Mirror/Polar, never by row id.
    sph_min=sph_max=cyl_min=cyl_max=0.0 AND total_power_min=total_power_max=
    max_cyl_abs=0.0 (the SAME "EXACT zero-tolerance plano-only match"
    pattern already used for PLATINUM's "BASE 2-4-8"/"POLARIZED" rows -
    setting the G3 fields too, not just the coarse box, so this is never
    left to any fuzzy +-0.25 coarse-box tolerance elsewhere in the matcher).
    Never touches DIVEL's other 7 regular prescription Stock rows (different
    coatings entirely), never touches price, never converts anything to RX.
    Idempotent: a row that already has a PowerRange is left alone."""
    company = _get_company(db, "DIVEL ITALIA")
    rows = (db.query(models.VariantPricing)
            .join(models.LensVariant, models.LensVariant.id == models.VariantPricing.variant_id)
            .join(models.LensModel, models.LensModel.id == models.LensVariant.lens_model_id)
            .join(models.Coating, models.Coating.id == models.VariantPricing.coating_id)
            .filter(models.LensModel.company_id == company.id,
                    models.VariantPricing.availability == models.PricingAvailability.STOCK,
                    models.VariantPricing.market_scope == "Egypt",
                    models.Coating.name.in_(_DIVEL_SUN_COATING_NAMES),
                    models.VariantPricing.effective_to.is_(None))
            .all())
    changed = 0
    for r in rows:
        if not list(r.power_ranges):
            pr = models.PowerRange(
                lens_model_id=r.variant.lens_model_id, variant_id=r.variant_id, pricing_id=r.id,
                sph_min=0.0, sph_max=0.0, cyl_min=0.0, cyl_max=0.0,
                total_power_min=0.0, total_power_max=0.0, max_cyl_abs=0.0)
            db.add(pr)
            changed += 1
    if changed:
        db.commit()
    return len(rows)


def reconcile(db: Session) -> dict:
    """Apply the full P0 Stock-Egypt correction. Idempotent - safe to call
    against an already-reconciled database (every step is a no-op then)."""
    return {
        "zeiss_new_rows": reconcile_zeiss(db),
        "platinum_stock_total": reconcile_platinum(db),
        "bbgr_stock_total": reconcile_bbgr(db),
        "seiko_egypt_total": reconcile_seiko(db),
        "synchrony_egypt_changed": reconcile_synchrony(db),
        "divel_sun_plano_total": reconcile_divel_sun_plano(db),
    }


if __name__ == "__main__":
    import os
    import sys

    BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if BACKEND_DIR not in sys.path:
        sys.path.insert(0, BACKEND_DIR)

    db_url = os.environ.get("DATABASE_URL", "sqlite:///./v12_dev.db")
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from app import database

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    if db_url.startswith("sqlite"):
        event.listen(engine, "connect", database._set_sqlite_pragma)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        result = reconcile(session)
        for k, v in result.items():
            print(f"{k}: {v}")
        print("variant_pricing_total:", session.query(models.VariantPricing).count())
    finally:
        session.close()
