"""
Synchrony By ZEISS - graphical power-range evidence (Phase 3).

Transcribed directly from the source PDF's SPH x CYL asterisk-grid charts
("Synchrony By Zeiss.pdf", pages 2-8), by counting printed cells - the same
"evidence, not parser logic" role zeiss_svrx_graphical_evidence.py plays for
ZEISS Main's own bar charts. Nothing here is matcher/schema/parser dispatch
logic; it is catalog-specific data for one document, consumed only by the
one-time Phase 3 import script. Never wired into pdf_hybrid_parser.py's
generic strategy dispatch.

Every band below is a literal reading of a printed row of asterisks: for a
minus-power grid, the row header is SPH and the column header is CYL, and a
band's cyl bound is set by however many columns (from CYL=0.00 leftmost) are
actually marked "*" on that row - never widened beyond what's printed. Where
consecutive SPH rows share the exact same CYL width, they are merged into one
band (an exact-boundary rectangle); a row whose width differs from its
neighbours becomes its own band, never approximated across the change.

Each entry: (sph_min, sph_max, cyl_min, cyl_max)
"""

# --- 1.56 AS (page 2) ---
# Minus grid: SPH 0.00 to -4.00, CYL 0.00 to -4.00, every cell filled (17x17).
# Plus & Mix grid: SPH +0.25 to +4.00, CYL 0.00 to -2.00, every cell filled (16x9).
BANDS_1_56_AS = [
    (-4.00, 0.00, -4.00, 0.00),
    (0.25, 4.00, -2.00, 0.00),
]

# --- 1.56 SPH Photo Gray (page 3) - Stock Out Of Egypt ---
# Minus grid: SPH 0.00 to -4.00, CYL 0.00 to -2.00, every cell filled (17x9).
# Plus & Mix grid: SPH +0.25 to +4.00, CYL 0.00 to -2.00, every cell filled (16x9).
BANDS_1_56_SPH_PHOTO_GRAY = [
    (-4.00, 0.00, -2.00, 0.00),
    (0.25, 4.00, -2.00, 0.00),
]

# --- 1.60 AS (pages 4-5) ---
# Minus grid (page 4): stepped -
#   SPH 0.00..-6.00   -> CYL 0.00..-4.00 (17 cols, full width)
#   SPH -6.25..-8.00  -> CYL 0.00..-3.00 (13 cols)
#   SPH -8.25..-10.00 -> CYL 0.00..-2.00 (9 cols)
# Plus & Mix grid (page 5): SPH +0.25..+6.00 -> CYL 0.00..-2.00, full width (24x9).
BANDS_1_60_AS = [
    (-6.00, 0.00, -4.00, 0.00),
    (-8.00, -6.25, -3.00, 0.00),
    (-10.00, -8.25, -2.00, 0.00),
    (0.25, 6.00, -2.00, 0.00),
]

# --- 1.67 AS, minus power only (page 8) - Stock Out Of Egypt; no plus/mix
# grid exists anywhere in the source for this SKU ---
# Stepped one row at a time from -8.25 down (column count strictly decreases
# each row), then a final flat band from -10.00 to -12.00 at cyl=0 only.
BANDS_1_67_AS_MINUS = [
    (-8.00, -2.00, -2.00, 0.00),   # rows -2.00..-8.00, 9 cols (cyl 0..-2.00)
    (-8.25, -8.25, -1.75, 0.00),   # row -8.25, 8 cols
    (-8.50, -8.50, -1.50, 0.00),   # row -8.50, 7 cols
    (-8.75, -8.75, -1.25, 0.00),   # row -8.75, 6 cols
    (-9.00, -9.00, -1.00, 0.00),   # row -9.00, 5 cols
    (-9.25, -9.25, -0.75, 0.00),   # row -9.25, 4 cols
    (-9.50, -9.50, -0.50, 0.00),   # row -9.50, 3 cols
    (-9.75, -9.75, -0.25, 0.00),   # row -9.75, 2 cols
    (-12.00, -10.00, 0.00, 0.00),  # rows -10.00..-12.00, 1 col (cyl=0 only)
]

# --- 1.60 AS Blue Protect (pages 6-7) ---
# Domain-confirmed (Phase 3C final correction): "Blue HMC+" on the page-1
# commercial price line and "Blue Protect" printed as the chart title on
# pages 6-7 are the SAME Synchrony product - "Blue Protect" is simply the
# descriptive name for the blue-light treatment, not a second product. Both
# charts are titled "1.60 AS Blue Protect" and are attached to the existing
# Blue HMC+ pricing identity (treatment_band="Blue HMC+"), never a second
# commercial identity.
# Minus grid (page 6): SPH 0.00 to -7.00, CYL 0.00 to -3.00, every cell
# filled (29x13) - one full rectangle, no stepping.
# Plus & Mix grid (page 7): SPH +0.25 to +6.00, CYL 0.00 to -2.00, every cell
# filled (24x9) - one full rectangle, no stepping.
BANDS_1_60_BLUE_PROTECT = [
    (-7.00, 0.00, -3.00, 0.00),
    (0.25, 6.00, -2.00, 0.00),
]
