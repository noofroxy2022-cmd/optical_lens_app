"""
Phase 4H/4I/4N: ZEISS Single Vision RX graphical power-range evidence.

The current ZEISS catalog states SV-RX power eligibility as a bar chart
("Power range: ClearMind" / "Power range: ClearView RX" / "Power range: SPH
RX", ZEISS_Main_Catalog.pdf page 8 of 32) rather than the OLD ClearView Free
Form RX sheet's explicit "Total Power min/max + Max.Cyl" text. This module is
the EXTRACTION-side evidence table for that chart, converted into the SAME
ExtractedPowerRange/ExtractedLensModel objects a text-grammar parser strategy
would produce (see app.pdf_hybrid_parser). Nothing here is a new range type
and nothing here is matcher logic - it is catalog-specific vocabulary/layout,
which belongs in evidence, not in lens_matcher.py or pdf_hybrid_parser.py's
generic dispatch. No RGB constant appears anywhere in this module's logic -
every treatment_band value below is a plain string, never a color.

Phase 4H/4I captured only 42 of the page's 131 real graphical bars (the other
89 were never omitted deliberately - they were simply not transcribed). Phase
4N re-derived the ENTIRE page from scratch, independently of the old table,
and this module is that full reconstruction - not a patch on top of the old
one. Every row below was proven by TWO independent methods:

  Method A (vector): pdfplumber page.rects - every bar's exact
    non_stroking_color (a CMYK 4-tuple) and (x0, x1) extent, plus
    page.extract_words() for every printed number/label with exact
    coordinates. The 5 legend colors were proven by swatch-rect-to-label
    adjacency (a swatch rect's own (x0,x1) sits immediately before its own
    text label), not by color similarity: Clear/BlueGuard=(0,0,0,0.148),
    PhotoFusion X=(0,0,0,0.5), POL=(0.199,0,0.797,0),
    AdaptiveSun=(1.0,0.199,0,0), AdaptiveSun POL=(1.0,0.797,0,0). These are
    the only 5 fill colors used anywhere on the page (bar-artifact one-off
    gradients aside), including in the ClearView RX/SPH RX sections that
    print no legend row of their own - i.e. those sections reuse the
    ClearMind legend's own proven definitions.
  Method B (rendered crop): the same region rendered to a 600dpi raster
    image and read directly - bar count, diameter label, sph bounds, cyl
    limit, and which bars share one printed label with which.
  Every row's rect count and rendered-crop bar count were cross-checked
  (the "tripwire"): a mismatch between the two counts means a bar was
  missed by one method, and the row is re-cropped tighter until both agree.
  This caught two real near-misses during Phase 4N (a ClearMind 1.6 and a
  ClearView RX 1.67 row each initially undercounted a PhotoFusion X bar
  sitting between two visually similar gray bars) - both were corrected
  before being recorded here, not left as guesses.

  Side finding (Phase 4I, reconfirmed in 4N): ClearView RX and SPH RX's
  sections render every index header, "sph"/"cyl" column label, and each
  bar TWICE at a fixed +62.2pt x-offset - a duplicate-rendering artifact in
  the source PDF. Both copies always carry the same value and the same y
  (top) coordinate, so grouping bars by (panel, rounded top) inherently
  de-duplicates this artifact without discarding any real bar.

CONFIDENCE POLICY (do not weaken without re-verifying against the source):
  - "proven": both methods agree with high confidence. Safe to
    review-confirm and commercially attach.
  - "review": a genuine, still-unresolved anomaly, or a value that cannot be
    read with high confidence by either method. Captured as evidence (raw
    label, page, diameter, treatment preserved) but NEVER confirmed/attached;
    power_eligibility stays irrelevant / not-yet-eligible until a human
    resolves it. Intentional under-coverage, not a bug.

Exactly TWO source bars remain anomalous (unchanged since Phase 4H, never
auto-corrected, never compressed into one row):
  - ClearMind 1.5, diameter 80/85, POL bar: printed "-4.00"/"-4.00".
  - ClearMind 1.5, diameter 80/85, AdaptiveSun POL bar: printed
    "-4.00"/"-4.00" (shares the POL row's printed label pair - one printed
    typo affecting both rows, not two independent misreads, but still two
    distinct bars and two distinct semantic rows below, one per treatment).
  Every structurally identical row elsewhere in the chart reads "+4.00" at
  this position, so this is very likely a genuine catalog typo - but per
  instruction it is never silently corrected. Stays "review" / unresolved
  for commercial persistence until ZEISS or the catalog owner confirms
  intent.

Exactly ONE source bar is permanently excluded (not "review" - there is
nothing to resolve, because no diameter was ever printed for it and one is
never fabricated): ClearMind 1.67, a "Clear"-labelled bar reading sph
-10.00/+9.50, cyl +6.00, whose diameter cell is genuinely blank in the
source PDF's own text layer (no word object exists there at all). This is
the only reduction between the 131 real source bars and the 130 ChartRow
entries below - there is no other compression at the ChartRow level. (The
Clear/BlueGuard EXPANSION described below happens at attach time, in the
opposite direction: one ChartRow becomes two real commercial SKUs, never
fewer.)

Footnote-driven exclusions (both confirmed from the printed footnote text,
not inferred):
  - ClearView RX / ClearMind: "*1.67, 1.6: ø80 not available in BlueGuard
    design" -> at those two indices' ø80 diameter, the Clear/BlueGuard bar
    proves "Clear" only; BlueGuard is not a valid treatment_band there.
  - SPH RX: "*1.5: Not available in ø80 BlueGuard design" -> same exclusion,
    index 1.5 only, for SPH RX.
"""
from dataclasses import dataclass
from typing import List, Optional

