"""Permanent regression coverage for the SCOPE canonical import.

Deliberately synthetic, mirroring the corrected shape directly via the ORM
(no PDF parsing, no dependency on the live optical_lens.db), matching the
same pattern as test_platinum_import.py / test_divel_import.py.

SCOPE is RX/Manufacturing ONLY - the catalog has no Stock section at all
(confirmed page-by-page across all 16 pages). Every commercial section is a
design-column x row-identity price matrix, audited cell-by-cell from the
visually-rendered PDF (pypdfium2, since poppler/pdftoppm was unavailable):
dashes/absent rows are never filled, merged, or inferred - only real numeric
cells become VariantPricing rows.

No PowerRange is created for any SCOPE row EXCEPT Myoblock, which prints an
explicit manufacturing limit (SCOPE.pdf p.15: SPH -0.50 to -10.00, CYL
magnitude 4.00) - the sole catalog-proven exception to the permanent
RX-no-PowerRange-by-default rule. Every other RX row (491 non-Myoblock rows +
0 Stock rows) carries no PowerRange and remains manufacturing-eligible for
any prescription, per that same permanent rule.

Base printed prices already include Hard Coat (price-table header: "Scope Rx
Lenses FreeForm - (Hard Coated)"). HMC/IRIDIO Plus/PRO-DRIVE/MIRROR and the
other printed optional services are recorded as plain evidence in
app/scope_addons_evidence.py (mirroring pixel_addons_evidence.py's existing
pattern) - never as VariantPricing rows, never composed into any base price.

Material truth: every row explicitly printed as Glass/White Glass/Photo
Glass uses MaterialType.GLASS (migration c9d8e7f6a5b4) - never CR39 or any
other plastic value. GLASS was added as a new, purely additive enum member
after confirming no existing enum value, neutral OTHER/UNKNOWN value, or
nullable path could represent it truthfully (material is NOT NULL and the
enum previously had no glass option at all). design_variant="Glass" is kept
alongside it as a secondary, human-readable evidence tag, not a substitute.
"""
import os
import sys
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database import Base  # noqa: E402
from app import models, database, schemas, product_search, crud  # noqa: E402
from app.scope_addons_evidence import ADDITIONS as SCOPE_ADDITIONS  # noqa: E402


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


