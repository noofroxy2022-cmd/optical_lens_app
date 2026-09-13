"""
Seiko 2025 Retail Pricelist - "Coatings & Exception" add-on evidence.

Printed on page 5 of "Seiko_Pricelist_2025.pdf" as flat surcharges layered
onto an already-priced base commercial identity, never separate base-lens
products:

    SRC ONE      1125 EGP
    SRC SCREEN   1125 EGP
    SRC ROAD     1125 EGP
    SRC SUN      1125 EGP
    SRC ULTRA    1350 EGP
    MIRROR       2475 EGP
    TINTING      1350 EGP

Same schema limitation already documented for Maxxee
(maxxee_addons_evidence.py): VariantPricing models exactly ONE price for
ONE full commercial identity; there is no generic base+surcharge
composition. Recorded here as plain evidence only - never wired into
pricing, matching, or parser dispatch of any kind.

Note: "SRC ONE" / "SRC SCREEN" / "SRC ULTRA" also appear elsewhere in this
same catalog as resolved `Coating` entities on Seiko's own STOCK and
Freeform VariantPricing rows (e.g. "1.5 SPH / SRC - ONE / 2025") - those
are the coating CHOSEN for an already-priced lens, not this page's flat
surcharge amount, and the two must never be conflated.
"""

ADDITIONS = {
    "SRC ONE": 1125,
    "SRC SCREEN": 1125,
    "SRC ROAD": 1125,
    "SRC SUN": 1125,
    "SRC ULTRA": 1350,
    "MIRROR": 2475,
    "TINTING": 1350,
}
