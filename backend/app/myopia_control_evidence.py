"""Myopia Control live-DB reconciliation (Special Lenses architecture,
owner-confirmed, 2026-09-19).

catalog_corrections.corrected_category (the single centralized source for
ingestion-time corrections, called from app/crud.py) already reclassifies
SCOPE's proven Myoblock/Metavision product to
models.LensCategory.MYOPIA_CONTROL for any NEW extraction/confirmation - a
clean rebuild reproduces it automatically. It does not retroactively touch
rows that were already confirmed and persisted before this fix. This module
is the same reconcile() pattern as anti_fatigue_evidence.py /
occupational_office_evidence.py: idempotent, safe to call on every startup/
rebuild, and reads catalog_corrections.MYOPIA_CONTROL_MODELS itself (the
single centralized proven-model list) - deliberately never the full
corrected_category(), which also knows about the separate Occupational/
Office and Young/Anti-Fatigue corrections, so this module can never
side-effect a row belonging to a different Special Lenses subtype.

Owner clarification (2026-09-19): "Myopia Control" is ONE generic, functional
Special Lenses subtype, never a manufacturer/product name - SCOPE's
"Myoblock/Metavision" is one proven product under it, not the category
itself. A future manufacturer's proven myopia-control product (e.g. ZEISS's
MyoCare / MyoCare S / MyoActive, once ingested) maps to this SAME category by
adding one more entry to MYOPIA_CONTROL_MODELS, never a new category or a
seller-UI redesign.

Owner-confirmed business rule (2026-09-19): this subtype is reached only by
the seller/doctor deliberately choosing "Special Lenses -> Myopia Control" -
the app never gates it on patient age or any frame/fitting measurement
(neither exists in the schema, and neither is added here, even though the
SCOPE catalog prints both as guidance). The trained person in the optical
store, not the app, decides whether the product is appropriate; the app's
job is only to show proven products under the correct subtype, match the
printed Power Range (Sph -0.50 to -10.00, Cyl to -4.00 - representable via
the existing PowerRange sph/cyl fields, no new mechanism), and apply the
normal price/availability mechanisms. ZEISS's proven Myopia Management
products (MyoCare / MyoCare S / MyoActive) are explicitly NOT touched here -
they are not currently ingested at all, and MyoActive's own catalog page
prints "Available from 1st October 2026" (after the current project date) -
a separate ingestion task.
"""
from typing import Dict

from sqlalchemy.orm import Session

from app import catalog_corrections, models


def reconcile(db: Session) -> Dict[str, int]:
    """Updates LensModel.category to MYOPIA_CONTROL for every already-
    persisted SCOPE Myoblock/Metavision row that is not yet correctly
    classified. Never touches any other company or model. Scoped strictly to
    MYOPIA_CONTROL_MODELS' own name list (never the full corrected_
    category(), which also knows about the separate Occupational/Office and
    Young/Anti-Fatigue corrections) so this module can never side-effect a
    row belonging to a different Special Lenses subtype. Returns the count
    of rows updated; a second call always returns 0 (idempotent)."""
    rows = (
        db.query(models.LensModel)
        .join(models.Company, models.Company.id == models.LensModel.company_id)
        .filter(models.Company.name.in_(tuple(catalog_corrections.MYOPIA_CONTROL_MODELS)))
        .all()
    )
    updated = 0
    for lm in rows:
        if lm.name not in catalog_corrections.MYOPIA_CONTROL_MODELS.get(lm.company.name, frozenset()):
            continue
        if lm.category != models.LensCategory.MYOPIA_CONTROL:
            lm.category = models.LensCategory.MYOPIA_CONTROL
            updated += 1
    if updated:
        db.commit()
    return {"updated": updated}
