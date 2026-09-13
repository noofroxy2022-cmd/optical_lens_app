"""
PIXEL catalog add-on evidence.

Printed surcharges layered onto an already-priced base commercial identity,
never separate base-lens products:

    Hi Power         +1000 EGP
    Tinting          +300 EGP
    Blue Cut Coating +1000 EGP
    Mirror Coating   +1000 EGP

Same schema limitation already documented for Maxxee/Seiko/BBGR
(maxxee_addons_evidence.py / seiko_addons_evidence.py /
bbgr_addons_evidence.py): VariantPricing models exactly ONE price for ONE
full commercial identity; there is no generic base+surcharge composition.
Recorded here as plain evidence only - never wired into pricing, matching,
or parser dispatch of any kind.

Hi Power is DIFFERENT from the other three: Tinting / Blue Cut / Mirror are
ordinary customer-choice surcharges (like every other manufacturer's
coating add-ons in this project) with no special handling needed. Hi Power
is prescription-power-dependent, but the catalog states NO numeric trigger
(no SPH/CYL/Total-Power/index threshold) - the lab/company decides at order
review whether it applies. Per the permanent domain rule (BBGR/PIXEL
correction phase), this does NOT block RX manufacturing eligibility for any
PIXEL RX row, and the base price is never hidden - but the FINAL price may
still need manual/lab confirmation. This is represented generically via
`VariantPricing.price_confirmation_note` (see models.py), set on every
current PIXEL RX pricing row (never STOCK, never any other company), never
by inventing a numeric trigger or an automatic +1000 addition.
"""

ADDITIONS = {
    "Hi Power": 1000,
    "Tinting": 300,
    "Blue Cut Coating": 1000,
    "Mirror Coating": 1000,
}

# The exact caveat text written to every current PIXEL RX
# VariantPricing.price_confirmation_note (see the PIXEL Hi Power correction
# script / test_pixel_hi_power_safety.py for how it is applied and verified).
HI_POWER_CONFIRMATION_NOTE = (
    "السعر الأساسي للزوج مؤكد من الكتالوج. قد تُضاف رسوم Hi Power (+1000 ج.م) "
    "إذا قرر المعمل أنها مطلوبة عند مراجعة الطلب — السعر النهائي يحتاج تأكيد المعمل."
)
