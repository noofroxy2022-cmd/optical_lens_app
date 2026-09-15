"""
SCOPE catalog add-on evidence.

Printed surcharges layered onto an already-priced base commercial identity,
never separate base-lens products. The price-table header explicitly reads
"Scope Rx Lenses FreeForm - (Hard Coated)" - Hard Coat is already included in
every printed base price on every SCOPE.pdf price page; these add-ons are
optional, customer-selected extras on top of that Hard-Coated base, never
automatically composed into it.

Same schema limitation already documented for Maxxee/Seiko/BBGR/PIXEL
(maxxee_addons_evidence.py / seiko_addons_evidence.py / bbgr_addons_evidence.py
/ pixel_addons_evidence.py): VariantPricing models exactly ONE price for ONE
full commercial identity; there is no generic base+surcharge composition.
Recorded here as plain evidence only - never wired into pricing, matching, or
parser dispatch of any kind. No VariantPricing row is ever created from these
values, and none is ever added to a base price automatically.

Final-price principle (never automated): final = base printed price + only
the optional additions the customer actually selects.
"""

COATING_ADDITIONS = {
    "HMC": 250,
    "IRIDIO Plus": 500,
    "PRO-DRIVE": 600,
    "MIRROR": 350,
}

LENS_SERVICE_ADDITIONS = {
    "Sun Tinting (Plastic 1.5-1.56)": 350,
    "Sun Tinting (Plastic 1.6/1.67)": 450,
    "Sun Tinting (Glass)": 500,
    "Prism up to 5 Diopters": 450,
    "Prism up to 10 Diopters": 500,
}

ADDITIONS = {**COATING_ADDITIONS, **LENS_SERVICE_ADDITIONS}
