"""HOYA "Mineral" / "Mineral Summit Progressive" product split
(owner-confirmed, 2026-09-20).

Evidence: Hoya_Price_List_2025_Updated.pdf p.28, headed "Mineral Lenses
(RX)" - one table, two sections separated by a printed double rule.

  Section 1 (4 rows) - no "Summit"/"Progressive" anywhere in the row name:
    Mineral 1.52 Multi Coat; Mineral 1.52 Multi Coat Photo (Gray-Brown);
    Mineral 1.81 Multi Coat; Mineral 1.9 Multi Coat.
  Section 2 (6 rows) - "Summit Progressive" explicitly printed in every row:
    Mineral 1.52/1.6/1.7/1.81 Summit Progressive Multi Coat, plus the 1.52
    and 1.6 Summit Progressive Multi Coat Photo (Gray-Brown) variants.

OWNER-CONFIRMED READING (2026-09-20, resolving the prior read-only audit's
ambiguity): "Mineral" names the MATERIAL (glass), never a design/category by
itself - HOYA groups every glass-material RX lens on one page. Section 1 is
Single Vision; Section 2 is a genuine Progressive design ("Summit
Progressive"). All 10 rows stay material=GLASS, RX, "Out Of Egypt" - this
module changes ONLY the category/model-identity split, never a price,
PowerRange, material, or availability value (all already proven correct in
the prior audit).

Before this fix, both groups were imported as ONE LensModel named "Mineral"
with category=PROGRESSIVE - correct for the 6 Summit rows, wrong for the 4
plain rows (which have no progressive design evidence at all and were
consequently unreachable in Single Vision search, and could leak into an
employee's advanced/targeted "category=progressive" filter when the
prescription carried no ADD - proven directly against product_search.search
during the read-only audit).

Target shape (durable - reproduces after any rebuild that recreates the
same "one Mineral LensModel" shape from the raw catalog, since the raw
catalog itself never distinguishes the two groups by LensModel name):
  - HOYA "Mineral": category=SINGLE_VISION, keeps the 4 plain
    VariantPricing rows (coating "Multi Coat") and their PowerRange rows
    completely unchanged.
  - HOYA "Mineral Summit Progressive" (new LensModel, category=PROGRESSIVE):
    receives the 6 Summit VariantPricing rows (coating "Progressive Multi
    Coat") and their PowerRange rows, prices and G3 bounds preserved byte
    for byte.

Three of the ten catalog rows (indexes 1.52, 1.52-Photo, 1.81) share ONE
LensVariant between their plain and Summit commercial identity (same
material/index/design/color, two different coatings). Moving that variant
wholesale would incorrectly drag its plain-Mineral pricing along with it, so
this module instead creates a twin LensVariant (identical optical identity)
under the new model for exactly those three, and re-points only the Summit
VariantPricing/PowerRange rows to the twin - the original variant and its
plain pricing never move. The other three Summit rows (indexes 1.6, 1.7,
1.6-Photo) have no plain-Mineral sibling at all, so their existing variant
is moved wholesale (a plain lens_model_id update, no duplication needed).

Identified by the EXACT coating code "Progressive Multi Coat" on a pricing
row currently attached to HOYA's "Mineral" LensModel - never a substring
match on "Summit" or "Progressive" that could reach an unrelated HOYA
product. Progressive ADD (+0.75/+3.50) is deliberately NOT applied here -
that is progressive_add_evidence.reconcile()'s own job, and it must run
AFTER this module so the newly-created "Mineral Summit Progressive" rows
are already sitting in a PROGRESSIVE-category, non-excluded LensModel by the
time it queries.

Idempotent by construction: the query that finds rows to move is scoped to
"currently attached to the Mineral LensModel"; once moved, a row belongs to
the new model and no longer matches, so a second call is always a no-op.
"""
from typing import Dict

from sqlalchemy.orm import Session

from app import models

COMPANY_NAME = "HOYA"
PLAIN_MODEL_NAME = "Mineral"
PROGRESSIVE_MODEL_NAME = "Mineral Summit Progressive"
SUMMIT_COATING_CODE = "Progressive Multi Coat"