from app.pdf_hybrid_parser import ExtractedLensModel, ExtractedPowerRange

SOURCE_PAGE = "ZEISS_Main_Catalog.pdf page 8 of 32 (\"ZEISS Single Vision Lenses - RX\")"

# index value -> (MaterialType enum value, material label used in notes)
_INDEX_MATERIAL = {
    1.50: "CR39",
    1.53: "trivex",
    1.60: "high_index_1.60",
    1.67: "high_index_1.67",
    1.74: "high_index_1.74",
}


@dataclass(frozen=True)
class ChartRow:
    family: str                    # "ClearMind" | "ClearView RX" | "SPH RX"
    design_tier: Optional[str]     # None -> family-level, shared across tiers
    index_value: float
    treatment_band: str            # raw catalog band evidence, e.g. "Clear/BlueGuard"
    diameter_zone: str             # raw catalog evidence, e.g. "70/75" or "60 - 55"
    total_power_min: float
    total_power_max: float
    max_cyl_abs: float
    confidence: str                # "proven" | "review"
    review_reason: Optional[str] = None


# ============================================================
# ClearView RX - family-level chart (no tier column on this page: ClearView
# RX has no "Individual 3 / Superb" split like ClearMind does), legend shared
# with ClearMind/SPH RX on the same page. Source: page 8, "Power range:
# ClearView RX". 46 real source bars (Phase 4N full reconstruction; Phase
# 4H/4I had captured 15 of these).
# ============================================================
_CLEARVIEW_RX_ROWS: List[ChartRow] = [
    # -- 1.74 (Abbe 32; Density 1.47) -- 5 bars, all Phase 4H/4I.
    ChartRow("ClearView RX", None, 1.74, "Clear/BlueGuard", "70", -12.00, 9.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.74, "PhotoFusion X", "70", -10.00, 9.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.74, "Clear/BlueGuard", "65", -15.00, 13.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.74, "Clear/BlueGuard", "60 - 55", -20.00, 16.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.74, "PhotoFusion X", "65 - 55", -14.00, 11.25, 6.00, "proven"),
    # -- 1.67 (Abbe 32; Density 1.35) -- 9 bars: 7 Phase 4H/4I, 2 newly
    # recovered in Phase 4N (PhotoFusion X bars sitting between the
    # Clear/BlueGuard and AdaptiveSun bars at each of these two diameters -
    # the exact failure mode the tripwire was built to catch).
    # footnote: "*1.67, 1.6: ø80 not available in BlueGuard design" -> Clear only at ø80
    ChartRow("ClearView RX", None, 1.67, "Clear", "80", -6.00, 6.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.67, "POL", "80", -4.00, 4.00, 4.00, "proven"),
    ChartRow("ClearView RX", None, 1.67, "Clear/BlueGuard", "70 - 75", -10.00, 8.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.67, "PhotoFusion X", "70 - 75", -10.00, 8.00, 4.00, "proven"),
    ChartRow("ClearView RX", None, 1.67, "AdaptiveSun", "70 - 75", -10.00, 8.00, 4.00, "proven"),
    ChartRow("ClearView RX", None, 1.67, "POL", "75 - 55", -12.00, 11.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.67, "Clear/BlueGuard", "65 - 55", -17.00, 11.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.67, "PhotoFusion X", "65 - 50", -12.00, 8.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.67, "AdaptiveSun", "65 - 50", -12.00, 8.00, 6.00, "proven"),
    # -- 1.6 (Abbe 41; Density 1.30) -- 16 bars: only the ø80 Clear/BlueGuard
    # row was in Phase 4H/4I; the other 15 (all 5 treatments at 3 further
    # diameter zones) are newly recovered in Phase 4N.
    ChartRow("ClearView RX", None, 1.60, "Clear/BlueGuard", "80", -6.00, 6.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.60, "Clear/BlueGuard", "75", -10.00, 8.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.60, "PhotoFusion X", "75", -6.00, 8.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.60, "AdaptiveSun", "75", -6.00, 8.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.60, "POL", "75", -9.00, 8.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.60, "AdaptiveSun POL", "75", -9.00, 8.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.60, "Clear/BlueGuard", "70", -11.00, 9.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.60, "PhotoFusion X", "70", -11.00, 9.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.60, "AdaptiveSun", "70", -11.00, 9.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.60, "POL", "70", -10.50, 8.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.60, "AdaptiveSun POL", "70", -10.50, 8.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.60, "POL", "65 - 60", -11.50, 8.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.60, "AdaptiveSun POL", "65 - 60", -11.50, 8.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.60, "Clear/BlueGuard", "65 - 55", -11.00, 10.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.60, "PhotoFusion X", "65 - 55", -11.00, 10.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.60, "AdaptiveSun", "65 - 55", -11.00, 10.00, 6.00, "proven"),
    # -- Index 1.53 (Abbe 45; Density 1.11) -- 3 bars, ALL newly recovered in
    # Phase 4N: this entire index block was wholesale absent from Phase
    # 4H/4I (which had no ClearView RX rows below 1.6 at all). Clear/BlueGuard
    # only - no POL/AdaptiveSun/AdaptiveSun POL bar exists at this index.
    ChartRow("ClearView RX", None, 1.53, "Clear/BlueGuard", "75", -3.00, 7.00, 4.00, "proven"),
    ChartRow("ClearView RX", None, 1.53, "Clear/BlueGuard", "70", -4.00, 7.00, 4.00, "proven"),
    ChartRow("ClearView RX", None, 1.53, "Clear/BlueGuard", "65 - 55", -7.00, 7.00, 4.00, "proven"),
    # -- 1.5 (Abbe 58; Density 1.32) -- 13 bars, ALL newly recovered in Phase
    # 4N: this entire index block, like 1.53 above, was wholesale absent
    # from Phase 4H/4I.
    ChartRow("ClearView RX", None, 1.50, "POL", "80", -4.00, 4.00, 4.00, "proven"),
    ChartRow("ClearView RX", None, 1.50, "AdaptiveSun POL", "80", -4.00, 4.00, 4.00, "proven"),
    ChartRow("ClearView RX", None, 1.50, "Clear/BlueGuard", "75", -6.00, 4.00, 4.00, "proven"),
    ChartRow("ClearView RX", None, 1.50, "PhotoFusion X", "75", -4.00, 4.00, 4.00, "proven"),
    ChartRow("ClearView RX", None, 1.50, "AdaptiveSun", "75", -4.00, 4.00, 4.00, "proven"),
    ChartRow("ClearView RX", None, 1.50, "POL", "75", -8.00, 8.00, 4.00, "proven"),
    ChartRow("ClearView RX", None, 1.50, "AdaptiveSun POL", "75", -8.00, 8.00, 4.00, "proven"),
    ChartRow("ClearView RX", None, 1.50, "Clear/BlueGuard", "70", -8.00, 6.00, 4.00, "proven"),
    ChartRow("ClearView RX", None, 1.50, "PhotoFusion X", "70 - 50", -6.00, 6.00, 4.00, "proven"),
    ChartRow("ClearView RX", None, 1.50, "AdaptiveSun", "70 - 50", -6.00, 6.00, 4.00, "proven"),
    ChartRow("ClearView RX", None, 1.50, "POL", "70 - 50", -8.00, 8.00, 4.00, "proven"),
    ChartRow("ClearView RX", None, 1.50, "AdaptiveSun POL", "70 - 50", -8.00, 8.00, 4.00, "proven"),
    ChartRow("ClearView RX", None, 1.50, "Clear/BlueGuard", "65 - 55", -8.00, 8.00, 4.00, "proven"),
]

