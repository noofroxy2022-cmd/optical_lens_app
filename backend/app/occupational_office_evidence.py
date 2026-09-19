"""Occupational / Office live-DB reconciliation (Special Lenses architecture,
owner-confirmed, 2026-09-19).

catalog_corrections.corrected_category (the single centralized source for
ingestion-time corrections, called from app/crud.py) already reclassifies
HOYA's Occupational family and SCOPE's Office family to
models.LensCategory.OFFICE for any NEW extraction/confirmation - a clean
rebuild reproduces it automatically. It does not retroactively touch rows
that were already confirmed and persisted before this fix. This module is
the same reconcile() pattern as progressive_add_evidence.py /
p0_stock_egypt_evidence.py: idempotent, safe to call on every startup/
rebuild, and reads catalog_corrections.OCCUPATIONAL_OFFICE_MODELS itself (the
single centralized proven-model list) - deliberately never the full
corrected_category(), which also knows about the separate Young/Anti-Fatigue
and Myopia Control corrections, so this module can never side-effect a row
belonging to a different Special Lenses subtype.
"""
from typing import Dict

from sqlalchemy.orm import Session

from app import catalog_corrections, models


def reconcile(db: Session) -> Dict[str, int]:
    """Updates LensModel.category to OFFICE for every already-persisted HOYA
    Occupational / SCOPE Office row that is not yet correctly classified.
    Never touches any other company or model. Scoped strictly to
    OCCUPATIONAL_OFFICE_MODELS' own name list (never the full corrected_
    category(), which also knows about the separate Young/Anti-Fatigue and
    Myopia Control corrections) so this module can never side-effect a row
    belonging to a different Special Lenses subtype. Returns the count of
    rows updated; a second call always returns 0 (idempotent)."""
    rows = (
        db.query(models.LensModel)
        .join(models.Company, models.Company.id == models.LensModel.company_id)
        .filter(models.Company.name.in_(tuple(catalog_corrections.OCCUPATIONAL_OFFICE_MODELS)))
        .all()
    )
    updated = 0
    for lm in rows:
        if lm.name not in catalog_corrections.OCCUPATIONAL_OFFICE_MODELS.get(lm.company.name, frozenset()):
            continue
        if lm.category != models.LensCategory.OFFICE:
            lm.category = models.LensCategory.OFFICE
            updated += 1
    if updated:
        db.commit()
    return {"updated": updated}
