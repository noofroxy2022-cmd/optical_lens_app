"""ZEISS Office Lenses ingestion (Special Lenses architecture, owner-
confirmed 2026-09-19/20/21).

Evidence: ZEISS_Main_Catalog.pdf pp.33-34 ("ZEISS Office Lenses"), extracted
by exact word-position (pdfplumber `extract_words`, not raw `extract_text` -
this catalog has a known duplicate/offset text-rendering artifact on some
pages, already documented in app/zeiss_svrx_graphical_evidence.py, and a
position-based re-verification pass caught it here too before any number
was trusted).

Commercial identity: THREE design tiers - Individual (nasal engraving
`OIxx`), Superb (`OSxx`), Plus (`OPxx`) - each repeating the same 4
treatment bands (Clear, BlueGuard, PhotoFusion X, Tinted). All 10 catalog
rows across the whole page are RX (owner-confirmed 2026-09-21: "ZEISS
Office Lenses = Manufacturing / RX" - no catalog page anywhere prints an
FSV/Stock/order-type word for Office; market_scope stays None, matching the
existing, unmodified ClearMind/ClearView RX/SPH RX precedent).

Modeled as ONE LensModel ("Office", category=OFFICE) with `design_tier`
distinguishing Individual/Superb/Plus - the exact field this schema already
reserves for "a commercial TIER within one family" (see models.py's own
ClearMind Individual/Superb example) - never three separate LensModels.

Material: 1.53 resolves to TRIVEX automatically via the existing
`catalog_corrections._corrected_material`/`_TRIVEX_1_53_COMPANIES` rule
(ZEISS is already in that set); every other index is CR39. No new material
code needed here.

Price cells: 1.53 IS priced for Clear and BlueGuard (every tier), but NEVER
for PhotoFusion X or Tinted (dashed in the source on every tier) - not a
transcription simplification, confirmed cell-by-cell from exact word
positions. 1.74 is additionally dashed for PhotoFusion X "Flash" and for
every Tinted coating, on every tier. No dashed cell is ever created here.

Power range ("Power range: Office Lenses", printed ONCE, shared identically
across all 3 tiers - never a per-tier chart): each index resolves to G3
`total_power_min`/`total_power_max`/`max_cyl_abs` bands, one row per printed
diameter zone (diameter recorded only in `notes`, never an enforced gate -
same precedent as ClearView RX / ZEISS MyoCare):

  1.74: "75/80E-70/75E" -> (-10.00, +6.00, cyl 4.00)
        "65/70E-55/60E" -> (-14.00, +9.00, cyl 6.00)
  1.67: "75/80E"        -> (-10.00, +6.00, cyl 4.00)
        "70/75E"        -> (-10.00, +8.00, cyl 4.00)
        "65/70E-55/60E" -> (-12.00, +8.00, cyl 6.00)
  1.6:  "75/80E"        -> ( -5.00, +6.00, cyl 4.00)
        "70/75E-55/60E" -> (-10.00, +6.00, cyl 6.00)
  1.53 (Trivex):
        "75/80"         -> ( -3.00, +5.00, cyl 4.00)
        "70/75"         -> ( -4.00, +5.00, cyl 4.00)
        "65/70-55/60"   -> ( -7.00, +5.00, cyl 4.00)
  1.5:  "75/80E"        -> ( -6.00, +4.00, cyl 4.00)
        "70/75E-55/60E" -> ( -7.00, +5.00, cyl 4.00)

ADD (owner-confirmed 2026-09-21, ZEISS Office is ADD-aware - see
app/product_search.py's `_check_range_with_add_policy`): every index prints
its own "Add X-Y dpt" caption directly under its power-range bars. FOUR of
the five indexes print "Add 0.75-3.50 dpt" - but 1.6 explicitly prints
"Add 0.75-4.00 dpt", a genuinely different upper bound, confirmed by exact
word position (not a misread of "3.50"). This module preserves that exact
per-index difference rather than forcing a single project-wide constant -
never fabricating a rounder number the catalog does not print.

Not routed through crud.confirm_catalog_commercial() - same rationale as
zeiss_myopia_control_evidence.py / p0_stock_egypt_evidence.py: this creates
new products while leaving every other ZEISS row (RX and Stock alike)
untouched, which that entry point cannot guarantee. Idempotent by
construction: every write checks the exact target identity before creating
anything, so re-running this module is always a safe no-op.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app import crud, models

MODEL_NAME = "Office"
SOURCE_CATALOG_FILENAME = "ZEISS_Main_Catalog.pdf"

TIERS = ("Individual", "Superb", "Plus")
_TIER_ENGRAVING = {"Individual": "OIxx", "Superb": "OSxx", "Plus": "OPxx"}  # documentation only


@dataclass(frozen=True)
class PowerZone:
    diameter_zone: str
    total_power_min: float
    total_power_max: float
    max_cyl_abs: float


@dataclass(frozen=True)
class AddRange:
    add_min: float
    add_max: float


# Index -> printed diameter-zone bands (shared identically across all 3 tiers).
POWER_ZONES: Dict[float, List[PowerZone]] = {
    1.74: [
        PowerZone("75/80E-70/75E", -10.00, 6.00, 4.00),
        PowerZone("65/70E-55/60E", -14.00, 9.00, 6.00),
    ],
    1.67: [
        PowerZone("75/80E", -10.00, 6.00, 4.00),
        PowerZone("70/75E", -10.00, 8.00, 4.00),
        PowerZone("65/70E-55/60E", -12.00, 8.00, 6.00),
    ],
    1.6: [
        PowerZone("75/80E", -5.00, 6.00, 4.00),
        PowerZone("70/75E-55/60E", -10.00, 6.00, 6.00),
    ],
    1.53: [
        PowerZone("75/80", -3.00, 5.00, 4.00),
        PowerZone("70/75", -4.00, 5.00, 4.00),
        PowerZone("65/70-55/60", -7.00, 5.00, 4.00),
    ],
    1.5: [
        PowerZone("75/80E", -6.00, 4.00, 4.00),
        PowerZone("70/75E-55/60E", -7.00, 5.00, 4.00),
    ],
}

# Index -> printed ADD range. 1.6 is genuinely different (0.75-4.00), not a
# typo - confirmed by exact word position, never overwritten with the more
# common 0.75-3.50 value the other four indexes print.
ADD_RANGES: Dict[float, AddRange] = {
    1.74: AddRange(0.75, 3.50),
    1.67: AddRange(0.75, 3.50),
    1.6: AddRange(0.75, 4.00),
    1.53: AddRange(0.75, 3.50),
    1.5: AddRange(0.75, 3.50),
}

# (tier, treatment_band, coating_code) -> {index_value: price}. Every value
# below is copied verbatim from the exact word-position extraction of
# ZEISS_Main_Catalog.pdf p.33 (Individual, Superb) and p.34 (Plus). Absent
# key == dashed cell in the source - never fabricated.
_IDX = (1.5, 1.53, 1.6, 1.67, 1.74)


def _prices(*values: Optional[int]) -> Dict[float, Decimal]:
    return {idx: Decimal(str(v)) for idx, v in zip(_IDX, values) if v is not None}


PRICES: Dict[tuple, Dict[float, Decimal]] = {
    # ---------------------------------------------------------- Individual
    ("Individual", "Clear", "DuraVision Plus Gold"): _prices(14900, 18800, 18800, 22800, 26600),
    ("Individual", "Clear", "DuraVision Plus Platinum"): _prices(14400, 18400, 18400, 22400, 26100),
    ("Individual", "Clear", "DuraVision Plus Chrome"): _prices(13900, 17900, 17900, 21900, 25700),
    ("Individual", "BlueGuard", "DuraVision Plus Gold"): _prices(16100, 20100, 20100, 24100, 27800),
    ("Individual", "BlueGuard", "DuraVision Plus Platinum"): _prices(15600, 19600, 19600, 23500, 27300),
    ("Individual", "PhotoFusion X", "DuraVision Plus Gold"): _prices(21900, None, 25900, 29900, 33700),
    ("Individual", "PhotoFusion X", "DuraVision Plus Platinum"): _prices(21400, None, 25400, 29400, 33200),
    ("Individual", "PhotoFusion X", "DuraVision Plus Chrome"): _prices(21100, None, 25100, 29100, 32700),
    ("Individual", "PhotoFusion X", "DuraVision Plus Flash"): _prices(21500, None, 25500, 29500, None),
    ("Individual", "Tinted", "DuraVision Plus Gold"): _prices(14800, None, 18800, 22600, None),
    ("Individual", "Tinted", "DuraVision Plus Platinum"): _prices(14600, None, 18600, 22400, None),
    ("Individual", "Tinted", "DuraVision Plus Chrome"): _prices(14400, None, 18400, 22200, None),
    ("Individual", "Tinted", "DuraVision Plus Sun"): _prices(14200, None, 18200, 22100, None),
    ("Individual", "Tinted", "DuraVision Plus Flash"): _prices(15100, None, 19100, 23100, None),
    # ---------------------------------------------------------------- Superb
    ("Superb", "Clear", "DuraVision Plus Gold"): _prices(12500, 16500, 16500, 20500, 24300),
    ("Superb", "Clear", "DuraVision Plus Platinum"): _prices(12100, 16100, 16100, 20100, 23800),
    ("Superb", "Clear", "DuraVision Plus Chrome"): _prices(11600, 15600, 15600, 19600, 23300),
    ("Superb", "BlueGuard", "DuraVision Plus Gold"): _prices(13700, 17700, 17700, 21700, 25400),
    ("Superb", "BlueGuard", "DuraVision Plus Platinum"): _prices(13200, 17200, 17200, 21200, 25100),
    ("Superb", "PhotoFusion X", "DuraVision Plus Gold"): _prices(20500, None, 24500, 27500, 31300),
    ("Superb", "PhotoFusion X", "DuraVision Plus Platinum"): _prices(20100, None, 24100, 27100, 30800),
    ("Superb", "PhotoFusion X", "DuraVision Plus Chrome"): _prices(19600, None, 23500, 26600, 30400),
    ("Superb", "PhotoFusion X", "DuraVision Plus Flash"): _prices(21100, None, 25100, 28100, None),
    ("Superb", "Tinted", "DuraVision Plus Gold"): _prices(12500, None, 16500, 20500, None),
    ("Superb", "Tinted", "DuraVision Plus Platinum"): _prices(12300, None, 16300, 20300, None),
    ("Superb", "Tinted", "DuraVision Plus Chrome"): _prices(12100, None, 16100, 20100, None),
    ("Superb", "Tinted", "DuraVision Plus Sun"): _prices(11800, None, 15800, 19800, None),
    ("Superb", "Tinted", "DuraVision Plus Flash"): _prices(13100, None, 17100, 21100, None),
    # ------------------------------------------------------------------ Plus
    ("Plus", "Clear", "DuraVision Plus Gold"): _prices(10200, 14100, 14100, 18100, 21900),
    ("Plus", "Clear", "DuraVision Plus Platinum"): _prices(9700, 13700, 13700, 17700, 21400),
    ("Plus", "Clear", "DuraVision Plus Chrome"): _prices(9200, 13200, 13200, 17200, 21100),
    ("Plus", "BlueGuard", "DuraVision Plus Gold"): _prices(11300, 15300, 15300, 19300, 23100),
    ("Plus", "BlueGuard", "DuraVision Plus Platinum"): _prices(10900, 14900, 14900, 18800, 22600),
    ("Plus", "PhotoFusion X", "DuraVision Plus Gold"): _prices(18100, None, 22100, 25200, 29100),
    ("Plus", "PhotoFusion X", "DuraVision Plus Platinum"): _prices(17700, None, 21700, 24700, 28500),
    ("Plus", "PhotoFusion X", "DuraVision Plus Chrome"): _prices(17200, None, 21200, 24300, 28100),
    ("Plus", "PhotoFusion X", "DuraVision Plus Flash"): _prices(18500, None, 22500, 25500, None),
    ("Plus", "Tinted", "DuraVision Plus Gold"): _prices(10100, None, 14100, 18100, None),
    ("Plus", "Tinted", "DuraVision Plus Platinum"): _prices(9800, None, 13800, 17800, None),
    ("Plus", "Tinted", "DuraVision Plus Chrome"): _prices(9600, None, 13600, 17600, None),
    ("Plus", "Tinted", "DuraVision Plus Sun"): _prices(9400, None, 13400, 17400, None),
    ("Plus", "Tinted", "DuraVision Plus Flash"): _prices(11100, None, 15100, 19100, None),
}


def _get_company(db: Session, name: str) -> models.Company:
    co = db.query(models.Company).filter(models.Company.name == name).one_or_none()
    if co is None:
        raise LookupError(f"company {name!r} not found - Office ingestion expects the ZEISS "
                           f"company row to already exist")
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
    m = models.LensModel(company_id=company.id, name=name, category=models.LensCategory.OFFICE)
    db.add(m); db.commit(); db.refresh(m)
    return m


def _get_or_create_variant(db: Session, model: models.LensModel, index_value: float,
                            design_tier: str, treatment_band: str) -> models.LensVariant:
    v = (db.query(models.LensVariant)
         .filter(models.LensVariant.lens_model_id == model.id,
                 models.LensVariant.index_value == index_value,
                 models.LensVariant.design_tier == design_tier,
                 models.LensVariant.treatment_band == treatment_band)
         .first())
    if v is not None:
        return v
    material = models.MaterialType.CR39
    is_asph = False
    design_type_enum = models.DesignType.SPHERICAL
    material, design_type_enum, is_asph = _apply_material_correction(index_value, material, design_type_enum, is_asph)
    v = models.LensVariant(
        lens_model_id=model.id, material=material, index_value=index_value,
        design_type=design_type_enum, is_aspherical=is_asph,
        design_tier=design_tier, treatment_band=treatment_band, price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    return v


def _apply_material_correction(index_value, material_enum, design_type_enum, is_asph):
    """Reuses the existing, already-proven ZEISS 1.53=Trivex correction
    (catalog_corrections._TRIVEX_1_53_COMPANIES already includes ZEISS) -
    no new material rule invented here."""
    from app import catalog_corrections
    material_enum, design_type_enum, is_asph = catalog_corrections.corrected_identity(
        company_name="ZEISS", model_name=MODEL_NAME, category=models.LensCategory.OFFICE.value,
        index_value=index_value, design_variant=None,
        material_enum=material_enum, design_type_enum=design_type_enum, is_asph=is_asph)
    return material_enum, design_type_enum, is_asph


def _ensure_pricing(db: Session, variant: models.LensVariant, catalog: models.Catalog,
                     coating: models.Coating, price: Decimal, zones: List[PowerZone],
                     add_range: AddRange) -> bool:
    """Idempotent: False (no-op) if this exact (variant, coating, RX) current
    row already exists; otherwise creates it plus one PowerRange row per
    diameter zone, every zone carrying the same catalog-printed ADD range."""
    existing = (db.query(models.VariantPricing)
                .filter(models.VariantPricing.variant_id == variant.id,
                        models.VariantPricing.coating_id == coating.id,
                        models.VariantPricing.availability == models.PricingAvailability.RX,
                        models.VariantPricing.effective_to.is_(None))
                .first())
    if existing is not None:
        return False
    vp = models.VariantPricing(
        variant_id=variant.id, coating_id=coating.id, availability=models.PricingAvailability.RX,
        price_pair=price, currency="EGP", source_catalog_id=catalog.id,
        effective_from=datetime.utcnow(), market_scope=None,
        power_eligibility=models.PowerEligibilityStatus.UNRESTRICTED)
    db.add(vp); db.commit(); db.refresh(vp)
    for zone in zones:
        pr = models.PowerRange(
            lens_model_id=variant.lens_model_id, variant_id=variant.id, pricing_id=vp.id,
            sph_min=zone.total_power_min, sph_max=zone.total_power_max,
            cyl_min=-zone.max_cyl_abs, cyl_max=0.0,
            total_power_min=zone.total_power_min, total_power_max=zone.total_power_max,
            max_cyl_abs=zone.max_cyl_abs, add_min=add_range.add_min, add_max=add_range.add_max,
            notes=f"diameter_mm={zone.diameter_zone} | source=ZEISS_Main_Catalog.pdf pp.33-34 "
                  f"\"Power range: Office Lenses\"")
        db.add(pr)
    db.commit()
    return True


def reconcile(db: Session) -> Dict[str, int]:
    """Idempotently creates ZEISS Office (Individual/Superb/Plus). Never
    touches any other ZEISS model. Returns the count of newly-created
    VariantPricing rows; a second call always returns 0."""
    company = _get_company(db, "ZEISS")
    catalog = _get_or_create_catalog(db, company, SOURCE_CATALOG_FILENAME)
    model = _get_or_create_model(db, company, MODEL_NAME)
    created = 0
    for (tier, treatment_band, coating_code), prices_by_index in PRICES.items():
        coating = crud.get_or_create_coating(db, coating_code, name=coating_code)
        for index_value, price in prices_by_index.items():
            variant = _get_or_create_variant(db, model, index_value, tier, treatment_band)
            zones = POWER_ZONES[index_value]
            add_range = ADD_RANGES[index_value]
            if _ensure_pricing(db, variant, catalog, coating, price, zones, add_range):
                created += 1
    return {"created": created}
