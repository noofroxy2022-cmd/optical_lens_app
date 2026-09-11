"""
Phase 4H/4I: ZEISS Single Vision RX graphical power-range evidence.

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

TWO INDEPENDENT EXTRACTION PASSES, by two genuinely different methods:
  Pass 1 (Phase 4H): visual reading of the page rendered to a raster image
    (pypdfium2), bar colors identified by eye against each section's own
    printed legend.
  Pass 2 (Phase 4I): structured extraction straight from the PDF's own object
    model via pdfplumber - page.extract_words() for every printed number/
    label with exact coordinates, and page.rects for every bar's exact
    non_stroking_color (a CMYK 4-tuple) and (x0,x1) extent. This is not a
    pixel/rendering-based method at all, so it cannot share Pass 1's
    rendering or eyeballing artifacts. Legend association was proven
    structurally, not by color similarity alone: the ClearMind legend row's
    5 swatches are pdfplumber rects whose own (x0,x1) sit immediately before
    their own text label (e.g. a (0.0,0.0,0.0,0.148)-fill rect at x=112.8-
    121.2 immediately followed by the word "Clear/BlueGuard" at x=123.5) -
    label + spatial adjacency, not color in isolation. The same 5 CMYK
    values (and no others, bar-artifact one-off gradients aside) are the
    only bar fill colors used anywhere on the page, including in the
    ClearView RX and SPH RX sections that print no legend of their own -
    i.e. those sections reuse the ClearMind legend's own proven color
    definitions, not a merely similar-looking palette.
  Where both passes agree with high confidence, the row is "proven". Where
  they cannot be reconciled with high confidence, it stays "review"
  (unresolved) - per instruction, a printed value is never "corrected"
  toward whatever looks more logical.

  Side finding from Pass 2: ClearView RX and SPH RX's sections render every
  index header, "sph"/"cyl" column label, and (usually) each number TWICE at
  two slightly offset x-positions - a duplicate-text-layer artifact in the
  source PDF (visible in Pass 1 too, as garbled overlapping digits like
  "+6-.60.000"). Both copies always carry the same value, so it is a
  rendering redundancy, not conflicting evidence; likely also why these two
  sections print no legend row of their own.

CONFIDENCE POLICY (do not weaken without re-verifying against the source):
  - "proven": both extraction passes agree with high confidence. Safe to
    review-confirm and commercially attach.
  - "review": a genuine, still-unresolved anomaly, or a value that cannot be
    read with high confidence by either method. Captured as evidence (raw
    label, page, diameter, treatment preserved) but NEVER confirmed/attached;
    power_eligibility stays irrelevant / not-yet-eligible until a human
    resolves it. Intentional under-coverage, not a bug.

One concrete anomaly remains, CONFIRMED REAL by both extraction passes
(same printed value each time - this is not a misread):
  - ClearMind 1.5, diameter 80/85, POL & AdaptiveSun POL bars (which share
    one printed label pair): the right-hand number is printed as "-4.00"
    where every structurally identical row elsewhere in the chart prints
    "+4.00". pdfplumber confirms the literal embedded text is "-4.00" at
    the expected sph_max position - so this is very likely a genuine catalog
    typo, not a transcription error, but per instruction it is never
    silently corrected to "+4.00". Stays "review" / unresolved for
    commercial persistence until ZEISS or the catalog owner confirms intent.

The other 9 originally-flagged rows were independently re-verified via Pass
2 and PROMOTED to "proven" (see per-row comments below for the exact
pdfplumber evidence): the 4 ClearMind 1.67 inline Clear/BlueGuard-split rows,
1 ClearMind 1.6 inline split row, 1 ClearView RX 1.6 dense-block row, 1
SPH RX 1.6 dense-block row, and 1 SPH RX 1.5 footnote-exclusion row (whose
sph_max was not printed directly beside its own bar but is a label shared
with the row below, per the same shared-label convention independently
confirmed elsewhere in this chart, corroborated by the bar's own left/right
pixel-width ratio implying the same value).

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
# RX has no "Individual 3 / Superb" split like ClearMind does), single legend
# shared with ClearMind/SPH RX on the same page. Source: page 8, "Power
# range: ClearView RX".
# ============================================================
_CLEARVIEW_RX_ROWS: List[ChartRow] = [
    # -- 1.74 (Abbe 32; Density 1.47) --
    ChartRow("ClearView RX", None, 1.74, "Clear/BlueGuard", "70", -12.00, 9.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.74, "PhotoFusion X", "70", -10.00, 9.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.74, "Clear/BlueGuard", "65", -15.00, 13.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.74, "Clear/BlueGuard", "60 - 55", -20.00, 16.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.74, "PhotoFusion X", "65 - 55", -14.00, 11.25, 6.00, "proven"),
    # -- 1.67 (Abbe 32; Density 1.35) --
    # footnote: "*1.67, 1.6: ø80 not available in BlueGuard design" -> Clear only at ø80
    ChartRow("ClearView RX", None, 1.67, "Clear", "80", -6.00, 6.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.67, "POL", "80", -4.00, 4.00, 4.00, "proven"),
    ChartRow("ClearView RX", None, 1.67, "Clear/BlueGuard", "70 - 75", -10.00, 8.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.67, "AdaptiveSun", "70 - 75", -10.00, 8.00, 4.00, "proven"),
    ChartRow("ClearView RX", None, 1.67, "POL", "75 - 55", -12.00, 11.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.67, "Clear/BlueGuard", "65 - 55", -17.00, 11.00, 6.00, "proven"),
    ChartRow("ClearView RX", None, 1.67, "AdaptiveSun", "65 - 50", -12.00, 8.00, 6.00, "proven"),
    # -- 1.6: pdfplumber pass 2 confirms (y~289-311, x~475-605): bar
    # non_stroking_color=(0,0,0,0.148)="Clear/BlueGuard" per the ClearMind
    # legend swatch; text "-6.00"/"+6.00" (dup. at two x-offsets, a known
    # ClearView RX/SPH RX rendering duplication - both copies agree) and
    # cyl "+6.00". Matches pass 1 exactly - PROVEN.
    ChartRow("ClearView RX", None, 1.60, "Clear/BlueGuard", "80", -6.00, 6.00, 6.00, "proven"),
]

# ============================================================
# ClearMind - family-level chart shared by BOTH commercial tiers
# ("Individual 3" and "Superb" on the pricing page); design_tier stays None
# because the chart itself carries no tier column - never split a
# family-level range into invented tier-specific rows. Source: page 8,
# "Power range: ClearMind".
# ============================================================
_CLEARMIND_ROWS: List[ChartRow] = [
    # -- 1.74 (Abbe 32; Density 1.47) --
    ChartRow("ClearMind", None, 1.74, "Clear/BlueGuard", "70 - 75", -10.00, 7.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.74, "Clear/BlueGuard", "65 - 70", -14.00, 9.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.74, "Clear/BlueGuard", "60 - 65", -15.00, 13.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.74, "Clear/BlueGuard", "55 - 60", -20.00, 16.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.74, "PhotoFusion X", "65/70 - 55/60", -14.00, 9.00, 6.00, "proven"),
    # -- 1.53 (Trivex) (Abbe 45; Density 1.11) --
    ChartRow("ClearMind", None, 1.53, "Clear/BlueGuard", "75/80", -3.00, 7.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.53, "Clear/BlueGuard", "70/75", -4.00, 7.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.53, "Clear/BlueGuard", "65/70 - 55/60", -7.00, 7.00, 4.00, "proven"),
    # -- 1.67, 1.6: inline "Clear"/"BlueGuard"/"BGuard" text overrides on top
    # of the shared swatch. pdfplumber pass 2 (y=214-340 region) confirms
    # every one of these 5 rows exactly: each bar's own row carries its own
    # printed diameter label, inline treatment word (kerned but unambiguous,
    # e.g. "Blue"+"G"+"u"+"a"+"rd" -> "BlueGuard"), sph-min, sph-max and cyl
    # value, with no fragment shared with an adjacent row. Matches pass 1
    # exactly on all 5 - PROVEN.
    ChartRow("ClearMind", None, 1.67, "Clear", "80/85", -6.00, 6.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.67, "POL", "80/85", -4.00, 4.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.67, "BlueGuard", "75/80", -10.00, 8.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.67, "BlueGuard", "70/75", -10.00, 8.00, 6.00, "proven"),
    ChartRow("ClearMind", None, 1.6, "Clear", "80/85", -6.00, 6.00, 6.00, "proven"),
    # NOTE (new finding from pass 2, not part of the original 10): the chart
    # also contains a further ClearMind 1.67 row - a "Clear" bar reading
    # sph -10.00/+9.50, cyl +6.00 - whose diameter cell is genuinely blank in
    # the source PDF's own text layer (not just illegible in the render): no
    # word object exists there at all. This is source-level ambiguity, not a
    # reading failure, and is intentionally left OUT of this evidence table
    # (never fabricated a diameter for it) rather than added as "review" -
    # a future pass may add it once its diameter is confirmed by other means
    # (e.g. contacting ZEISS).
    # -- 1.5 (Abbe 58; Density 1.32) --
    ChartRow("ClearMind", None, 1.50, "PhotoFusion X", "75/80", -4.00, 4.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.50, "AdaptiveSun", "75/80", -4.00, 4.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.50, "Clear/BlueGuard", "75/80 - 50/55", -8.00, 8.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.50, "PhotoFusion X", "70/75 - 50/55", -6.00, 6.00, 4.00, "proven"),
    ChartRow("ClearMind", None, 1.50, "AdaptiveSun", "70/75 - 50/55", -6.00, 6.00, 4.00, "proven"),
    # printed anomaly, CONFIRMED REAL by pdfplumber pass 2 (not a transcription
    # error): the literal embedded PDF text at the sph_max position is
    # "-4.00" (y=460.3, x=226.9), shared as one label by both the POL bar
    # (y=455.7) and the AdaptiveSun POL bar (y=462.3) directly below it -
    # one printed typo affecting both rows, not two independent misreads.
    # Every structurally identical row elsewhere in the chart reads "+4.00"
    # at this position, so this is very likely a genuine catalog error - but
    # per instruction it is never silently corrected. Stays unresolved for
    # commercial persistence until ZEISS or the catalog owner confirms intent.
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
# SPH RX - family-level chart. Source: page 8, "Power range: SPH RX".
# ============================================================
_SPH_RX_ROWS: List[ChartRow] = [
    # -- 1.67 (Abbe 32; Density 1.35) --
    ChartRow("SPH RX", None, 1.67, "POL", "80", -4.00, 4.00, 4.00, "proven"),
    ChartRow("SPH RX", None, 1.67, "POL", "75 - 55", -12.00, 11.00, 6.00, "proven"),
    ChartRow("SPH RX", None, 1.67, "PhotoFusion X", "75", -12.00, 8.00, 6.00, "proven"),
    ChartRow("SPH RX", None, 1.67, "Clear/BlueGuard", "70 - 50", -12.00, 8.00, 6.00, "proven"),
    # -- 1.53 (Trivex) (Abbe 45; Density 1.11) --
    ChartRow("SPH RX", None, 1.53, "Clear/BlueGuard", "75", -3.00, 7.00, 4.00, "proven"),
    ChartRow("SPH RX", None, 1.53, "Clear/BlueGuard", "70", -4.00, 7.00, 4.00, "proven"),
    ChartRow("SPH RX", None, 1.53, "Clear/BlueGuard", "65 - 55", -7.00, 7.00, 4.00, "proven"),
    # -- 1.6: pdfplumber pass 2 confirms (y=225-232, x~783-925): POL bar,
    # diameter "80" (doubled per the section's rendering-duplication quirk,
    # both copies agree), sph -4.00/+4.00, cyl +4.00. Matches pass 1 - PROVEN.
    ChartRow("SPH RX", None, 1.60, "POL", "80", -4.00, 4.00, 4.00, "proven"),
    # -- 1.5: footnote "*1.5: Not available in ø80 BlueGuard design" -> Clear
    # only at ø80. pdfplumber pass 2 (y=375-389) confirms sph_min=-5.00
    # printed directly beside this bar; sph_max=+4.00 is not printed beside
    # THIS bar specifically but is the label immediately below (shared with
    # the POL row at the same diameter, y=384.1) - the same shared-label
    # convention independently confirmed elsewhere in this chart (e.g.
    # ClearMind 1.67's "-10.00" shared by BlueGuard/Clear) - and is
    # corroborated by this bar's own left/right pixel-width ratio
    # (18.0 : 14.4 units either side of the zero line implies ~5.00 : ~4.00).
    # Two independent corroborating signals agree - PROVEN.
    ChartRow("SPH RX", None, 1.50, "Clear", "80", -5.00, 4.00, 4.00, "proven"),
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
# chart and is deliberately left unmapped rather than guessed.
_TREATMENT_BAND_EXPANSION = {
    "Clear/BlueGuard": ("Clear", "BlueGuard"),
}


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
            pr = ExtractedPowerRange(
                sph_min=min(row.total_power_min, row.total_power_max),
                sph_max=max(row.total_power_min, row.total_power_max),
                cyl_min=-row.max_cyl_abs,
                cyl_max=0.0,
                index_value=row.index_value,
                material=_INDEX_MATERIAL[row.index_value],
                availability=availability,
                design_tier=row.design_tier,
                treatment_band=band,
                power_eligibility="unresolved",
                market_scope=market_scope,
                has_range=True,
                total_power_min=row.total_power_min,
                total_power_max=row.total_power_max,
                max_cyl_abs=row.max_cyl_abs,
                notes=f"diameter_mm={row.diameter_zone} | source={SOURCE_PAGE}"
                      + (f" | expanded from '{row.treatment_band}'" if len(bands) > 1 else ""),
            )
            if row.confidence == "review":
                pr.flag_review(row.review_reason or "graphical chart row needs independent re-verification")
            model.power_ranges.append(pr)
    return list(by_family.values())
