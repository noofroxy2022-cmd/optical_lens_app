"""HOYA Daynamic / Daynamic PNX progressive line (Catalog Truth Audit,
2026-09-18, Section B2) - the durable, re-runnable source for this
correction, following the same evidence-module + apply-function pattern as
p0_stock_egypt_evidence.py / technology_evidence.py / addon_scope_evidence.py.

Evidence: Hoya_Price_List_2025_Updated.pdf p.20, "Daynamic Progressive
Lenses (RX)" table - 8 rows (Daynamic 1.5/1.6/1.67 and Daynamic PNX 1.53,
each plain "Super Hi Vision" and "+ Sensity Original (Gray-Brown-Green)"),
each printing TWO numbers under one "Price" header and one G3 total-power
envelope ("Total Sph+Cyl (...) Max Cyl (6)").

OWNER-CONFIRMED BUSINESS RULE (2026-09-19, not an inference): across the
HOYA price catalog, a two-price row is wholesale (first) | customer/retail
(second). The wholesale price must NEVER be persisted as, or surface as, a
seller/customer price - only the second (retail) number is ever written to
VariantPricing.price_pair. The wholesale numbers are cited below in comments
purely as evidence provenance; they are never stored anywhere.

Every other field is cross-validated against evidence already present
elsewhere in this codebase, never guessed:
  - Model identity ("Daynamic" / "Daynamic PNX", category=progressive,
    coating="Super Hi Vision", indexes 1.5/1.53/1.6/1.67) already whitelisted
    in addon_scope_evidence.py's HOYA catalog identities (pre-existing,
    predates this module) - confirms exact spelling/casing.
  - "Daynamic PNX" already listed in technology_evidence._HOYA_PNX_MODELS
    (pre-existing) - confirms the 1.53 model name and that it is
    catalog-proven impact-resistant via the existing PNX mechanism (also
    independently covered by the blanket 1.53 rule).
  - "Sensity Original" already mapped to {PHOTO_GRAY, PHOTO_BROWN} in
    technology_evidence._EVIDENCE for HOYA (pre-existing) - confirms the
    color_variant spelling for the "+ Sensity Original" rows.
  - The G3 total-power envelope for each index (-8/+6/6, -8/+6/6, -13/+6.5/6,
    -13/+8/6 for 1.5/1.53/1.6/1.67 respectively) is IDENTICAL, index-for-index,
    to HOYA's already-correctly-ingested sibling "Amplitude Plus"/"Amplitude
    Plus PNX" progressive rows from the SAME catalog (verified directly
    against release_runtime.db) - HOYA's progressive lens blanks share one
    mechanical power envelope per index across product tiers; only price and
    coating differ. The coarse sph/cyl box is derived with the exact same
    formula already implicit in those sibling rows: cyl_min=-max_cyl_abs,
    cyl_max=0.0, sph_min=total_power_min, sph_max=total_power_max+max_cyl_abs.
  - Coating "Super Hi Vision" (coatings.id already exists in the certified
    runtime db) is used uniformly across all 4 indexes and both color
    variants, matching addon_scope_evidence.py's uniform `coating=super_hv`
    for every Daynamic entry (no per-index exception, unlike Amplitude Plus).
  - market_scope="Out Of Egypt" matches addon_scope_evidence.py's `hoya()`
    helper (fixed for every HOYA progressive/single_vision RX identity) and
    every already-ingested HOYA progressive sibling row.

The "Available Additions" sub-table on the same page (BLC/UVC/MEIRYO/HVLUK/
HVLBUK/Sensity upgrades/Tinting/SunPro/Mirror) is deliberately NOT re-encoded
here: "BLC" already exists as a HOYA-wide RX Type-B add-on in
technology_evidence._ADDON_EVIDENCE (price 1500 - already the correct retail
number under this same owner rule), which already applies to any HOYA RX
row including these new Daynamic ones with zero further change. The other
Additions do not map to any capability this app currently tracks; encoding
them would require a new, unproven capability-mapping decision and is
out of the now-proven Daynamic scope.
"""
from decimal import Decimal
from typing import Dict, Tuple

from sqlalchemy.orm import Session

from app import models, crud

_SUPER_HI_VISION = "Super Hi Vision"
_SENSITY_ORIGINAL = "Sensity Original"

# index -> (total_power_min, total_power_max, max_cyl_abs) - proven identical
# to Amplitude Plus/Amplitude Plus PNX at the same index (see module docstring).
_G3_ENVELOPE: Dict[float, Tuple[float, float, float]] = {
    1.5: (-8.0, 6.0, 6.0),
    1.53: (-8.0, 6.0, 6.0),
    1.6: (-13.0, 6.5, 6.0),
    1.67: (-13.0, 8.0, 6.0),
}

