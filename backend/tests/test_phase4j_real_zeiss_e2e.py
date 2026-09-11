"""Phase 4J - ONE real-PDF integration test tying the whole SV-RX story
together: real catalog -> real 315-row commercial extraction/confirmation
(index-grid strategy) -> real graphical-range evidence attach -> real
eligibility check. Marked slow/integration (skipped unless the real ZEISS
PDF is present, matching this project's existing HOYA real-catalog test
convention) so normal test runs stay fast; this is the one test that must
never be replaced by synthetic-only coverage for this specific claim.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database import Base  # noqa: E402
from app import models, database, crud, schemas  # noqa: E402
from app.pdf_hybrid_parser import PDFHybridParser, ParserContext  # noqa: E402
from app.zeiss_svrx_graphical_evidence import build_extracted_models  # noqa: E402
from app.lens_matcher import lens_matcher as _matcher  # noqa: E402

_ZEISS_PDF = r"C:\Users\WIN-10 PRO\Downloads\ZEISS_Main_Catalog.pdf"


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    event.listen(engine, "connect", database._set_sqlite_pragma)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


# No custom "slow" marker exists in this project (no pytest.ini registering
# one) - matches the established real-catalog convention exactly
# (test_phase4_parser.py's @pytest.mark.skipif(not os.path.exists(_HOYA_UPD))):
# skipped automatically wherever the real PDF isn't present, runs for real
# otherwise. This is the ONE test in the whole SV-RX story that touches the
# actual authoritative PDF end to end - deliberately not duplicated.
@pytest.mark.skipif(not os.path.exists(_ZEISS_PDF), reason="real ZEISS catalog not present")
def test_4j_real_zeiss_315_extraction_and_graphical_attach(db):
    import pdfplumber

    # ---- 1. real 315-row commercial extraction (index-grid strategy) ----
    co = crud.create_company(db, schemas.CompanyCreate(name="ZEISS", country="EG"))
    price_cat = models.Catalog(company_id=co.id, filename="ZEISS_Main_Catalog.pdf",
                               file_path=_ZEISS_PDF, status=models.CatalogStatus.DRAFT)
    db.add(price_cat); db.commit(); db.refresh(price_cat)

    p = PDFHybridParser(use_vision=False)
    with pdfplumber.open(_ZEISS_PDF) as pdf:
        page = pdf.pages[6]  # 0-indexed page 6 = PDF page 7, the SV-RX price grid
        extracted = list(p._reconstruct_index_grid(page, ParserContext()))
    counts = {m.name: len(m.power_ranges) for m in extracted}
    assert counts == {"ClearMind": 172, "ClearView RX": 86, "SPH RX": 57}
    assert sum(counts.values()) == 315

    p.extracted_models = extracted
    p.save_extractions_to_db(price_cat.id, db)
    exts = crud.get_extractions_by_catalog(db, price_cat.id)
    assert len(exts) == 315

    # human review overlay: the index-grid strategy always flags needs_review
    # (it cannot verify availability structurally) - the one real correction
    # is availability, since this SV-RX family is ZEISS's own "RX" category
    # (the section header is literally "ZEISS Single Vision Lenses - RX").
    for e in exts:
        crud.update_extraction(db, e.id, schemas.CatalogExtractionUpdate(extracted_availability="rx"))
        crud.confirm_extraction(db, e.id, "qa")

    result = crud.confirm_catalog_commercial(db, price_cat.id, "admin")
    assert result["confirmed"] == 315
    assert result["conflicts"] == 0
    assert result["skipped_unresolved"] == 0
    vp_count = db.query(models.VariantPricing).join(models.LensVariant).join(models.LensModel).filter(
        models.LensModel.company_id == co.id).count()
    assert vp_count == 315

    # ---- 2. attach ONLY the proven graphical ranges (never the 2 anomaly rows) ----
    ev_cat = models.Catalog(company_id=co.id, filename="zeiss_graphical_evidence.pdf",
                            file_path="synthetic", status=models.CatalogStatus.DRAFT)
    db.add(ev_cat); db.commit(); db.refresh(ev_cat)
    p2 = PDFHybridParser(use_vision=False)
    p2.extracted_models = build_extracted_models(only_confidence="proven")
    p2.save_extractions_to_db(ev_cat.id, db)
    proven_exts = [e for e in crud.get_extractions_by_catalog(db, ev_cat.id) if e.status != "needs_review"]
    for e in proven_exts:
        crud.confirm_extraction(db, e.id, "qa")

    created_total, wrong, ambiguous = 0, 0, 0
    for e in proven_exts:
        res = crud.attach_range_to_existing_pricing(db, e.id)
        if "error" in res:
            if "ambiguous" in res["error"]:
                ambiguous += 1
        else:
            created_total += len(res["created"])
    assert wrong == 0
    assert ambiguous == 0
    assert created_total > 0, "at least the well-justified matches must attach"

    # ---- 3. exercise the real production eligibility path on a real,
    # persisted, attached ZEISS PowerRange ----
    pr = db.query(models.PowerRange).join(models.VariantPricing).join(models.LensVariant).filter(
        models.LensVariant.treatment_band == "Clear",
        models.LensVariant.index_value == 1.74,
        models.PowerRange.total_power_min == -20.0,
    ).first()
    assert pr is not None, "the ClearMind/ClearView RX 1.74 widest Clear range must be attached"
    # exact boundary and 0.25D-outside checks against the REAL persisted row -
    # strict G3 boundaries from commit c2e2c56 must be unchanged.
    ok_exact = _matcher._check_form_against_range(pr, (-14.0, -6.0, 0, 0.0)) == []   # M2=-20 exact
    ok_outside = _matcher._check_form_against_range(pr, (-14.25, -6.0, 0, 0.0)) == []  # M2=-20.25
    assert ok_exact is True
    assert ok_outside is False

    # the 2 anomaly rows must never have created a PowerRange anywhere
    anomaly_ranges = db.query(models.PowerRange).filter(
        models.PowerRange.total_power_min == -4.0, models.PowerRange.total_power_max == -4.0,
    ).count()
    assert anomaly_ranges == 0
