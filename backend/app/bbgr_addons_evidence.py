"""
BBGR (French) - "Coating" / "Tinting" page-4 add-on evidence.

Printed on page 4 of "BBGR فرنساوي.pdf" as flat surcharges layered onto an
already-priced base commercial identity, never separate base-lens products:

    Coating:
        Hard        350 EGP
        Diam's      800 EGP
        Neva Max   1300 EGP
        Neva blue  1300 EGP
        Neva Drive 1500 EGP
        Mirror     1300 EGP

    Tinting / extras:
        Tinting 1.50   200 EGP
        UV             150 EGP
        Tinting hi     250 EGP
        Prism         1000 EGP
        Tinting sample 250 EGP
        Optimiton      200 EGP

Same schema limitation already documented for Maxxee/Seiko
(maxxee_addons_evidence.py / seiko_addons_evidence.py): VariantPricing
models exactly ONE price for ONE full commercial identity; there is no
generic base+surcharge composition. Recorded here as plain evidence only -
never wired into pricing, matching, or parser dispatch of any kind.

Note: "Diam's" also appears on page 2 as a real STOCK Coating entity (e.g.
"1.56 Diam's" = 1050 EGP, an all-in commercial price for that lens+coating
combination) - that is a DIFFERENT number from this page's standalone 800
EGP surcharge, and the two must never be conflated. The STOCK row's price
is the full retail price; this page's amount is what an RX order would add
for the same coating choice.
"""

COATING = {
    "Hard": 350,
    "Diam's": 800,
    "Neva Max": 1300,
    "Neva blue": 1300,
    "Neva Drive": 1500,
    "Mirror": 1300,
}

TINTING_EXTRAS = {
    "Tinting 1.50": 200,
    "UV": 150,
    "Tinting hi": 250,
    "Prism": 1000,
    "Tinting sample": 250,
    "Optimiton": 200,
}