# ============================================================
# ClearMind - family-level chart shared by BOTH commercial tiers
# ("Individual 3" and "Superb" on the pricing page); design_tier stays None
# because the chart itself carries no tier column - never split a
# family-level range into invented tier-specific rows. Source: page 8,
# "Power range: ClearMind". 45 real source bars (44 usable as evidence, 1
# permanently excluded - see module docstring); Phase 4H/4I had captured 17
# of the 44.
# ============================================================
_CLEARMIND_ROWS: List[ChartRow] = [
    # -- 1.74 (Abbe 32; Density 1.47) -- 6 bars: 5 Phase 4H/4I, 1 newly
    # recovered (PhotoFusion X sharing the first Clear/BlueGuard row's values).
    ChartRow("ClearMind", None, 1.74, "Clear/BlueGuard", "70 - 75", -10.00, 7.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.74, "PhotoFusion X", "70 - 75", -10.00, 7.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.74, "Clear/BlueGuard", "65 - 70", -14.00, 9.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.74, "Clear/BlueGuard", "60 - 65", -15.00, 13.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.74, "Clear/BlueGuard", "55 - 60", -20.00, 16.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.74, "PhotoFusion X", "65/70 - 55/60", -14.00, 9.00, 6.00, "proven"),
    # -- 1.53 (Trivex) (Abbe 45; Density 1.11) -- 3 bars, all Phase 4H/4I.
    ChartRow("ClearMind", None, 1.53, "Clear/BlueGuard", "75/80", -3.00, 7.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.53, "Clear/BlueGuard", "70/75", -4.00, 7.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.53, "Clear/BlueGuard", "65/70 - 55/60", -7.00, 7.00, 4.00, "proven"),
    # -- 1.67 (Abbe 32; Density 1.35) -- 10 usable bars (11 real source bars;
    # the 11th is the permanently-excluded blank-diameter "Clear" bar, sph
    # -10.00/+9.50, cyl +6.00 - see module docstring, never fabricated a
    # diameter for it). 4 were Phase 4H/4I; 6 newly recovered in Phase 4N.
    ChartRow("ClearMind", None, 1.67, "Clear", "80/85", -6.00, 6.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.67, "POL", "80/85", -4.00, 4.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.67, "BlueGuard", "75/80", -10.00, 8.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.67, "BlueGuard", "70/75", -10.00, 8.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.67, "PhotoFusion X", "75/80 - 70/75", -10.00, 8.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.67, "AdaptiveSun", "75/80 - 70/75", -10.00, 8.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.67, "POL", "75/80 - 55/60", -12.00, 11.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.67, "Clear/BlueGuard", "65/70 - 50/55", -17.00, 10.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.67, "PhotoFusion X", "65/70 - 50/55", -12.00, 8.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.67, "AdaptiveSun", "65/70 - 50/55", -12.00, 8.00, 6.00, "proven"),
    # -- 1.6 (Abbe 41; Density 1.30) -- 15 bars: only the ø80/85 "Clear" row
    # was in Phase 4H/4I; the other 14 are newly recovered in Phase 4N. The
    # "ø75/80" zone's PhotoFusion X bar (between "BGuard" and "AdaptiveSun")
    # was the specific row that first undercounted in this reconstruction -
    # re-verified against the vector rect count before being recorded here.
    ChartRow("ClearMind", None, 1.60, "Clear", "80/85", -6.00, 6.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.60, "POL", "80/85", -4.00, 4.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.60, "AdaptiveSun POL", "80/85", -4.00, 4.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.60, "Clear", "75/80", -10.00, 6.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.60, "BlueGuard", "75/80", -6.00, 6.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.60, "PhotoFusion X", "75/80", -6.00, 6.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.60, "AdaptiveSun", "75/80", -6.00, 6.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.60, "Clear/BlueGuard", "70/75", -10.00, 8.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.60, "PhotoFusion X", "70/75", -10.00, 8.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.60, "AdaptiveSun", "70/75", -10.00, 8.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.60, "POL", "75/80 - 55/60", -11.00, 10.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.60, "AdaptiveSun POL", "75/80 - 55/60", -11.00, 10.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.60, "Clear/BlueGuard", "65/70 - 50/55", -10.00, 10.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.60, "PhotoFusion X", "65/70 - 50/55", -10.00, 8.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.60, "AdaptiveSun", "65/70 - 50/55", -10.00, 8.00, 6.00, "proven"),
    # -- 1.5 (Abbe 58; Density 1.32) -- 10 bars: 6 Phase 4H/4I (including
    # both anomalies), 4 newly recovered in Phase 4N.
    ChartRow("ClearMind", None, 1.50, "Clear/BlueGuard", "75/80", -4.00, 4.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.50, "PhotoFusion X", "75/80", -4.00, 4.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.50, "AdaptiveSun", "75/80", -4.00, 4.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.50, "Clear/BlueGuard", "75/80 - 50/55", -8.00, 8.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.50, "PhotoFusion X", "70/75 - 50/55", -6.00, 6.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.50, "AdaptiveSun", "70/75 - 50/55", -6.00, 6.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.50, "POL", "75/80 - 50/55", -8.00, 8.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.50, "AdaptiveSun POL", "75/80 - 50/55", -8.00, 8.00, 4.00, "proven"),
    # printed anomaly, CONFIRMED REAL by both extraction methods (not a
    # transcription error): the literal embedded PDF text at the sph_max
    # position is "-4.00" (y=460.3, x=226.9), shared as one label by both
    # the POL bar (y=455.7) and the AdaptiveSun POL bar (y=462.3) directly
    # below it - one printed typo affecting both rows, not two independent
    # misreads, but still two distinct source bars and two distinct
    # semantic rows (never compressed into one). Every structurally
    # identical row elsewhere in the chart reads "+4.00" at this position,
    # so this is very likely a genuine catalog typo - but per instruction it
    # is never silently corrected. Stays unresolved for commercial
    # persistence until ZEISS or the catalog owner confirms intent.
    ChartRow("ClearMind", None, 1.50, "POL", "80/85", -4.00, -4.00, 4.00, "review",
             "printed anomaly CONFIRMED by two independent extraction methods "
             "(rendered-image read and raw PDF text layer both read -4.00): "
             "right-side reads -4.00 where +4.00 is expected by every "
             "structurally identical row; not auto-corrected"),
    ChartRow("ClearMind", None, 1.50, "AdaptiveSun POL", "80/85", -4.00, -4.00, 4.00, "review",
             "printed anomaly CONFIRMED by two independent extraction methods "
             "(shares the POL row's printed label pair, verified via pdfplumber "
             "coordinates): right-side reads -4.00 where +4.00 is expected by "
             "every structurally identical row; not auto-corrected"),
]

