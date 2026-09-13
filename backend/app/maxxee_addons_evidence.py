"""
Maxxee By Hoya - "Available Additions" catalog evidence (Phase: Maxxee import).

Printed identically at the bottom of every RX page (3-8) of "Maxxee By Hoya
P.L 2025 - R-1-1.pdf":

    HMC+       850 EGP
    Blue HMC+  1300 EGP
    Tinting    850 EGP

These are ADD-ON SURCHARGES layered onto an already-priced base commercial
identity (e.g. "add HMC+ coating to this RX lens for +850"), never separate
base-lens products in their own right.

Schema limitation (confirmed during the Maxxee import's Section 1 pre-write
check): VariantPricing models exactly ONE price for ONE full commercial
identity (product + index + design + coating + availability + market +
power_scope). There is no generic "base price + additive surcharge"
composition anywhere in the schema - modeling an add-on would require either
(a) fabricating a second, duplicate base product whose only difference is
the add-on baked into its price (creates a false commercial identity that
does not exist as such in the catalog), or (b) inventing a new schema
concept (a surcharge/add-on table) that no other manufacturer's import has
ever needed and that Phase constraints explicitly forbid introducing without
a proven generic blocker spanning more than this one catalog.

Recorded here as plain evidence only - never wired into pricing, matching,
or parser dispatch of any kind. A future generic "additive pricing" schema
feature (if ever justified by more than one manufacturer needing it) would
read from data like this; today, nothing consumes it.
"""

ADDITIONS = {
    "HMC+": 850,
    "Blue HMC+": 1300,
    "Tinting": 850,
}