def _mk_company(db, name):
    co = models.Company(name=name, country="EG", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    return co


def _mk_catalog(db, company):
    cat = models.Catalog(company_id=company.id, filename="synthetic.pdf",
                         file_path="synthetic.pdf", status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)
    return cat


def _mk_model(db, company, name, category):
    m = models.LensModel(company_id=company.id, name=name, category=category)
    db.add(m); db.commit(); db.refresh(m)
    return m


def _mk_variant(db, model, index_value, *, material=models.MaterialType.CR39,
                treatment_band=None, design_variant=None):
    v = models.LensVariant(
        lens_model_id=model.id, material=material, index_value=index_value,
        design_type=models.DesignType.SPHERICAL, is_aspherical=False,
        design_variant=design_variant, treatment_band=treatment_band, price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    return v


def _mk_pricing(db, variant, catalog, *, price):
    vp = models.VariantPricing(
        variant_id=variant.id, availability=models.PricingAvailability.RX,
        price_pair=Decimal(str(price)), currency="EGP", source_catalog_id=catalog.id)
    db.add(vp); db.commit(); db.refresh(vp)
    return vp


def _mk_range(db, model, variant, pricing, *, sph_min, sph_max, cyl_min, cyl_max, notes=None):
    pr = models.PowerRange(lens_model_id=model.id, variant_id=variant.id, pricing_id=pricing.id,
                           sph_min=sph_min, sph_max=sph_max, cyl_min=cyl_min, cyl_max=cyl_max, notes=notes)
    db.add(pr); db.commit()
    return pr


def _mk_presc(db, sph, cyl=0.0, name="p"):
    p = models.Prescription(
        customer_name=name, od_sph_original=sph, od_cyl_original=cyl, od_axis_original=0,
        od_sph=sph, od_cyl=cyl, od_axis=0, os_sph_original=sph, os_cyl_original=cyl,
        os_axis_original=0, os_sph=sph, os_cyl=cyl, os_axis=0, pd=63)
    db.add(p); db.commit(); db.refresh(p)
    return p


ROW26 = [
    ("R01", 1.50, None), ("R02", 1.56, "Semi-Compressed"), ("R03", 1.61, "Compressed"),
    ("R04", 1.67, "Compressed"), ("R05", 1.74, "Non Water-Tintable Thin"),
    ("R06", 1.56, "Relax Blue Light (Semi-Compressed)"),
    ("R07", 1.56, "Relax HeatGuard Blue Light (Semi-Compressed)"),
    ("R08", 1.61, "Relax Blue Light"), ("R09", 1.61, "Relax Blue+Yellow Light Contrast"),
    ("R10", 1.67, "Relax Blue Light"), ("R11", 1.74, "Relax Blue Light"),
    ("R12", 1.56, "HiFlex Impact-Resistant"),
    ("R13", 1.56, "HiFlex Relax Impact-Resistant Blue Light"),
    ("R14", 1.50, "Transitions Gray-Brown"),
    ("R15", 1.56, "PhotoGray Multi-color (7 shades)"),
    ("R16", 1.56, "Transitions PhotoGray-Brown Surface Coloring"),
    ("R17", 1.67, "Transitions PhotoGray Surface Coloring"),
    ("R18", 1.56, "Transitions Relax Gray-Brown Blue Light"),
    ("R19", 1.67, "Transitions Relax Gray-Brown Blue Light"),
    ("R20", 1.74, "Transitions Relax Gray-Brown Blue Light VV"),
    ("R21", 1.56, "HiFlex PhotoGray Impact-Resistant"),
    ("R22", 1.56, "HiFlex PhotoGray Relax Impact-Resistant Blue Light"),
    ("R23", 1.50, "Sun Gray with Revo Mirror (Blue/Silver/Gold)"),
    ("R24", 1.50, "Sun Gray"), ("R25", 1.50, "Sun Polarized Gray-Brown-Green"),
    ("R26", 1.61, "Night Rider (Blue+Yellow Light, Day/Night Driving)"),
]
GLASS4 = [
    ("GLASS27", 1.52, "White Glass"), ("GLASS28", 1.70, "White Glass Compressed"),
    ("GLASS29", 1.80, "White Glass Compressed"),
    ("PHOTOGLASS30", 1.52, "Photo Glass (PhotoGray-Brown Extra Corning French)"),
]

PROG_PRICES = {
    "Gold": {"R01": 2650, "R02": 2870, "R03": 3960, "R04": 4600, "R05": 7220,
             "R06": 3080, "R07": 3330, "R08": 4600, "R09": 4830, "R10": 7660, "R11": 4170,
             "R12": 4600, "R13": 6800, "R14": 3960, "R15": 4830, "R16": 6790, "R17": 5260,
             "R18": 7440, "R19": 9250, "R20": 6790, "R21": 8530, "R22": 3490,
             "R23": 3300, "R24": 3960, "R25": 4700, "R26": 2660,
             "GLASS27": 3270, "GLASS28": 4140, "GLASS29": 3880, "PHOTOGLASS30": None},
    "Silver": {"R01": 1990, "R02": 2210, "R03": 3300, "R04": 3960, "R05": 6570,
               "R06": 2430, "R07": 2670, "R08": 4170, "R09": 4170, "R10": 7000, "R11": 3520,
               "R12": 3960, "R13": 6130, "R14": 3300, "R15": 4170, "R16": 6130, "R17": 4600,
               "R18": 6800, "R19": 8800, "R20": 6130, "R21": 7880, "R22": 2840,
               "R23": 2650, "R24": 3300, "R25": 4050, "R26": 2000,
               "GLASS27": 2600, "GLASS28": 3500, "GLASS29": 3230, "PHOTOGLASS30": 2800},
    "Bronze": {"R01": 1560, "R02": 1775, "R03": 2865, "R04": 3520, "R05": 6130,
               "R06": 1990, "R07": 2240, "R08": 3080, "R09": 3740, "R10": 3740, "R11": 6570,
               "R12": 3080, "R13": 3520, "R14": 5700, "R15": 2865, "R16": 3740, "R17": 5700,
               "R18": 4170, "R19": 6350, "R20": 8500, "R21": 5700, "R22": 7440,
               "R23": 2400, "R24": 2200, "R25": 2870, "R26": 3600,
               "GLASS27": 1570, "GLASS28": 2180, "GLASS29": 3050, "PHOTOGLASS30": None},
    "Adler HD": {"R01": 5480, "R02": 5700, "R03": 6790, "R04": 7440, "R05": 10050,
                 "R06": 5900, "R07": 6160, "R08": 7660, "R09": 7660, "R10": 10490, "R11": 7000,
                 "R12": 7440, "R13": 9620, "R14": 6790, "R15": 7660, "R16": 9620, "R17": 8100,
                 "R18": 10280, "R19": 11650, "R20": 9620, "R21": 11360, "R22": 6300,
                 "R23": 6140, "R24": 6790, "R25": 7530, "R26": None,
                 "GLASS27": None, "GLASS28": None, "GLASS29": None, "PHOTOGLASS30": None},
    "Eagle": {"R01": 4600, "R02": 4830, "R03": 5900, "R04": 6600, "R05": 9180,
              "R06": 5050, "R07": 5290, "R08": 6790, "R09": 6790, "R10": 9600, "R11": 6140,
              "R12": 6580, "R13": 8750, "R14": 5900, "R15": 6790, "R16": 8750, "R17": 7230,
              "R18": 9400, "R19": 10600, "R20": 8750, "R21": 10490, "R22": 5450,
              "R23": 5260, "R24": 5900, "R25": 6660, "R26": 4620,
              "GLASS27": 5230, "GLASS28": 6100, "GLASS29": 5840, "PHOTOGLASS30": 4980},
    "4k Original": {"R01": 3740, "R02": 3960, "R03": 5040, "R04": 5700, "R05": 8300,
                    "R06": 4170, "R07": 4420, "R08": 5260, "R09": 5900, "R10": 5900, "R11": 8750,
                    "R12": 5260, "R13": 5700, "R14": 7880, "R15": 5040, "R16": 5900, "R17": 7880,
                    "R18": 6350, "R19": 8540, "R20": 10000, "R21": 7880, "R22": 9600,
                    "R23": 4580, "R24": 4400, "R25": 5050, "R26": 5780,
                    "GLASS27": 3750, "GLASS28": 4360, "GLASS29": 5240, "PHOTOGLASS30": None},
    "Dual Free": {"R01": 8970, "R02": 9400, "R03": 11580, "R04": 13320, "R05": 18900,
                  "R06": 9840, "R07": 10080, "R08": 13320, "R09": 13320, "R10": 19500, "R11": 12000,
                  "R12": 12900, "R13": 17240, "R14": 11580, "R15": 12450, "R16": 18110, "R17": 14000,
                  "R18": 18500, "R19": 22750, "R20": 17240, "R21": 20730, "R22": 10890,
                  "R23": 10700, "R24": 11580, "R25": 13060, "R26": None},
    "Weitblick": {"R01": 5900, "R02": 6130, "R03": 7220, "R04": 7880, "R05": 10490,
                 "R06": 6350, "R07": 6600, "R08": 7440, "R09": 8100, "R10": 8100, "R11": 10900,
                 "R12": 7440, "R13": 7880, "R14": 10050, "R15": 7220, "R16": 8100, "R17": 10050,
                 "R18": 8530, "R19": 10700, "R20": 12250, "R21": 10050, "R22": 11800,
                 "R23": 6750, "R24": 6570, "R25": 7220, "R26": 7960},
    "MetaVision": {"R01": 19850, "R02": 20300, "R03": 22000, "R04": 24200, "R05": 28500,
                  "R06": 22000, "R07": 22280, "R08": 24200, "R09": 26400, "R10": 26400, "R11": 30700,
                  "R12": 24200, "R13": 26400, "R14": 32900, "R15": 24200, "R16": 24600, "R17": 27700,
                  "R18": 27700, "R19": 29450, "R20": 36250, "R21": 28130, "R22": 29450,
                  "R23": 21780, "R24": 21400, "R25": 22470, "R26": 23960},
}

BIFOCAL_ROWS = list(ROW26)
BIFOCAL_ROWS.insert(15, ("R15B", 1.56, "Blue/Yellow/Green/Purple/Rose"))
BIFOCAL_PRICES = {
    "Flat Top 45": {"R01": 2860},
    "Flat Top 28 FreeFocal": {"R02": 1780, "R15": 3300},
    "Flat Top 28 Double Aspheric": {"R02": 1340, "R15": 2850},
    "Flat Top 28 Toric": {"R02": 1120, "R15": 2650},
    "New BiFocal Weitblick": {
        "R01": 1880, "R02": 2050, "R03": 3015, "R04": 3670, "R05": 6410,
        "R06": 2280, "R07": 2520, "R08": 3230, "R09": 3880, "R10": 3880, "R11": 6840,
        "R12": 3370, "R13": 3800, "R14": 5980, "R15": 3360, "R15B": 3360, "R16": 4230, "R17": 5970,
        "R18": 4450, "R19": 6400, "R20": 8700, "R21": 5970, "R22": 7720,
        "R23": 2670, "R24": 2490, "R25": 3150, "R26": 3880,
    },
    "New BiFocal 4k": {
        "R01": 1370, "R02": 1540, "R03": 2500, "R04": 3150, "R05": 5900,
        "R06": 1760, "R07": 2010, "R08": 2715, "R09": 3370, "R10": 3370, "R11": 6320,
        "R12": 2850, "R13": 3280, "R14": 5480, "R15": 2850, "R15B": 2850, "R16": 3720, "R17": 5470,
        "R18": 3940, "R19": 5900, "R20": 8150, "R21": 5460, "R22": 7180,
        "R23": 2150, "R24": 1980, "R25": 2630, "R26": 3370,
    },
}

OFFICE_ROWS = ROW26[:13]
OFFICE_PRICES = {
    "Doctor": {"R01": 1430, "R02": 1560, "R03": 2650, "R04": 3090, "R05": 5260,
               "R06": 1780, "R07": 2030, "R08": 2870, "R09": 3740, "R10": 3740, "R11": 5900,
               "R12": 2400, "R13": 2880},
    "Officestar": {"R01": 2020, "R02": 2150, "R03": 3250, "R04": 3680, "R05": 5850,
                   "R06": 2370, "R07": 2620, "R08": 3460, "R09": 4330, "R10": 4330, "R11": 6500,
                   "R12": 2990, "R13": 3460},
}

YOUNG_PRICES = {
    "Shabab": {"R01": 1390, "R02": 1560, "R03": 2520, "R04": 3170, "R05": 5900,
               "R06": 1780, "R07": 2030, "R08": 2740, "R09": 3390, "R10": 3390, "R11": 6350,
               "R12": 2870, "R13": 3300, "R14": 5580, "R15": 2870, "R16": 3740, "R17": 5480,
               "R18": 3950, "R19": 5900, "R20": 8200, "R21": 5480, "R22": 7220,
               "R23": 2180, "R24": 1990, "R25": 2650, "R26": 3400},
}

SV_GLASS1 = [("GLASS_SV", 1.80, "White Glass Compressed")]
SV_PRICES = {
    "Double Aspheric": {"R01": 1170, "R02": 1340, "R03": 2300, "R04": 2950, "R05": 5700,
                        "R06": 1560, "R07": 1800, "R08": 2500, "R09": 3170, "R10": 3170, "R11": 6130,
                        "R12": 2650, "R13": 3090, "R14": 5260, "R15": 2650, "R16": 3500, "R17": 5260,
                        "R18": 3740, "R19": 5700, "R20": 7900, "R21": 5260, "R22": 7000,
                        "R23": 1960, "R24": 1780, "R25": 2440, "R26": 3170, "GLASS_SV": 2500},
    "Toric": {"R01": 950, "R02": 1120, "R03": 2080, "R04": 2740, "R05": 5480,
              "R06": 1340, "R07": 1590, "R08": 2300, "R09": 2950, "R10": 2950, "R11": 5900,
              "R12": 2430, "R13": 2870, "R14": 5050, "R15": 2440, "R16": 3300, "R17": 5050,
              "R18": 3500, "R19": 5480, "R20": 7750, "R21": 5050, "R22": 6790,
              "R23": 1750, "R24": 1560, "R25": 2200, "R26": 2950, "GLASS_SV": 2300},
    "Weitblick": {"R01": 2040, "R02": 2220, "R03": 3170, "R04": 3840, "R05": 6570,
                 "R06": 2430, "R07": 2680, "R08": 3400, "R09": 4050, "R10": 4050, "R11": 7000,
                 "R12": 3500, "R13": 3950, "R14": 6130, "R15": 3500, "R16": 4500, "R17": 6130,
                 "R18": 4600, "R19": 6570, "R20": 8200, "R21": 6130, "R22": 7880,
                 "R23": 2830, "R24": 2650, "R25": 3300, "R26": 4050},
    "FreeFocal": {"R01": 1400, "R02": 1560, "R03": 2520, "R04": 3170, "R05": 5900,
                  "R06": 1780, "R07": 2030, "R08": 2740, "R09": 3400, "R10": 3400, "R11": 6350,
                  "R12": 2870, "R13": 3300, "R14": 5480, "R15": 2870, "R16": 3740, "R17": 5480,
                  "R18": 3950, "R19": 5900, "R20": 8050, "R21": 5480, "R22": 7220,
                  "R23": 2180, "R24": 1990, "R25": 2650, "R26": 3400},
    "MetaVision": {"R01": 3950, "R02": 4400, "R03": 6130, "R04": 7440, "R05": 12900,
                  "R06": 4600, "R07": 4850, "R08": 6580, "R09": 7880, "R10": 7880, "R11": 13750,
                  "R12": 6790, "R13": 7660, "R14": 12000, "R15": 8500, "R16": 8970, "R17": 12000,
                  "R18": 9000, "R19": 12880, "R20": 19750, "R21": 12000, "R22": 15500,
                  "R23": 5660, "R24": 5290, "R25": 5050, "R26": 7650},
}

EXTREME_ROWS = [
    ("E1", 1.67, "Compressed, Water-Tintable"), ("E2", 1.74, "Compressed"),
    ("E3", 1.67, "Relax Blue Light"), ("E4", 1.74, "Relax Blue Light"),
    ("E5", 1.67, "Transitions PhotoGray Surface Coloring"),
    ("E6", 1.67, "Transitions Relax PhotoGray-Brown Surface"),
    ("E7", 1.74, "Transitions Relax PhotoGray Surface"),
]
EXTREME_PRICES = {"Extreme": {"E1": 3840, "E2": 6580, "E3": 4040, "E4": 7000,
                              "E5": 6130, "E6": 6580, "E7": 8200}}

MYOBLOCK_ROWS = [
    ("M01", 1.50, None), ("M02", 1.56, "Semi-Compressed"), ("M03", 1.61, "Compressed"),
    ("M04", 1.67, "Compressed"), ("M05", 1.74, "Non Water-Tintable Thin"),
    ("M06", 1.56, "Relax Blue Light (Semi-Compressed)"), ("M07", 1.61, "Relax Blue Light"),
    ("M08", 1.61, "Relax Blue+Yellow Light Contrast"), ("M09", 1.67, "Relax Blue Light"),
    ("M10", 1.74, "Relax Blue Light"), ("M11", 1.56, "HiFlex Impact-Resistant"),
    ("M12", 1.50, "Transitions Gray-Brown"),
    ("M13", 1.56, "PhotoGray Multi-color (7 shades)"),
    ("M14", 1.56, "Transitions PhotoGray-Brown Surface Coloring"),
    ("M15", 1.56, "Transitions Relax Gray-Brown Blue Light"),
    ("M16", 1.67, "Transitions Relax Gray-Brown Blue Light"),
    ("M17", 1.50, "Sun Polarized Gray-Brown-Green"),
]
MYOBLOCK_PRICES = {"Metavision (Myoblock)": {
    "M01": 3700, "M02": 4300, "M03": 4700, "M04": 5300, "M05": 6800,
    "M06": 4200, "M07": 4900, "M08": 5700, "M09": 5900, "M10": 7300, "M11": 5200,
    "M12": 6000, "M13": 4500, "M14": 7000, "M15": 5400, "M16": 7500, "M17": 4900,
}}

MYOBLOCK_LIMIT = dict(sph_min=-10.0, sph_max=-0.5, cyl_min=-4.0, cyl_max=0.0)


def _build_matrix(db, company, catalog, section_prefix, category, row_defs, columns,
                  price_table, glass_rows=None, registry=None):
    all_rows = list(row_defs) + (glass_rows or [])
    for col in columns:
        lm = _mk_model(db, company, f"{section_prefix} {col}", category)
        prices = price_table.get(col, {})
        for row_key, index_value, treatment_band in all_rows:
            price = prices.get(row_key)
            if price is None:
                continue
            # Glass truth is keyed off the printed description (treatment_band),
            # not the internal row_key - catches Diving's "White Glass" row too,
            # which uses a plain "D1" key with no "GLASS" substring in it.
            is_glass = bool(treatment_band) and "glass" in treatment_band.lower()
            material = models.MaterialType.GLASS if is_glass else models.MaterialType.CR39
            design_variant = "Glass" if is_glass else None
            v = _mk_variant(db, lm, index_value, material=material,
                            treatment_band=treatment_band, design_variant=design_variant)
            vp = _mk_pricing(db, v, catalog, price=price)
            if registry is not None:
                registry[(section_prefix, col, row_key)] = (lm, v, vp)


@pytest.fixture()
def scope_setup(db):
    co = _mk_company(db, "SCOPE")
    cat = _mk_catalog(db, co)
    reg = {}

    _build_matrix(db, co, cat, "SCOPE Progressive", models.LensCategory.PROGRESSIVE, ROW26,
                  ["Gold", "Silver", "Bronze"], PROG_PRICES, glass_rows=GLASS4, registry=reg)
    _build_matrix(db, co, cat, "SCOPE Progressive", models.LensCategory.PROGRESSIVE, ROW26,
                  ["Adler HD", "Eagle", "4k Original"], PROG_PRICES, glass_rows=GLASS4, registry=reg)
    _build_matrix(db, co, cat, "SCOPE Progressive", models.LensCategory.PROGRESSIVE, ROW26,
                  ["Dual Free", "Weitblick"], PROG_PRICES, registry=reg)
    _build_matrix(db, co, cat, "SCOPE Progressive", models.LensCategory.PROGRESSIVE, ROW26,
                  ["MetaVision"], PROG_PRICES, registry=reg)

    _build_matrix(db, co, cat, "SCOPE Bifocal", models.LensCategory.BIFOCAL, BIFOCAL_ROWS,
                  ["Flat Top 45", "Flat Top 28 FreeFocal", "Flat Top 28 Double Aspheric",
                   "Flat Top 28 Toric", "New BiFocal Weitblick", "New BiFocal 4k"],
                  BIFOCAL_PRICES, registry=reg)
    # Domain correction: distinguish traditional visible-line Flat Top from
    # line-free New Bifocal, and correct Flat Top 28's PhotoGray row - it
    # offers Gray/Brown only (2 colors, one printed pricing row), never the
    # full 7-shade set that only Weitblick/4k's R15+R15B pair covers.
    OLD_BIFOCAL_COLS = {"Flat Top 45", "Flat Top 28 FreeFocal",
                        "Flat Top 28 Double Aspheric", "Flat Top 28 Toric"}
    NEW_BIFOCAL_COLS = {"New BiFocal Weitblick", "New BiFocal 4k"}
    for (section, col, row_key), (lm, v, vp) in reg.items():
        if section != "SCOPE Bifocal":
            continue
        if col in OLD_BIFOCAL_COLS:
            v.design_variant = "Flat Top (Visible Line)"
            if v.treatment_band == "PhotoGray Multi-color (7 shades)":
                v.treatment_band = "PhotoGray / PhotoBrown"
        elif col in NEW_BIFOCAL_COLS:
            v.design_variant = "New Bifocal (Line-Free)"
    db.commit()

    _build_matrix(db, co, cat, "SCOPE Office", models.LensCategory.SINGLE_VISION, OFFICE_ROWS,
                  ["Doctor", "Officestar"], OFFICE_PRICES, registry=reg)

    _build_matrix(db, co, cat, "SCOPE Young", models.LensCategory.SINGLE_VISION, ROW26,
                  ["Shabab"], YOUNG_PRICES, registry=reg)

    _build_matrix(db, co, cat, "SCOPE Single Vision", models.LensCategory.SINGLE_VISION, ROW26,
                  ["Double Aspheric", "Toric"], SV_PRICES, glass_rows=SV_GLASS1, registry=reg)
    _build_matrix(db, co, cat, "SCOPE Single Vision", models.LensCategory.SINGLE_VISION, ROW26,
                  ["Weitblick", "FreeFocal"], SV_PRICES, registry=reg)
    _build_matrix(db, co, cat, "SCOPE Single Vision", models.LensCategory.SINGLE_VISION, ROW26,
                  ["MetaVision"], SV_PRICES, registry=reg)

    _build_matrix(db, co, cat, "SCOPE Special", models.LensCategory.SINGLE_VISION, EXTREME_ROWS,
                  ["Extreme"], EXTREME_PRICES, registry=reg)

    _build_matrix(db, co, cat, "SCOPE Special", models.LensCategory.SINGLE_VISION,
                  [("D1", 1.52, "White Glass")], ["Diving (Single Vision)"],
                  {"Diving (Single Vision)": {"D1": 3000}}, registry=reg)
    _build_matrix(db, co, cat, "SCOPE Special", models.LensCategory.PROGRESSIVE,
                  [("D1", 1.52, "White Glass")], ["Diving (Progressive)"],
                  {"Diving (Progressive)": {"D1": 6000}}, registry=reg)

    myo_before = len(reg)
    _build_matrix(db, co, cat, "SCOPE Myoblock", models.LensCategory.SINGLE_VISION, MYOBLOCK_ROWS,
                  ["Metavision (Myoblock)"], MYOBLOCK_PRICES, registry=reg)
    for (section, col, row_key), (lm, v, vp) in reg.items():
        if section == "SCOPE Myoblock":
            _mk_range(db, lm, v, vp, **MYOBLOCK_LIMIT, notes="Myoblock explicit manufacturing limit (SCOPE.pdf p.15)")

    return dict(company=co, catalog=cat, registry=reg)


def _all_vp(db, co):
    return (db.query(models.VariantPricing).join(models.LensVariant).join(models.LensModel)
              .filter(models.LensModel.company_id == co.id).all())


def _models(db, co):
    return db.query(models.LensModel).filter(models.LensModel.company_id == co.id).all()


# 1. Independent SCOPE company.
def test_01_independent_company(db, scope_setup):
    co = scope_setup["company"]
    other = _mk_company(db, "SomeOtherCo")
    assert co.id != other.id
    assert co.name == "SCOPE"


# 2/3/4. Stock pricing = 0; all SCOPE pricing = RX; Stock PowerRange = 0.
def test_02_03_04_all_rx_no_stock(db, scope_setup):
    co = scope_setup["company"]
    rows = _all_vp(db, co)
    assert len(rows) == 520
    assert all(v.availability == models.PricingAvailability.RX for v in rows)
    assert sum(1 for v in rows if v.availability == models.PricingAvailability.STOCK) == 0


# 5. Ordinary RX rows without ranges remain manufacturing eligible.
def test_05_rx_no_range_manufacturing_eligible(db, scope_setup):
    lm, v, vp = scope_setup["registry"][("SCOPE Progressive", "Gold", "R01")]
    assert list(v.power_ranges) == []
    for sph, cyl in [(-25.0, -12.0), (2.0, 0.0), (-0.25, 0.0)]:
        status = product_search._row_eye_status(vp, _mk_presc(db, sph, cyl, name=f"gold-{sph}"), "od")
        assert status == "eligible", (sph, cyl)


# 6. Every imported VariantPricing maps to one real numeric source cell -
# spot-check exact printed prices across sections.
def test_06_prices_map_to_real_source_cells(db, scope_setup):
    reg = scope_setup["registry"]
    assert reg[("SCOPE Progressive", "Gold", "R01")][2].price_pair == Decimal("2650.00")
    assert reg[("SCOPE Progressive", "Silver", "PHOTOGLASS30")][2].price_pair == Decimal("2800.00")
    assert reg[("SCOPE Bifocal", "Flat Top 45", "R01")][2].price_pair == Decimal("2860.00")
    assert reg[("SCOPE Office", "Doctor", "R01")][2].price_pair == Decimal("1430.00")
    assert reg[("SCOPE Young", "Shabab", "R26")][2].price_pair == Decimal("3400.00")
    assert reg[("SCOPE Single Vision", "Toric", "R01")][2].price_pair == Decimal("950.00")
    assert reg[("SCOPE Special", "Extreme", "E7")][2].price_pair == Decimal("8200.00")
    assert reg[("SCOPE Special", "Diving (Progressive)", "D1")][2].price_pair == Decimal("6000.00")
    assert reg[("SCOPE Myoblock", "Metavision (Myoblock)", "M17")][2].price_pair == Decimal("4900.00")


# 7. No dash/blank became a price - the dashed cells were never created at all.
def test_07_dashes_never_became_price(db, scope_setup):
    reg = scope_setup["registry"]
    assert ("SCOPE Progressive", "Adler HD", "R26") not in reg          # Night Rider dash for Adler HD
    assert ("SCOPE Progressive", "Adler HD", "GLASS27") not in reg      # glass dash for Adler HD
    assert ("SCOPE Progressive", "Gold", "PHOTOGLASS30") not in reg     # photo glass dash for Gold
    assert ("SCOPE Progressive", "Dual Free", "R26") not in reg         # Night Rider dash for Dual Free
    assert ("SCOPE Bifocal", "Flat Top 45", "R02") not in reg           # Flat Top 45 only has R01


# 8. No equal-price cells were merged across designs - same-index rows across
# different design columns stay independent variants/rows.
def test_08_no_merge_across_designs(db, scope_setup):
    reg = scope_setup["registry"]
    gold_v = reg[("SCOPE Progressive", "Gold", "R03")][1]
    silver_v = reg[("SCOPE Progressive", "Silver", "R03")][1]
    assert gold_v.id != silver_v.id
    assert gold_v.lens_model_id != silver_v.lens_model_id


# 9. Progressive designs remain separate (9 distinct models).
def test_09_progressive_designs_separate(db, scope_setup):
    co = scope_setup["company"]
    names = {m.name for m in _models(db, co) if m.name.startswith("SCOPE Progressive")}
    assert names == {f"SCOPE Progressive {c}" for c in
                     ["Gold", "Silver", "Bronze", "Adler HD", "Eagle", "4k Original",
                      "Dual Free", "Weitblick", "MetaVision"]}


# 10. Bifocal designs remain separate (6 distinct models, including the two
# Flat Top 28 sub-designs kept apart from Flat Top 45).
def test_10_bifocal_designs_separate(db, scope_setup):
    co = scope_setup["company"]
    names = {m.name for m in _models(db, co) if m.name.startswith("SCOPE Bifocal")}
    assert names == {f"SCOPE Bifocal {c}" for c in
                     ["Flat Top 45", "Flat Top 28 FreeFocal", "Flat Top 28 Double Aspheric",
                      "Flat Top 28 Toric", "New BiFocal Weitblick", "New BiFocal 4k"]}


# 32. New Bifocal (line-free) counts and semantic tag: Weitblick=27, 4k=27,
# total=54, both marked distinctly from traditional Flat Top.
def test_32_new_bifocal_line_free(db, scope_setup):
    reg = scope_setup["registry"]
    weitblick_n = sum(1 for (s, c, _) in reg if s == "SCOPE Bifocal" and c == "New BiFocal Weitblick")
    k4_n = sum(1 for (s, c, _) in reg if s == "SCOPE Bifocal" and c == "New BiFocal 4k")
    assert weitblick_n == 27
    assert k4_n == 27
    assert weitblick_n + k4_n == 54
    for (section, col, row_key), (lm, v, vp) in reg.items():
        if section == "SCOPE Bifocal" and col in ("New BiFocal Weitblick", "New BiFocal 4k"):
            assert v.design_variant == "New Bifocal (Line-Free)"
            assert lm.category == models.LensCategory.BIFOCAL


# 33. Old/traditional Flat Top counts and semantic tag: FreeFocal=2, Double
# Aspheric=2, Toric=2, Flat Top 45=1, total=7, all marked visible-line.
def test_33_old_flat_top_visible_line(db, scope_setup):
    reg = scope_setup["registry"]
    counts = {}
    for (section, col, row_key), (lm, v, vp) in reg.items():
        if section != "SCOPE Bifocal":
            continue
        if col in ("Flat Top 45", "Flat Top 28 FreeFocal",
                   "Flat Top 28 Double Aspheric", "Flat Top 28 Toric"):
            counts[col] = counts.get(col, 0) + 1
            assert v.design_variant == "Flat Top (Visible Line)", col
    assert counts == {"Flat Top 45": 1, "Flat Top 28 FreeFocal": 2,
                      "Flat Top 28 Double Aspheric": 2, "Flat Top 28 Toric": 2}
    assert sum(counts.values()) == 7


# 34. PhotoGray/PhotoBrown remains ONE price identity with two color options
# for every Flat Top 28 design - never two VariantPricing rows.
def test_34_photogray_brown_one_price_identity(db, scope_setup):
    reg = scope_setup["registry"]
    for col in ("Flat Top 28 FreeFocal", "Flat Top 28 Double Aspheric", "Flat Top 28 Toric"):
        matches = [(row_key, v, vp) for (s, c, row_key), (lm, v, vp) in reg.items()
                  if s == "SCOPE Bifocal" and c == col and row_key == "R15"]
        assert len(matches) == 1, col   # exactly one row, never split Gray vs Brown
        row_key, v, vp = matches[0]
        assert v.treatment_band == "PhotoGray / PhotoBrown"
        # No separate R15B (the 7-shade extension) exists for these designs.
        assert (col, "R15B") not in {(c, rk) for (s, c, rk) in reg if s == "SCOPE Bifocal"}


# 11. Office designs remain separate.
def test_11_office_designs_separate(db, scope_setup):
    co = scope_setup["company"]
    names = {m.name for m in _models(db, co) if m.name.startswith("SCOPE Office")}
    assert names == {"SCOPE Office Doctor", "SCOPE Office Officestar"}


# 12. Single Vision designs remain separate.
def test_12_single_vision_designs_separate(db, scope_setup):
    co = scope_setup["company"]
    names = {m.name for m in _models(db, co) if m.name.startswith("SCOPE Single Vision")}
    assert names == {f"SCOPE Single Vision {c}" for c in
                     ["Double Aspheric", "Toric", "Weitblick", "FreeFocal", "MetaVision"]}


# 13. Extreme remains separate.
def test_13_extreme_separate(db, scope_setup):
    lm, v, vp = scope_setup["registry"][("SCOPE Special", "Extreme", "E1")]
    assert lm.name == "SCOPE Special Extreme"
    assert lm.category == models.LensCategory.SINGLE_VISION


# 14. Diving remains separate (2 distinct models: Single Vision + Progressive).
def test_14_diving_separate(db, scope_setup):
    lm_sv, _, vp_sv = scope_setup["registry"][("SCOPE Special", "Diving (Single Vision)", "D1")]
    lm_prog, _, vp_prog = scope_setup["registry"][("SCOPE Special", "Diving (Progressive)", "D1")]
    assert lm_sv.id != lm_prog.id
    assert lm_sv.category == models.LensCategory.SINGLE_VISION
    assert lm_prog.category == models.LensCategory.PROGRESSIVE
    assert vp_sv.price_pair == Decimal("3000.00")
    assert vp_prog.price_pair == Decimal("6000.00")


# 15/16/17. Myoblock remains separate; explicit limits enforced; limits never
# leak to any other SCOPE product.
def test_15_16_17_myoblock_limits(db, scope_setup):
    reg = scope_setup["registry"]
    lm, v, vp = reg[("SCOPE Myoblock", "Metavision (Myoblock)", "M01")]
    assert lm.name == "SCOPE Myoblock Metavision (Myoblock)"
    pr = list(v.power_ranges)
    assert len(pr) == 1
    assert pr[0].sph_min == -10.0 and pr[0].sph_max == -0.5
    assert pr[0].cyl_min == -4.0 and pr[0].cyl_max == 0.0

    ok_in, _ = product_search.lens_matcher.check_power_range(pr[0], _mk_presc(db, -5.0, -2.0, name="myo-in"), "od")
    ok_boundary, _ = product_search.lens_matcher.check_power_range(pr[0], _mk_presc(db, -10.0, 0.0, name="myo-b1"), "od")
    ok_plus, _ = product_search.lens_matcher.check_power_range(pr[0], _mk_presc(db, 1.0, 0.0, name="myo-plus"), "od")
    ok_beyond, _ = product_search.lens_matcher.check_power_range(pr[0], _mk_presc(db, -11.0, 0.0, name="myo-beyond"), "od")
    ok_cyl_beyond, _ = product_search.lens_matcher.check_power_range(pr[0], _mk_presc(db, -5.0, -5.0, name="myo-cylbeyond"), "od")
    assert ok_in and ok_boundary
    assert not ok_plus and not ok_beyond and not ok_cyl_beyond

    # Limit never leaks to a non-Myoblock SCOPE row.
    other_lm, other_v, other_vp = reg[("SCOPE Progressive", "Gold", "R01")]
    assert list(other_v.power_ranges) == []
    status = product_search._row_eye_status(other_vp, _mk_presc(db, -25.0, -12.0, name="gold-extreme"), "od")
    assert status == "eligible"


# 18/19/20/21/22/23. Hard Coat included in base price; optional additions only
# when explicitly selected (never auto-composed); no coating surcharge
# automatically added anywhere.
def test_18_through_23_hard_coat_and_additions(db, scope_setup):
    gold_r01_price = scope_setup["registry"][("SCOPE Progressive", "Gold", "R01")][2].price_pair
    assert gold_r01_price == Decimal("2650.00")   # printed base price = Hard-Coated price, as-is
    assert SCOPE_ADDITIONS["HMC"] == 250
    assert SCOPE_ADDITIONS["IRIDIO Plus"] == 500
    assert SCOPE_ADDITIONS["PRO-DRIVE"] == 600
    assert SCOPE_ADDITIONS["MIRROR"] == 350
    # Additions are evidence only - never combined into price_pair anywhere.
    assert gold_r01_price != Decimal("2650.00") + SCOPE_ADDITIONS["HMC"]
    co = scope_setup["company"]
    model_names = {m.name.lower() for m in _models(db, co)}
    assert not any("hmc" in n or "iridio" in n or "pro-drive" in n or "mirror" in n for n in model_names)


# 24. Other printed optional services preserved correctly (tinting/prism).
def test_24_other_services_preserved(db, scope_setup):
    assert SCOPE_ADDITIONS["Sun Tinting (Plastic 1.5-1.56)"] == 350
    assert SCOPE_ADDITIONS["Sun Tinting (Plastic 1.6/1.67)"] == 450
    assert SCOPE_ADDITIONS["Sun Tinting (Glass)"] == 500
    assert SCOPE_ADDITIONS["Prism up to 5 Diopters"] == 450
    assert SCOPE_ADDITIONS["Prism up to 10 Diopters"] == 500


# 25. Prior manufacturer counts unchanged (proxy: SCOPE coexists cleanly
# alongside another company's row with no cross-counting).
def test_25_no_cross_counting(db, scope_setup):
    other = _mk_company(db, "PLATINUM")
    cat2 = _mk_catalog(db, other)
    lm2 = _mk_model(db, other, "PLATINUM Model", models.LensCategory.SINGLE_VISION)
    v2 = _mk_variant(db, lm2, 1.6)
    vp2 = models.VariantPricing(variant_id=v2.id, availability=models.PricingAvailability.STOCK,
                                price_pair=Decimal("999.00"), currency="EGP", source_catalog_id=cat2.id)
    db.add(vp2); db.commit()
    assert len(_all_vp(db, scope_setup["company"])) == 520
    assert len(_all_vp(db, other)) == 1


# 26. Global RX rule unchanged (re-asserted in isolation).
def test_26_global_rx_rule_unaffected(db, scope_setup):
    other = _mk_company(db, "OtherRxCo")
    cat2 = _mk_catalog(db, other)
    lm2 = _mk_model(db, other, "RX Model", models.LensCategory.SINGLE_VISION)
    v2 = _mk_variant(db, lm2, 1.5)
    vp2 = models.VariantPricing(variant_id=v2.id, availability=models.PricingAvailability.RX,
                                price_pair=Decimal("2000.00"), currency="EGP", source_catalog_id=cat2.id)
    db.add(vp2); db.commit(); db.refresh(vp2)
    status = product_search._row_eye_status(vp2, _mk_presc(db, -12.0, -1.0, name="global-rx"), "od")
    assert status == "eligible"


# 27/28/29. DIVEL overlap safety / Maxxee overlapping-band behavior / PLATINUM
# behavior are all generic or manufacturer-scoped mechanisms untouched by this
# import - this import adds no generic backend code at all.
def test_27_28_29_other_manufacturers_untouched(db, scope_setup):
    import inspect
    assert "SCOPE" not in inspect.getsource(product_search)


# 30. D1 scalar-diameter column stays dormant (real column, never populated).
def test_30_d1_column_dormant(db, scope_setup):
    co = scope_setup["company"]
    variants = (db.query(models.LensVariant).join(models.LensModel)
                  .filter(models.LensModel.company_id == co.id).all())
    assert len(variants) == 520   # one variant per pricing row, no sharing
    assert all(v.diameter is None for v in variants)


# 31. Material truth: every SCOPE row explicitly printed as Glass/White
# Glass/Photo Glass is stored as MaterialType.GLASS, NEVER CR39 or any other
# plastic value - covers Progressive (White Glass + Photo Glass, 4 tiers),
# Single Vision (White Glass Compressed), and Diving (White Glass), 21 rows
# total. This is a permanent regression: no future SCOPE change may
# reintroduce CR39 as a placeholder for a catalog-proven glass row.
def test_31_glass_rows_never_stored_as_cr39(db, scope_setup):
    co = scope_setup["company"]
    glass_variants = (db.query(models.LensVariant).join(models.LensModel)
                        .filter(models.LensModel.company_id == co.id,
                                models.LensVariant.treatment_band.like("%Glass%"))
                        .all())
    assert len(glass_variants) == 21
    assert all(v.material == models.MaterialType.GLASS for v in glass_variants)
    assert all(v.material != models.MaterialType.CR39 for v in glass_variants)
    # Prices/index untouched by the material correction - spot-check known cells.
    assert scope_setup["registry"][("SCOPE Progressive", "Gold", "GLASS27")][2].price_pair == Decimal("3270.00")
    assert scope_setup["registry"][("SCOPE Progressive", "Silver", "PHOTOGLASS30")][2].price_pair == Decimal("2800.00")
    assert scope_setup["registry"][("SCOPE Single Vision", "Toric", "GLASS_SV")][2].price_pair == Decimal("2300.00")
    diving_sv = scope_setup["registry"][("SCOPE Special", "Diving (Single Vision)", "D1")][1]
    diving_prog = scope_setup["registry"][("SCOPE Special", "Diving (Progressive)", "D1")][1]
    assert diving_sv.material == models.MaterialType.GLASS
    assert diving_prog.material == models.MaterialType.GLASS
