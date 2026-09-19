"""ZEISS MyoCare / MyoCare S ingestion (Special Lenses architecture,
owner-confirmed, 2026-09-19/20).

Evidence source: ZEISS_Main_Catalog.pdf pp.51-52 ("ZEISS MyoCare Lenses").
Second-pass vector-rect extraction (same two-method standard as
app/zeiss_svrx_graphical_evidence.py: pdfplumber rect fill-color + extent,
cross-checked against a rendered-crop visual read) proved every number
below directly from the printed graphical SPH/CYL charts - none estimated,
none rounded from a visual guess.

Product identity: MyoCare (C.A.R.E., central zone 7mm, defocus +4.6D) and
MyoCare S (C.A.R.E., central zone 9mm, defocus +3.8D) are catalog-proven
DISTINCT optical designs, ingested as two separate LensModel rows. Their
commercial price and Power Range tables are, as printed, IDENTICAL between
the two products (every chart/table on the page is captioned "MyoCare/
MyoCare S" with no per-product split) - this module deliberately mirrors
that fact rather than inventing a difference, and deliberately preserves the
identity split rather than collapsing them into one row.

Both map to the SAME generic functional subtype - models.LensCategory.
MYOPIA_CONTROL / use_mode="myopia_control" - never a product-specific
category. This is the second manufacturer under that one category (after
SCOPE Myoblock/Metavision); a future manufacturer's proven myopia-control
product is one more model here, never a new category.

RX vs Stock (owner-confirmed, 2026-09-20): "ZEISS RX lenses are RX /
Manufacturing, NOT Stock." The "ZEISS Stock is physically in Egypt"
business fact (app/p0_stock_egypt_evidence.py) applies ONLY to the printed
Stock/FSV form (index 1.59, DuraVision Platinum, 73mm) - market_scope=
"Egypt" - and is NEVER extended to any RX row. Every RX row here uses
market_scope=None, matching the existing, unmodified precedent already set
by ClearMind / ClearView RX / SPH RX (crud.py's own market_scope default
when no catalog/reviewer value is entered - not a fabricated rule).

RX Power Range (G3 total_power_min / max_cyl_abs, the same mechanism
ClearView RX/ClearMind already use on this exact catalog): diameter is
recorded as evidence only (PowerRange.notes), never a new eligibility gate -
consistent with the owner's explicit rule that catalog age/fitting/diameter
facts stay documentation, never a search gate the app enforces itself.

  index 1.50: diameter 70mm only -> total_power_min=-6.00, max_cyl_abs=4.00
  index 1.59 and 1.60 (identical, per the combined chart - see
    app/zeiss_myopia_control_evidence.py's own extraction notes):
      65mm       -> total_power_min=-9.00
      65mm,70mm  -> total_power_min=-7.00
      65,70,73mm -> total_power_min=-6.00
    (max_cyl_abs=6.00 for all three)
  index 1.67:
      65mm       -> total_power_min=-10.00
      65mm,70mm  -> total_power_min=-9.00
      65,70,73mm -> total_power_min=-8.00
    (max_cyl_abs=6.00 for all three)

No total_power_max is set anywhere - the catalog prints no plus-side cap on
any MyoCare/MyoCare S chart, and none is invented here (same "leave it
unset" precedent PLATINUM's own plus-only G3 rows already use).

Stock/FSV: index 1.59, diameter 73mm, total_power_min=-6.00, max_cyl_abs=
2.00, DuraVision Platinum @ 7800, market_scope="Egypt" (the existing,
already-proven ZEISS Stock-Egypt business fact, extended here by one new
named row - never silently inherited).

MyoActive is deliberately NOT included in this module. It is proven
Myopia Management but (a) not yet ingestable - its own catalog page prints
"Available from 1st October 2026", after this project's current date, and
(b) its own power-range chart is combined with MyoCare/MyoCare S RX 1.59/
1.60 with no per-product split proven separately. A future module/entry
handles it once both conditions clear - never a placeholder/inactive row
here.

Not routed through crud.confirm_catalog_commercial() - same rationale as
p0_stock_egypt_evidence.py: that entry point replaces a company's ENTIRE
current pricing atomically, the wrong tool for adding two new products
while leaving every other ZEISS row (RX and Stock alike) untouched.
Idempotent by construction: every write checks the exact target identity
before creating anything, so re-running this module is always a safe no-op.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app import crud, models

PRODUCT_NAMES = ("MyoCare", "MyoCare S")

SOURCE_CATALOG_FILENAME = "ZEISS_Main_Catalog.pdf"


@dataclass(frozen=True)
class RxBand:
    index_value: float
    diameter_zone: str
    sph_min: float
    sph_max: float
    cyl_min: float
    cyl_max: float
    total_power_min: float
    max_cyl_abs: float


_RX_BANDS: List[RxBand] = [
    RxBand(1.50, "70", -6.00, 0.00, -4.00, 0.00, -6.00, 4.00),
    RxBand(1.59, "65", -9.00, 0.00, -6.00, 0.00, -9.00, 6.00),
    RxBand(1.59, "65,70", -9.00, 0.00, -6.00, 0.00, -7.00, 6.00),
    RxBand(1.59, "65,70,73", -9.00, 0.00, -6.00, 0.00, -6.00, 6.00),
    RxBand(1.60, "65", -9.00, 0.00, -6.00, 0.00, -9.00, 6.00),
    RxBand(1.60, "65,70", -9.00, 0.00, -6.00, 0.00, -7.00, 6.00),
    RxBand(1.60, "65,70,73", -9.00, 0.00, -6.00, 0.00, -6.00, 6.00),
    RxBand(1.67, "65", -10.00, -2.00, -6.00, 0.00, -10.00, 6.00),
    RxBand(1.67, "65,70", -10.00, -2.00, -6.00, 0.00, -9.00, 6.00),
    RxBand(1.67, "65,70,73", -10.00, -2.00, -6.00, 0.00, -8.00, 6.00),
]

_STOCK_BAND = RxBand(1.59, "73", -6.00, 0.00, -2.00, 0.00, -6.00, 2.00)

RX_PRICES: Dict[str, Dict[float, Decimal]] = {
    "DuraVision Plus Platinum": {1.50: Decimal("9700"), 1.59: Decimal("13700"),
                                  1.60: Decimal("13700"), 1.67: Decimal("17700")},
    "DuraVision Kids": {1.50: Decimal("9200"), 1.59: Decimal("13200"),
                         1.60: Decimal("13200"), 1.67: Decimal("17200")},
}
STOCK_COATING = "DuraVision Platinum"
STOCK_PRICE = Decimal("7800")


def _get_company(db: Session, name: str) -> models.Company:
    co = db.query(models.Company).filter(models.Company.name == name).one_or_none()
    if co is None:
        raise LookupError(f"company {name!r} not found - MyoCare/MyoCare S ingestion expects "
                           f"the ZEISS company row to already exist")
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
    m = models.LensModel(company_id=company.id, name=name, category=models.LensCategory.MYOPIA_CONTROL)
    db.add(m); db.commit(); db.refresh(m)
    return m


def _get_or_create_variant(db: Session, model: models.LensModel, index_value: float) -> models.LensVariant:
    v = (db.query(models.LensVariant)
         .filter(models.LensVariant.lens_model_id == model.id,
                 models.LensVariant.index_value == index_value,
                 models.LensVariant.material == models.MaterialType.CR39,
                 models.LensVariant.design_type == models.DesignType.SPHERICAL,
                 models.LensVariant.is_aspherical.is_(False))
         .first())
    if v is not None:
        return v
    v = models.LensVariant(
        lens_model_id=model.id, material=models.MaterialType.CR39, index_value=index_value,
        design_type=models.DesignType.SPHERICAL, is_aspherical=False, price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    return v


def _ensure_pricing(db: Session, variant: models.LensVariant, catalog: models.Catalog,
                     coating: models.Coating, availability: models.PricingAvailability,
                     price: Decimal, market_scope: Optional[str],
                     bands: List[RxBand]) -> bool:
    """Idempotent: returns False (no-op) if this exact (variant, coating,
    availability) current row already exists; otherwise creates it plus one
    PowerRange row per band. Never duplicates, never overwrites a price."""
    existing = (db.query(models.VariantPricing)
                .filter(models.VariantPricing.variant_id == variant.id,
                        models.VariantPricing.coating_id == coating.id,
                        models.VariantPricing.availability == availability,
                        models.VariantPricing.effective_to.is_(None))
                .first())
    if existing is not None:
        return False
    vp = models.VariantPricing(
        variant_id=variant.id, coating_id=coating.id, availability=availability,
        price_pair=price, currency="EGP", source_catalog_id=catalog.id,
        effective_from=datetime.utcnow(), market_scope=market_scope,
        power_eligibility=models.PowerEligibilityStatus.UNRESTRICTED)
    db.add(vp); db.commit(); db.refresh(vp)
    for band in bands:
        pr = models.PowerRange(
            lens_model_id=variant.lens_model_id, variant_id=variant.id, pricing_id=vp.id,
            sph_min=band.sph_min, sph_max=band.sph_max, cyl_min=band.cyl_min, cyl_max=band.cyl_max,
            total_power_min=band.total_power_min, max_cyl_abs=band.max_cyl_abs,
            notes=f"diameter_mm={band.diameter_zone} | source=ZEISS_Main_Catalog.pdf pp.51-52 "
                  f"\"ZEISS MyoCare Lenses\"")
        db.add(pr)
    db.commit()
    return True


def reconcile(db: Session) -> Dict[str, int]:
    """Idempotently creates MyoCare and MyoCare S (RX + Stock) under ZEISS.
    Never touches any other ZEISS model, never touches MyoActive. Returns
    counts of newly-created VariantPricing rows; a second call always
    returns all-zero counts."""
    company = _get_company(db, "ZEISS")
    catalog = _get_or_create_catalog(db, company, SOURCE_CATALOG_FILENAME)
    created_rx = 0
    created_stock = 0
    for product_name in PRODUCT_NAMES:
        model = _get_or_create_model(db, company, product_name)
        # RX
        for coating_code, prices_by_index in RX_PRICES.items():
            coating = crud.get_or_create_coating(db, coating_code, name=coating_code)
            for index_value, price in prices_by_index.items():
                variant = _get_or_create_variant(db, model, index_value)
                bands = [b for b in _RX_BANDS if b.index_value == index_value]
                if _ensure_pricing(db, variant, catalog, coating, models.PricingAvailability.RX,
                                    price, None, bands):
                    created_rx += 1
        # Stock / FSV
        stock_variant = _get_or_create_variant(db, model, _STOCK_BAND.index_value)
        stock_coating = crud.get_or_create_coating(db, STOCK_COATING, name=STOCK_COATING)
        if _ensure_pricing(db, stock_variant, catalog, stock_coating, models.PricingAvailability.STOCK,
                            STOCK_PRICE, "Egypt", [_STOCK_BAND]):
            created_stock += 1
    return {"rx_created": created_rx, "stock_created": created_stock}