# ============================================================
# SPH RX - family-level chart. Source: page 8, "Power range: SPH RX". 40
# real source bars (Phase 4N full reconstruction; Phase 4H/4I had captured
# 10 of these). No 1.74 index block exists for this family (matches the
# real commercial price list, which has no SPH RX 1.74 pricing at all).
# ============================================================
_SPH_RX_ROWS: List[ChartRow] = [
    # -- 1.67 (Abbe 32; Density 1.35) -- 7 bars: 4 Phase 4H/4I, 3 newly
    # recovered in Phase 4N.
    ChartRow("SPH RX", None, 1.67, "POL", "80", -4.00, 4.00, 4.00, "proven"),
    ChartRow("SPH RX", None, 1.67, "POL", "75 - 55", -12.00, 11.00, 6.00, "proven"),
    ChartRow("SPH RX", None, 1.67, "Clear/BlueGuard", "75", -12.00, 8.00, 6.00, "proven"),
    ChartRow("SPH RX", None, 1.67, "PhotoFusion X", "75", -12.00, 8.00, 6.00, "proven"),
    ChartRow("SPH RX", None, 1.67, "Clear/BlueGuard", "70 - 50", -12.00, 8.00, 6.00, "proven"),
    ChartRow("SPH RX", None, 1.67, "PhotoFusion X", "70 - 50", -12.00, 8.00, 6.00, "proven"),
    ChartRow("SPH RX", None, 1.67, "AdaptiveSun", "70 - 50", -12.00, 8.00, 6.00, "proven"),
    # -- 1.53 (Trivex) (Abbe 45; Density 1.11) -- 3 bars, all Phase 4H/4I.
    ChartRow("SPH RX", None, 1.53, "Clear/BlueGuard", "75", -3.00, 7.00, 4.00, "proven"),
    ChartRow("SPH RX", None, 1.53, "Clear/BlueGuard", "70", -4.00, 7.00, 4.00, "proven"),
    ChartRow("SPH RX", None, 1.53, "Clear/BlueGuard", "65 - 55", -7.00, 7.00, 4.00, "proven"),
    # -- 1.6 (Abbe 41; Density 1.30) -- 13 bars: only the ø80 POL row was in
    # Phase 4H/4I; the other 12 are newly recovered in Phase 4N.
    ChartRow("SPH RX", None, 1.60, "POL", "80", -4.00, 4.00, 4.00, "proven"),
    ChartRow("SPH RX", None, 1.60, "AdaptiveSun POL", "80", -4.00, 4.00, 4.00, "proven"),
    ChartRow("SPH RX", None, 1.60, "PhotoFusion X", "75", -6.00, 6.00, 4.00, "proven"),
    ChartRow("SPH RX", None, 1.60, "AdaptiveSun", "75", -6.00, 6.00, 4.00, "proven"),
    ChartRow("SPH RX", None, 1.60, "Clear/BlueGuard", "75 - 70", -10.00, 4.00, 6.00, "proven"),
    ChartRow("SPH RX", None, 1.60, "PhotoFusion X", "70", -10.00, 8.00, 6.00, "proven"),
    ChartRow("SPH RX", None, 1.60, "AdaptiveSun", "70", -10.00, 8.00, 6.00, "proven"),
    ChartRow("SPH RX", None, 1.60, "Clear/BlueGuard", "65 - 60", -14.00, 6.50, 6.00, "proven"),
    ChartRow("SPH RX", None, 1.60, "PhotoFusion X", "65 - 50", -10.00, 8.00, 6.00, "proven"),
    ChartRow("SPH RX", None, 1.60, "AdaptiveSun", "65 - 50", -10.00, 8.00, 6.00, "proven"),
    ChartRow("SPH RX", None, 1.60, "Clear/BlueGuard", "55 - 50", -16.00, 6.50, 6.00, "proven"),
    ChartRow("SPH RX", None, 1.60, "POL", "75 - 55", -11.00, 10.00, 6.00, "proven"),
    ChartRow("SPH RX", None, 1.60, "AdaptiveSun POL", "75 - 55", -11.00, 10.00, 6.00, "proven"),
    # -- 1.5 (Abbe 58; Density 1.32) -- 17 bars: only the ø80 "Clear" row
    # (footnote "*1.5: Not available in ø80 BlueGuard design") was in Phase
    # 4H/4I; the other 16 are newly recovered in Phase 4N.
    ChartRow("SPH RX", None, 1.50, "Clear", "80", -5.00, 4.00, 4.00, "proven"),
    ChartRow("SPH RX", None, 1.50, "POL", "80", -4.00, 4.00, 4.00, "proven"),
    ChartRow("SPH RX", None, 1.50, "AdaptiveSun POL", "80", -4.00, 4.00, 4.00, "proven"),
    ChartRow("SPH RX", None, 1.50, "Clear/BlueGuard", "75", -7.00, 6.00, 4.00, "proven"),
    ChartRow("SPH RX", None, 1.50, "PhotoFusion X", "75", -6.00, 6.50, 4.00, "proven"),
    ChartRow("SPH RX", None, 1.50, "AdaptiveSun", "75", -6.00, 6.50, 4.00, "proven"),
    ChartRow("SPH RX", None, 1.50, "Clear/BlueGuard", "70", -8.00, 9.00, 10.00, "proven"),
    ChartRow("SPH RX", None, 1.50, "PhotoFusion X", "70", -7.50, 6.50, 4.00, "proven"),
    ChartRow("SPH RX", None, 1.50, "AdaptiveSun", "70", -7.50, 6.50, 4.00, "proven"),
    ChartRow("SPH RX", None, 1.50, "Clear/BlueGuard", "65", -12.00, 10.00, 10.00, "proven"),
    ChartRow("SPH RX", None, 1.50, "PhotoFusion X", "65 - 50", -10.00, 6.50, 4.00, "proven"),
    ChartRow("SPH RX", None, 1.50, "AdaptiveSun", "65 - 50", -10.00, 6.50, 4.00, "proven"),
    ChartRow("SPH RX", None, 1.50, "POL", "75 - 50", -8.00, 8.00, 4.00, "proven"),
    ChartRow("SPH RX", None, 1.50, "AdaptiveSun POL", "75 - 50", -8.00, 8.00, 4.00, "proven"),
    ChartRow("SPH RX", None, 1.50, "Clear/BlueGuard", "60", -20.00, 14.00, 10.00, "proven"),
    ChartRow("SPH RX", None, 1.50, "Clear/BlueGuard", "55", -20.00, 20.00, 10.00, "proven"),
    ChartRow("SPH RX", None, 1.50, "Clear/BlueGuard", "50", -20.00, 23.00, 10.00, "proven"),
]