def _get_company(db: Session, name: str) -> models.Company:
    co = db.query(models.Company).filter(models.Company.name == name).one_or_none()
    if co is None:
        raise LookupError(f"company {name!r} not found - the Mineral/Summit split expects "
                           f"HOYA's normal catalog import to already exist")
    return co


def _get_or_create_progressive_model(db: Session, company: models.Company) -> models.LensModel:
    m = (db.query(models.LensModel)
         .filter(models.LensModel.company_id == company.id, models.LensModel.name == PROGRESSIVE_MODEL_NAME)
         .first())
    if m is not None:
        return m
    m = models.LensModel(company_id=company.id, name=PROGRESSIVE_MODEL_NAME,
                          category=models.LensCategory.PROGRESSIVE)
    db.add(m); db.commit(); db.refresh(m)
    return m


def _get_or_create_twin_variant(db: Session, target_model: models.LensModel,
                                 source: models.LensVariant) -> models.LensVariant:
    v = (db.query(models.LensVariant)
         .filter(models.LensVariant.lens_model_id == target_model.id,
                 models.LensVariant.material == source.material,
                 models.LensVariant.index_value == source.index_value,
                 models.LensVariant.design_type == source.design_type,
                 models.LensVariant.is_aspherical == source.is_aspherical,
                 models.LensVariant.design_variant == source.design_variant,
                 models.LensVariant.color_variant == source.color_variant,
                 models.LensVariant.design_tier == source.design_tier,
                 models.LensVariant.treatment_band == source.treatment_band)
         .first())
    if v is not None:
        return v
    v = models.LensVariant(
        lens_model_id=target_model.id, material=source.material, index_value=source.index_value,
        design_type=source.design_type, is_aspherical=source.is_aspherical,
        design_variant=source.design_variant, color_variant=source.color_variant,
        design_tier=source.design_tier, treatment_band=source.treatment_band,
        price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    return v


def reconcile(db: Session) -> Dict[str, int]:
    """Splits HOYA's mixed "Mineral" LensModel. Returns counts; a second
    call always returns all-zero counts (idempotent)."""
    company = _get_company(db, COMPANY_NAME)
    result = {"category_fixed": 0, "model_created": 0, "pricing_moved": 0, "twin_variants_created": 0}

    mineral = (db.query(models.LensModel)
               .filter(models.LensModel.company_id == company.id, models.LensModel.name == PLAIN_MODEL_NAME)
               .first())
    if mineral is None:
        return result

    if mineral.category != models.LensCategory.SINGLE_VISION:
        mineral.category = models.LensCategory.SINGLE_VISION
        db.commit()
        result["category_fixed"] = 1

    summit_exists_already = (
        db.query(models.LensModel)
        .filter(models.LensModel.company_id == company.id, models.LensModel.name == PROGRESSIVE_MODEL_NAME)
        .first() is not None
    )
    summit = _get_or_create_progressive_model(db, company)
    if not summit_exists_already:
        result["model_created"] = 1

    summit_pricing_rows = (
        db.query(models.VariantPricing)
        .join(models.LensVariant, models.LensVariant.id == models.VariantPricing.variant_id)
        .join(models.Coating, models.Coating.id == models.VariantPricing.coating_id)
        .filter(models.LensVariant.lens_model_id == mineral.id,
                models.Coating.code == SUMMIT_COATING_CODE)
        .all()
    )
    for vp in summit_pricing_rows:
        old_variant = vp.variant
        other_pricing = [p for p in old_variant.pricing_records if p.id != vp.id]
        is_shared = any((p.coating.code if p.coating else None) != SUMMIT_COATING_CODE
                         for p in other_pricing)
        if is_shared:
            before_count = (db.query(models.LensVariant)
                             .filter(models.LensVariant.lens_model_id == summit.id).count())
            twin = _get_or_create_twin_variant(db, summit, old_variant)
            after_count = (db.query(models.LensVariant)
                           .filter(models.LensVariant.lens_model_id == summit.id).count())
            if after_count > before_count:
                result["twin_variants_created"] += 1
            vp.variant_id = twin.id
            for pr in list(vp.power_ranges):
                pr.variant_id = twin.id
                pr.lens_model_id = summit.id
        else:
            old_variant.lens_model_id = summit.id
            for pr in list(old_variant.power_ranges):
                pr.lens_model_id = summit.id
        db.commit()
        result["pricing_moved"] += 1
    return result
