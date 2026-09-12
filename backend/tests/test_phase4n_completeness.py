"""
Phase 4N: completeness tripwire tests for the ZEISS SV-RX graphical evidence
table.

Phase 4H/4I transcribed only 42 of the page's 131 real graphical bars (89
were simply never transcribed - not a deliberate exclusion). Phase 4N
independently re-derived the full page (pdfplumber vector geometry + 600dpi
rendered crops, cross-checked against each other) and rebuilt ALL_ROWS from
that source inventory. These tests assert the exact counts that
reconstruction proved, so that a FUTURE catalog-evidence edit that silently
drops rows (the exact Phase 4H failure mode) fails CI immediately instead of
going unnoticed for four more phases.

These are structural/count assertions against the current ALL_ROWS table,
not a live re-parse of the PDF (the PDF is not available in CI) - they
encode the proven inventory as a permanent regression fence.
"""
import os
import sys
from collections import Counter

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.zeiss_svrx_graphical_evidence import ALL_ROWS  # noqa: E402


def _norm_band(band: str) -> str:
    if band in ("Clear", "BlueGuard", "Clear/BlueGuard"):
        return "Clear/BlueGuard-family"
    if band == "PhotoFusion X":
        return "PhotoFusion X"
    if band == "AdaptiveSun POL":
        return "AdaptiveSun POL"
    return band


def test_4n_total_canonical_row_count():
    # 131 real source bars - 1 permanently-excluded blank-diameter bar
    # (ClearMind 1.67 "Clear", sph -10.00/+9.50 - no diameter ever printed
    # for it, never fabricated) = 130 usable ChartRow entries.
    assert len(ALL_ROWS) == 130


def test_4n_treatment_totals_reconcile_to_proven_pdf_counts():
    totals = Counter(_norm_band(r.treatment_band) for r in ALL_ROWS)
    # Clear/BlueGuard-family: 50 real bars in the PDF, 1 permanently excluded -> 49.
    assert totals["Clear/BlueGuard-family"] == 49
    assert totals["PhotoFusion X"] == 26
    assert totals["POL"] == 20
    assert totals["AdaptiveSun"] == 21
    assert totals["AdaptiveSun POL"] == 14


def test_4n_family_totals_reconcile():
    totals = Counter(r.family for r in ALL_ROWS)
    assert totals["ClearView RX"] == 46
    assert totals["ClearMind"] == 44  # 45 real bars - 1 permanently excluded
    assert totals["SPH RX"] == 40


def test_4n_clearview_rx_150_and_153_present():
    # Phase 4M found these two entire index blocks wholesale absent from the
    # pre-4N evidence table (0 rows each). They must never silently regress
    # back to empty.
    cv_150 = [r for r in ALL_ROWS if r.family == "ClearView RX" and r.index_value == 1.50]
    cv_153 = [r for r in ALL_ROWS if r.family == "ClearView RX" and r.index_value == 1.53]
    assert len(cv_150) == 13
    assert len(cv_153) == 3
    # 1.53 is Clear/BlueGuard-only - no POL/AdaptiveSun/AdaptiveSun POL bar
    # exists at that index; a future edit must not invent one.
    assert {r.treatment_band for r in cv_153} == {"Clear/BlueGuard"}


def test_4n_sph_rx_has_no_174_block():
    # SPH RX genuinely has no 1.74 index in the real catalog (confirmed both
    # graphically - the chart draws no such block - and commercially - the
    # real price grid prints blank cells for SPH RX at 1.74). A future edit
    # must not invent a SPH RX 1.74 row.
    assert not [r for r in ALL_ROWS if r.family == "SPH RX" and r.index_value == 1.74]


def test_4n_no_duplicate_semantic_rows():
    keys = [(r.family, r.index_value, r.treatment_band, r.diameter_zone) for r in ALL_ROWS]
    assert len(keys) == len(set(keys)), "no two ChartRow entries may describe the same source bar"


def test_4n_exactly_two_anomalies_remain_unresolved():
    review_rows = [r for r in ALL_ROWS if r.confidence == "review"]
    assert len(review_rows) == 2
    keys = {(r.family, r.index_value, r.treatment_band, r.total_power_min, r.total_power_max)
            for r in review_rows}
    assert keys == {
        ("ClearMind", 1.5, "POL", -4.0, -4.0),
        ("ClearMind", 1.5, "AdaptiveSun POL", -4.0, -4.0),
    }


def test_4n_anomalies_never_fabricated_as_symmetric():
    # Guards specifically against a future "helpful" auto-correction of the
    # printed -4.00/-4.00 to the "expected" +4.00 - the anomaly must stay
    # exactly as printed.
    for r in ALL_ROWS:
        if r.confidence == "review":
            assert r.total_power_min == r.total_power_max == -4.0


def test_4n_every_row_has_sane_bounds_except_known_anomalies():
    # min must be <= max, and cyl must be non-negative, for every row that
    # isn't one of the two known-anomalous rows above.
    for r in ALL_ROWS:
        if r.confidence == "review":
            continue
        assert r.total_power_min <= r.total_power_max, r
        assert r.max_cyl_abs >= 0, r


def test_4n_clear_blueguard_band_labels_are_canonical():
    # "BGuard" (an inline chart abbreviation) must always be normalized to
    # "BlueGuard" before it reaches ChartRow - the raw abbreviation would
    # never match the real commercial SKU name and would silently no-SKU.
    bands = {r.treatment_band for r in ALL_ROWS}
    assert "BGuard" not in bands
