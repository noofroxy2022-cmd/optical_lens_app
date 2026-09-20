"""Progressive ADD data-completeness fix (Catalog Truth Audit follow-up,
2026-09-19) - the single, centralized, re-runnable source for defaulting a
Progressive PowerRange's missing ADD bounds, following the same
evidence-module + apply-function pattern as p0_stock_egypt_evidence.py /
hoya_daynamic_evidence.py.

OWNER-CONFIRMED BUSINESS RULE (authoritative, not an inference): Progressive
ADD is available from +0.75D through +3.50D inclusive, in +0.25D steps, and
this is the Progressive ADD range used across every Progressive manufacturer
in this project. For HOYA specifically, the catalog note "Available
Additions From +0.75 To +3.50 Maximum" - repeated verbatim on every genuine
"...Progressive Lenses (RX)" page (Hoya_Price_List_2025_Updated.pdf pp.18-24)
- means the Progressive lens Addition power range itself, per the owner
(not merely add-on-coating eligibility, which was this module's own earlier,
now-superseded reading before the owner's confirmation).

The 0.25D step is a domain fact, not a new validation: the schema/matcher
has no step/increment check anywhere (grepped - none exists), only a
continuous add_min<=add<=add_max interval check
(lens_matcher._check_form_against_range). Per instruction, no such check is
invented here; only the interval bounds are populated.

Audit (release_runtime.db, 2026-09-19) - every category=PROGRESSIVE
PowerRange row, before this fix:
  - Maxxee: 34 rows, ALL already add_min=0.75/add_max=3.5 - matches the
    owner rule exactly, never touched (rule: never overwrite explicit data).
  - HOYA: 75 rows total, ALL add_min/add_max NULL, split into:
    * 52 rows across 12 GENUINELY progressive families, each explicitly
      headed "Progressive Lenses (RX)" in the real catalog: Amplitude Plus
      (6)/PNX(2), Balansis(7)/PNX(2), Daynamic(6)/PNX(2), iD LifeStyle(7)/
      PNX(2), iD MyStyle(7)/PNX(2), iD MySelf(7)/PNX(2) - THE PROVEN GAP
      this module fixes.
    * 13 rows OUT OF SCOPE, stored under category=PROGRESSIVE only as a
      known pre-existing importer quirk (see addon_scope_evidence.py's own
      comment: "HOYA's importer stores occupational/bifocal models as
      progressive"), never touched:
        - "Bi-Focal" (5 rows) - catalog page headed "Bi-Focal Lenses (RX)"
          (p.27) - explicitly excluded per the owner's "Progressive only"
          confirmation.
        - "Supereader B"(2)/"WorkSmart"(2)+PNX(1)/"iD WorkStyle"(2)+PNX(1)
          (8 rows) - catalog page headed "Occupational Lenses (RX)" (p.25-26)
          with fixed reading-DISTANCE specs ("Reading From 40cm To 120cm",
          "(Space-Screen-Close)"), not a continuous ADD-power corridor -
          a materially different product type from "Progressive lenses".

RESOLVED (Special Lenses architecture / HOYA Mineral split, owner-confirmed
2026-09-20): the original audit above also excluded "Mineral" (10 rows) as
out of scope, reasoning the page is headed only "Mineral Lenses (RX)", never
"Progressive Lenses (RX)". That page-header-level reading was correct but
incomplete: the page's own row-level printed names prove it actually mixes
TWO optical designs under one importer LensModel - 4 plain Single Vision
rows and 6 rows explicitly named "... Summit Progressive Multi Coat". See
app/hoya_mineral_summit_evidence.py for the full citation and the split
that resolves this: the 4 plain rows stay under HOYA "Mineral"
(category=SINGLE_VISION, permanently out of this module's PROGRESSIVE-only
query - no exclusion-list entry needed any more), and the 6 Summit rows move
to a new "Mineral Summit Progressive" LensModel (category=PROGRESSIVE) -
which, being genuinely Progressive and not listed in _EXCLUDED_MODEL_NAMES,
receives the same owner-confirmed +0.75/+3.50 rule as HOYA's other 12
genuine Progressive families the next time this module runs (order
dependency: hoya_mineral_summit_evidence.reconcile() must run first).

No other manufacturer currently has any category=PROGRESSIVE row this
module's exclusion list needs to know about.
"""
from typing import Dict, FrozenSet

from sqlalchemy.orm import Session

from app import models

DEFAULT_PROGRESSIVE_ADD_MIN = 0.75
DEFAULT_PROGRESSIVE_ADD_MAX = 3.50

# company -> LensModel names that are stored as category=PROGRESSIVE but are
# catalog-proven NOT to be genuine Progressive-ADD-corridor products (see
# module docstring for the exact page evidence per name). Never touched.
# "Mineral" no longer appears here (2026-09-20): the plain rows are now
# SINGLE_VISION (out of this query entirely) after the split in
# app/hoya_mineral_summit_evidence.py; the genuinely-Progressive "Mineral
# Summit Progressive" rows are deliberately NOT excluded - they receive the
# rule below like any other genuine HOYA Progressive family.
_EXCLUDED_MODEL_NAMES: Dict[str, FrozenSet[str]] = {
    "HOYA": frozenset({
        "Bi-Focal",
        "Supereader B", "WorkSmart", "WorkSmart PNX",
        "iD WorkStyle", "iD WorkStyle PNX",
    }),
}


def reconcile(db: Session) -> dict:
    """Idempotent: fills add_min/add_max with the owner-confirmed default
    (0.75/3.50) on every Progressive PowerRange row that has NEITHER bound
    set. Never touches a row that already has any explicit add_min or
    add_max (more-specific catalog evidence always wins), never touches
    Bifocal or any other category, never touches the HOYA
    occupational/bifocal rows misfiled under category=PROGRESSIVE. Correctly
    DOES reach "Mineral Summit Progressive" once
    hoya_mineral_summit_evidence.reconcile() has split it out - it is a
    genuine Progressive family, not an exclusion.
    Returns the count of rows updated; safe to call on every startup/rebuild.
    """
    rows = (
        db.query(models.PowerRange)
        .join(models.VariantPricing, models.VariantPricing.id == models.PowerRange.pricing_id)
        .join(models.LensVariant, models.LensVariant.id == models.PowerRange.variant_id)
        .join(models.LensModel, models.LensModel.id == models.LensVariant.lens_model_id)
        .join(models.Company, models.Company.id == models.LensModel.company_id)
        .filter(models.LensModel.category == models.LensCategory.PROGRESSIVE,
                models.PowerRange.add_min.is_(None),
                models.PowerRange.add_max.is_(None))
        .all()
    )
    updated = 0
    for pr in rows:
        company_name = pr.variant.lens_model.company.name
        model_name = pr.variant.lens_model.name
        if model_name in _EXCLUDED_MODEL_NAMES.get(company_name, frozenset()):
            continue
        pr.add_min = DEFAULT_PROGRESSIVE_ADD_MIN
        pr.add_max = DEFAULT_PROGRESSIVE_ADD_MAX
        updated += 1
    if updated:
        db.commit()
    return {"updated": updated}
