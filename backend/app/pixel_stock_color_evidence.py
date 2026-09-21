"""PIXEL Stock Out Of Egypt "Finished, Single Vision, Out Of Egypt" color-
attribute correction.

CONFIRMED FROM DIRECT CATALOG EVIDENCE (owner-supplied, HAT catalog-gap
reconciliation, 2026-09-21): the "Finished, Single Vision, Out Of Egypt"
page prints these two commercial identities with an explicit "Transmatic
/B/G" color, matching the DB's already-correct price/range/coating/index
exactly:

  Index 1.50, coating "Astro", Spheric  - PAIR price 3500 both bands
      negative SPH 0.00 to -4.00, positive SPH 0.00 to +4.00, CYL to -2.00
  Index 1.56, coating "Astro+B", Aspheric - PAIR price 5000 both bands
      negative SPH 0.00 to -4.00, positive SPH 0.00 to +4.00, CYL to -2.00

Full reconciliation of every OTHER row visible on the same catalog page
(indices 1.53/1.61/1.67, both Clear and Transmatic/G identities) against the
live release_runtime.db found every one of them ALREADY correctly
represented (same coating, price, range, availability, market_scope) - this
module corrects ONLY the two rows above. Their price, PowerRange (already
split into a genuine negative-band and positive-band VariantPricing row per
the project's existing positive/negative representation), coating, index,
design-type and availability were ALL already correct; only
LensVariant.color_variant was left NULL on these two rows - never guessed,
now set explicitly from this direct catalog citation. This is a
normalization/linking correction, not a missing-row import: no
VariantPricing, PowerRange, price, or availability is created or changed
here, and no OTHER Pixel identity is touched.

Idempotent by construction: identifies each target variant structurally
(company, category, index_value, design_type, is_aspherical, color_variant
IS NULL, design_variant IS NULL) - unique within Pixel Single Vision at each
index today - and is a safe no-op if color_variant is already set. Never
guesses: raises rather than silently doing nothing if the expected structural
shape (including the specific coating/price this citation is tied to) is not
found, so this module fails loudly instead of silently matching the wrong
row after a future re-import changes the shape.
"""
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models


def _get_company(db: Session, name: str):
    return db.query(models.Company).filter(models.Company.name == name).first()


def reconcile_pixel_stock_transmatic_colors(db: Session) -> int:
    """Sets color_variant="Transmatic/B/G" on the two structurally-unique,
    already-priced Pixel Stock Out Of Egypt Single Vision identities cited
    above. Returns the number of variants actually changed (0 on a repeat
    run)."""
    company = _get_company(db, "Pixel")
    if company is None:
        return 0

    targets = [
        # (index_value, design_type, is_aspherical, expected coating, expected price)
        (1.50, models.DesignType.SPHERICAL, False, "Astro", "3500.00"),
        (1.56, models.DesignType.ASPHERICAL, True, "Astro+B", "5000.00"),
    ]
    changed = 0
    for index_value, design_type, is_aspherical, expected_coating, expected_price in targets:
        candidates = (
            db.query(models.LensVariant)
            .join(models.LensModel)
            .filter(
                models.LensModel.company_id == company.id,
                models.LensModel.category == models.LensCategory.SINGLE_VISION,
                models.LensVariant.index_value == index_value,
                models.LensVariant.design_type == design_type,
                models.LensVariant.is_aspherical == is_aspherical,
                models.LensVariant.design_variant.is_(None),
                # NOTE: SQL's IN() never matches NULL, even if NULL is in the
                # list - must be spelled out with an explicit IS NULL branch.
                or_(models.LensVariant.color_variant.is_(None),
                    models.LensVariant.color_variant == "Transmatic/B/G"),
            )
            .all()
        )
        if len(candidates) != 1:
            raise RuntimeError(
                f"pixel_stock_color_evidence: expected exactly 1 matching Pixel "
                f"Single Vision variant at index {index_value} (design_type="
                f"{design_type}, aspherical={is_aspherical}, color NULL or already "
                f"Transmatic/B/G), found {len(candidates)} - catalog shape changed, "
                f"refusing to guess which row to correct."
            )
        variant = candidates[0]
        if variant.color_variant == "Transmatic/B/G":
            continue  # already reconciled - safe no-op
        priced = [
            p for p in variant.pricing_records
            if p.effective_to is None
            and p.availability == models.PricingAvailability.STOCK
            and p.market_scope == "Out Of Egypt"
            and str(p.price_pair) == expected_price
            and p.coating is not None and p.coating.code == expected_coating
        ]
        if not priced:
            raise RuntimeError(
                f"pixel_stock_color_evidence: variant {variant.id} at index "
                f"{index_value} does not carry the expected {expected_coating} / "
                f"{expected_price} Stock Out Of Egypt pricing this citation is tied "
                f"to - refusing to change its color_variant."
            )
        variant.color_variant = "Transmatic/B/G"
        changed += 1
    if changed:
        db.commit()
    return changed