ALL_ROWS: List[ChartRow] = _CLEARVIEW_RX_ROWS + _CLEARMIND_ROWS + _SPH_RX_ROWS

# A chart row's treatment_band of "Clear/BlueGuard" means the CHART draws one
# undifferentiated bar for both - confirmed by the chart's own inline
# "Clear"/"BlueGuard"/"BGuard" text overrides elsewhere (ClearMind 1.67/1.6),
# which prove the chart DOES split them whenever their ranges actually
# differ, and only shows the merged swatch when they don't. The REAL
# commercial extraction (Phase 4J, the real SV-RX price grid) never prices
# "Clear/BlueGuard" as one identity - it always lists "Clear" and
# "BlueGuard" as two separate priced products. So an unsplit chart row is
# itself the chart's proof that the identical range applies to both real
# products - this is the same "shared axis" principle already applied to
# design_tier/coating, made explicit and auditable here rather than left as
# an implicit wildcard in the generic (manufacturer-agnostic) attach
# function. This does NOT apply to "POL"/"AdaptiveSun": those are chart-
# DISTINCT bands with DIFFERENT printed ranges, and the real commercial data
# separately merges them into one priced "Polarized / AdaptiveSun" /
# "AdaptiveSun Polarized" product - which of the two ranges (if either)
# should govern that merged commercial product is NOT decidable from this
# chart and is deliberately left unmapped rather than guessed. This is the
# ONLY compression rule at the ChartRow level (131 real bars -> 130 usable
# ChartRow entries, the 131st being the permanently-excluded blank-diameter
# bar documented in the module docstring); Clear/BlueGuard's own expansion
# into two real SKUs happens downstream, at attach time, and does not
# reduce the ChartRow count itself.
_TREATMENT_BAND_EXPANSION = {
    "Clear/BlueGuard": ("Clear", "BlueGuard"),
}

