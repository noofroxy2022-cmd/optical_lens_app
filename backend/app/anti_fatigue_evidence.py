"""Young / Anti-Fatigue live-DB reconciliation (Special Lenses architecture,
owner-confirmed, 2026-09-19).

catalog_corrections.corrected_category (the single centralized source for
ingestion-time corrections, called from app/crud.py) already reclassifies
SCOPE's proven Young/Shabab product to models.LensCategory.ANTI_FATIGUE for
any NEW extraction/confirmation - a clean rebuild reproduces it
automatically. It does not retroactively touch rows that were already
confirmed and persisted before this fix. This module is the same reconcile()
pattern as occupational_office_evidence.py / progressive_add_evidence.py:
idempotent, safe to call on every startup/rebuild, and reads catalog_
corrections.ANTI_FATIGUE_MODELS itself (the single centralized proven-model
list) - deliberately never the full corrected_category(), which also knows
about the separate Occupational/Office and Myopia Control corrections, so
this module can never side-effect a row belonging to a different Special
Lenses subtype.

Owner-confirmed business rule (2026-09-19): this subtype is reached only by
the seller/doctor deliberately choosing "Special Lenses -> Young /
Anti-Fatigue" - the app never gates it on patient age or any frame/fitting
measurement (none exist in the schema, and none are added here). The trained
person in the optical store, not the app, decides whether the product is
appropriate; the app's job is only to show proven products under the correct
subtype, match the printed Power Range, and apply the normal price/
availability mechanisms.
"""
from typing import Dict

from sqlalchemy.orm import Session

from app import catalog_corrections, models


def reconcile(db: Session) -> Dict[str, int]:
    """Updates LensModel.category to ANTI_FATIGUE for every already-persisted
    SCOPE Young/Shabab row that is not yet correctly classified. Never
    touches any other company or model. Scoped strictly to
    ANTI_FATIGUE_MODELS' own name list (never the full corrected_category(),
    which also knows about the separate Occupational/Office and Myopia
    Control corrections) so this module can never side-effect a row
    belonging to a different Special Lenses subtype. Returns the count of
    rows updated; a second call always returns 0 (idempotent)."""
    rows = (
        db.query(models.LensModel)
        .join(models.Company, models.Company.id == models.LensModel.company_id)
        .filter(models.Company.name.in_(tuple(catalog_corrections.ANTI_FATIGUE_MODELS)))
        .all()
    )
    updated = 0
    for lm in rows:
        if lm.name not in catalog_corrections.ANTI_FATIGUE_MODELS.get(lm.company.name, frozenset()):
            continue
        if lm.category != models.LensCategory.ANTI_FATIGUE:
            lm.category = models.LensCategory.ANTI_FATIGUE
            updated += 1
    if updated:
        db.commit()
    return {"updated": updated}