# (model_name, index) -> (wholesale [never persisted - cited for provenance
# only], retail [the only value ever written to price_pair]), per color.
# Hoya_Price_List_2025_Updated.pdf p.20.
_BASE_PRICES: Dict[Tuple[str, float], Tuple[Decimal, Decimal]] = {
    ("Daynamic", 1.5): (Decimal("6000"), Decimal("12600")),
    ("Daynamic PNX", 1.53): (Decimal("7200"), Decimal("15150")),
    ("Daynamic", 1.6): (Decimal("8000"), Decimal("16800")),
    ("Daynamic", 1.67): (Decimal("8200"), Decimal("17250")),
}
_SENSITY_PRICES: Dict[Tuple[str, float], Tuple[Decimal, Decimal]] = {
    ("Daynamic", 1.5): (Decimal("8700"), Decimal("18300")),
    ("Daynamic PNX", 1.53): (Decimal("9650"), Decimal("20300")),
    ("Daynamic", 1.6): (Decimal("10300"), Decimal("21650")),
    ("Daynamic", 1.67): (Decimal("10600"), Decimal("22300")),
}


def _get_or_create_model(db: Session, company_id: int, name: str) -> models.LensModel:
    m = (db.query(models.LensModel)
         .filter(models.LensModel.company_id == company_id, models.LensModel.name == name,
                 models.LensModel.category == models.LensCategory.PROGRESSIVE)
         .first())
    if m is not None:
        return m
    m = models.LensModel(company_id=company_id, name=name, category=models.LensCategory.PROGRESSIVE)
    db.add(m); db.commit(); db.refresh(m)
    return m


def _get_or_create_variant(db: Session, model: models.LensModel, index_value: float,
                            color_variant: str = None) -> models.LensVariant:
    v = (db.query(models.LensVariant)
         .filter(models.LensVariant.lens_model_id == model.id,
                 models.LensVariant.index_value == index_value,
                 models.LensVariant.material == models.MaterialType.CR39,
                 models.LensVariant.design_type == models.DesignType.SPHERICAL,
                 models.LensVariant.is_aspherical.is_(False),
                 models.LensVariant.color_variant == color_variant)
         .first())
    if v is not None:
        return v
    v = models.LensVariant(
        lens_model_id=model.id, material=models.MaterialType.CR39, index_value=index_value,
        design_type=models.DesignType.SPHERICAL, is_aspherical=False,
        color_variant=color_variant, availability=models.LensAvailability.RX,
        price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    return v


def reconcile(db: Session) -> dict:
    """Idempotent: creates the 8 catalog-proven Daynamic/Daynamic PNX
    VariantPricing rows (+ their PowerRange) if not already present. Never
    touches any other HOYA row. Returns counts; safe to call on every
    startup/rebuild."""
    company = db.query(models.Company).filter(models.Company.name == "HOYA").first()
    if company is None:
        return {"created_pricing_rows": 0, "reason": "HOYA company not found"}
    catalog = (db.query(models.Catalog)
               .filter(models.Catalog.company_id == company.id,
                       models.Catalog.status == models.CatalogStatus.CONFIRMED)
               .order_by(models.Catalog.id)
               .first())
    if catalog is None:
        return {"created_pricing_rows": 0, "reason": "no CONFIRMED HOYA catalog found"}
    coating = (db.query(models.Coating)
               .filter(models.Coating.name == _SUPER_HI_VISION)
               .first())
    if coating is None:
        return {"created_pricing_rows": 0, "reason": "Super Hi Vision coating not found"}

    created = 0
    for color_variant, prices in ((None, _BASE_PRICES), (_SENSITY_ORIGINAL, _SENSITY_PRICES)):
        for (model_name, index_value), (_wholesale, retail) in prices.items():
            model = _get_or_create_model(db, company.id, model_name)
            variant = _get_or_create_variant(db, model, index_value, color_variant)
            existing = (db.query(models.VariantPricing)
                        .filter(models.VariantPricing.variant_id == variant.id,
                                models.VariantPricing.coating_id == coating.id,
                                models.VariantPricing.availability == models.PricingAvailability.RX,
                                models.VariantPricing.market_scope == "Out Of Egypt",
                                models.VariantPricing.effective_to.is_(None))
                        .first())
            if existing is not None:
                continue
            total_min, total_max, max_cyl = _G3_ENVELOPE[index_value]
            power_scope = crud.build_power_scope(
                sph_min=total_min, sph_max=total_max + max_cyl, cyl_min=-max_cyl, cyl_max=0.0,
                total_power_min=total_min, total_power_max=total_max, max_cyl_abs=max_cyl)
            vp = models.VariantPricing(
                variant_id=variant.id, coating_id=coating.id,
                availability=models.PricingAvailability.RX,
                power_eligibility=models.PowerEligibilityStatus.UNRESTRICTED,
                price_pair=retail, currency="EGP", source_catalog_id=catalog.id,
                market_scope="Out Of Egypt", power_scope=power_scope)
            db.add(vp); db.commit(); db.refresh(vp)
            pr = models.PowerRange(
                lens_model_id=model.id, variant_id=variant.id, pricing_id=vp.id,
                sph_min=total_min, sph_max=total_max + max_cyl, cyl_min=-max_cyl, cyl_max=0.0,
                total_power_min=total_min, total_power_max=total_max, max_cyl_abs=max_cyl)
            db.add(pr); db.commit()
            created += 1
    return {"created_pricing_rows": created}