# Phase 4K/4N: the REAL SV-RX price grid (reconstructed in Phase 4J from the
# authoritative PDF via the production index-grid strategy) prices "POL" and
# "AdaptiveSun" together as ONE commercial offer literally named "Polarized /
# AdaptiveSun" - confirmed identical price_pair per (family, index, coating)
# triple, one LensVariant, one treatment_band string in the real data. The
# chart proves these two bands have DIFFERENT power ranges (different bars,
# different numbers) - this is a real grain mismatch: one price, two
# optically distinct sub-options. Never merge the ranges and never invent a
# second price: each row keeps ITS OWN range and is tagged with
# applicability_key = its original band ("POL" / "AdaptiveSun"), while the
# treatment_band used to FIND the real commercial identity is remapped to
# the actual printed name. Phase 4K originally proved this for the 4 combos
# where the (then-incomplete) chart evidence happened to carry POL/
# AdaptiveSun bands. Phase 4N's full reconstruction found POL/AdaptiveSun
# evidence at 4 further combos, so this whitelist was re-verified (a direct
# query of the real 315-row scratch DB, not inferred) and extended to every
# (family, index) where "Polarized / AdaptiveSun" is confirmed to actually
# exist as a priced LensVariant - all 8 of ClearMind/ClearView RX/SPH RX at
# 1.5 and 1.6, plus ClearMind/ClearView RX at 1.67. SPH RX at 1.67 was
# checked and confirmed to have NO "Polarized / AdaptiveSun" (or
# "AdaptiveSun Polarized") SKU at all - its two POL rows there are correctly
# left unmapped and stay in the no-real-SKU bucket, never guessed into this
# one. This is a commercial-identity lookup for an already-proven range, not
# price-driven range fabrication - the range itself comes from the chart.
_POL_ADAPTIVESUN_MERGED_OFFER = "Polarized / AdaptiveSun"
_POL_ADAPTIVESUN_REAL_COMBOS = frozenset({
    ("ClearView RX", 1.5), ("ClearView RX", 1.6), ("ClearView RX", 1.67),
    ("ClearMind", 1.5), ("ClearMind", 1.6), ("ClearMind", 1.67),
    ("SPH RX", 1.5), ("SPH RX", 1.6),
})

# Phase 4N: "AdaptiveSun POL" chart evidence maps by exact family/index scope
# to the distinct real commercial SKU "AdaptiveSun Polarized" - proven
# separately from "Polarized / AdaptiveSun" (different, higher prices at
# every matching cell; both appear as separate line items on the real
# pricing pages). This is a plain evidence-label normalization (Phase 4N
# Section 3 preference A: label rename only), not a schema change and not
# an applicability_key merge - "AdaptiveSun POL" evidence never shares a
# price with "POL" or "AdaptiveSun" evidence, so there is nothing to tag
# with applicability_key here; each "AdaptiveSun POL" row maps to its own,
# fully distinct commercial identity. Only real, priced (family, index)
# combos are included - never inferred from name similarity alone.
_ADAPTIVESUN_POL_REAL_SKU = "AdaptiveSun Polarized"
_ADAPTIVESUN_POL_REAL_COMBOS = frozenset({
    ("ClearMind", 1.5), ("ClearMind", 1.6),
    ("ClearView RX", 1.5), ("ClearView RX", 1.6),
    ("SPH RX", 1.5), ("SPH RX", 1.6),
})


def build_extracted_models(
    *, availability: str = "rx", market_scope: Optional[str] = None,
    only_confidence: Optional[str] = None,
) -> List[ExtractedLensModel]:
    """Convert the chart evidence table into ExtractedLensModel/
    ExtractedPowerRange objects, one ExtractedLensModel per family, exactly
    as app.pdf_hybrid_parser.PDFHybridParser.save_extractions_to_db expects.

    `only_confidence` (e.g. "proven") filters to rows at that confidence
    level; None (default) includes every row - "review" rows are still
    flagged via flag_review() and left review_status="needs_review" so they
    can never be silently confirmed/attached downstream.
    """
    by_family: dict[str, ExtractedLensModel] = {}
    for row in ALL_ROWS:
        if only_confidence is not None and row.confidence != only_confidence:
            continue
        model = by_family.get(row.family)
        if model is None:
            model = ExtractedLensModel(name=row.family, category="single_vision")
            by_family[row.family] = model
        bands = _TREATMENT_BAND_EXPANSION.get(row.treatment_band, (row.treatment_band,))
        for band in bands:
            # POL/AdaptiveSun single-price-offer remap (proven combos only -
            # see _POL_ADAPTIVESUN_REAL_COMBOS; e.g. SPH RX @ 1.67 is
            # deliberately excluded and stays unmapped/unattachable).
            if band in ("POL", "AdaptiveSun") and (row.family, row.index_value) in _POL_ADAPTIVESUN_REAL_COMBOS:
                real_band, applicability_key = _POL_ADAPTIVESUN_MERGED_OFFER, band
            elif band == "AdaptiveSun POL" and (row.family, row.index_value) in _ADAPTIVESUN_POL_REAL_COMBOS:
                real_band, applicability_key = _ADAPTIVESUN_POL_REAL_SKU, None
            else:
                real_band, applicability_key = band, None
            pr = ExtractedPowerRange(
                sph_min=min(row.total_power_min, row.total_power_max),
                sph_max=max(row.total_power_min, row.total_power_max),
                cyl_min=-row.max_cyl_abs,
                cyl_max=0.0,
                index_value=row.index_value,
                material=_INDEX_MATERIAL[row.index_value],
                availability=availability,
                design_tier=row.design_tier,
                treatment_band=real_band,
                applicability_key=applicability_key,
                power_eligibility="unresolved",
                market_scope=market_scope,
                has_range=True,
                total_power_min=row.total_power_min,
                total_power_max=row.total_power_max,
                max_cyl_abs=row.max_cyl_abs,
                notes=f"diameter_mm={row.diameter_zone} | source={SOURCE_PAGE}"
                      + (f" | expanded from '{row.treatment_band}'" if len(bands) > 1 else "")
                      + (f" | applicability={applicability_key} of merged offer '{real_band}'"
                         if applicability_key else "")
                      + (f" | normalized from chart label '{row.treatment_band}'"
                         if real_band == _ADAPTIVESUN_POL_REAL_SKU else ""),
            )
            if row.confidence == "review":
                pr.flag_review(row.review_reason or "graphical chart row needs independent re-verification")
            model.power_ranges.append(pr)
    return list(by_family.values())
