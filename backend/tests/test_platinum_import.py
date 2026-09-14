"""Permanent regression coverage for the PLATINUM canonical import.

Deliberately synthetic, mirroring the corrected shape directly via the ORM
(no PDF parsing, no dependency on the live optical_lens.db), matching the
same pattern as test_divel_import.py / test_visall_import.py.

Two commercial sections:
  - STOCK (16 independent commercial products, each with its own printed
    SPH/CYL/Total-Power Stock Power Range - PowerRange = 16, one-to-one).
  - RX / Manufacturing (191 pricing identities across RX Single Vision, HD,
    HD UT, Office, Young, MYO D, BI FOCAL, BI (HS), and six Progressive
    designs X-PLORE/X-TEND/X-TEND UT/X-PERIENCE/X-PERIENCE UT/X-PERIENCE T -
    NONE of these carry a PowerRange, per the project's permanent RX rule:
    a made-to-order RX row with zero PowerRange is always manufacturing-
    eligible; nothing here fabricates a manufacturing limit PLATINUM never
    publishes).

STOCK RANGE RULE (explicit user/domain clarification for this import): the
printed "TOTAL POWER" column caps the PLUS side ONLY. Implemented with the
project's existing G3 mechanism (total_power_max + max_cyl_abs, the same
fields HOYA uses) with total_power_min left UNSET, so:
  - a PLUS prescription's meridian is hard-capped at the printed TOTAL POWER
    value (no tolerance, by design of the G3 clause);
  - a MINUS prescription is governed purely by the plain sph_min/cyl-box
    coarse check (no meridian/CYL compensation is ever added to the minus
    side) - this falls out for free by leaving total_power_min unset;
  - plus-only rows (e.g. "1.5 (60)") get sph_min=0 so no minus prescription
    can ever pass the coarse box at all;
  - minus-only rows (1.67, 1.74) use a PLAIN box only (no G3 fields) since
    they have no plus side to asymmetrically cap and their one printed
    negative boundary already equals the plain sph_min;
  - "1.5 BASE 2-4-8" and "1.5 POLARIZED" print an all-zero SPH/CYL/Total
    Power row - preserved as an EXACT zero-tolerance plano-only match
    (total_power_min=total_power_max=max_cyl_abs=0.0), never expanded into
    a broader range and never left to the matcher's usual +-0.25 coarse-box
    tolerance (which would otherwise wrongly admit e.g. SPH +0.25).

Domain identity corrections (explicit user/domain confirmation):
  - "Blu STEEL G2" (printed "1.6 G2") has commercial index 1.60, never the
    technical catalog's physical-lens index of 1.61.
  - "PLATINUM PLUS" has NO printed price on the supplied price-list page;
    its 900 EGP price is user/domain-confirmed, index 1.56, BlueCut.
  - "AeroLite" is printed on the price list simply as "1.59" (600 EGP);
    the technical catalog identifies it as AeroLite, polycarbonate-related,
    index 1.59.
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
from app import models, database, schemas, product_search, crud, lens_matcher  # noqa: E402

matcher = lens_matcher.LensMatcherFinal()


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


def _mk_model(db, company, name, category=models.LensCategory.SINGLE_VISION):
    m = models.LensModel(company_id=company.id, name=name, category=category)
    db.add(m); db.commit(); db.refresh(m)
    return m


def _mk_variant(db, model, index_value, *, material=models.MaterialType.CR39,
                design_variant=None, color_variant=None, treatment_band=None):
    v = models.LensVariant(
        lens_model_id=model.id, material=material, index_value=index_value,
        design_type=models.DesignType.SPHERICAL, is_aspherical=False,
        design_variant=design_variant, color_variant=color_variant,
        treatment_band=treatment_band, price=0.0, currency="EGP")
    db.add(v); db.commit(); db.refresh(v)
    return v


def _mk_pricing(db, variant, catalog, *, availability, price):
    vp = models.VariantPricing(
        variant_id=variant.id, availability=availability, price_pair=Decimal(str(price)),
        currency="EGP", source_catalog_id=catalog.id)
    db.add(vp); db.commit(); db.refresh(vp)
    return vp


def _mk_range(db, model, variant, pricing, *, sph_min, sph_max, cyl_mag,
              total_power_max=None, total_power_min=None, notes=None):
    max_cyl_abs = cyl_mag if (total_power_max is not None or total_power_min is not None) else None
    pr = models.PowerRange(
        lens_model_id=model.id, variant_id=variant.id, pricing_id=pricing.id,
        sph_min=sph_min, sph_max=sph_max, cyl_min=-cyl_mag, cyl_max=0.0,
        max_cyl_abs=max_cyl_abs, total_power_max=total_power_max,
        total_power_min=total_power_min, notes=notes)
    db.add(pr); db.commit()
    return pr


def _mk_presc(db, sph, cyl=0.0, name="p"):
    p = models.Prescription(
        customer_name=name, od_sph_original=sph, od_cyl_original=cyl, od_axis_original=0,
        od_sph=sph, od_cyl=cyl, od_axis=0, os_sph_original=sph, os_cyl_original=cyl,
        os_axis_original=0, os_sph=sph, os_cyl=cyl, os_axis=0, pd=63)
    db.add(p); db.commit(); db.refresh(p)
    return p


STOCK = [
    ("1.5", 250, models.MaterialType.CR39, 1.5, None, -6.0, 4.0, 2.0, 4.0, None, None),
    ("1.5 (60)", 300, models.MaterialType.CR39, 1.5, None, 0.0, 6.0, 2.0, 6.0, None, None),
    ("1.5 (EXT)", 350, models.MaterialType.CR39, 1.5, None, -6.0, 4.0, 4.0, 4.0, None, None),
    # Plano-only SUN stock (non-prescription): "BASE 2-4-8" names Base Curve
    # options (2/4/8), never an SPH/CYL/Total-Power range - preserved via
    # design_variant, never treated as optical power. Eligible ONLY at exact
    # SPH 0.00 / CYL 0.00 (see ZERO_TOLERANCE_ROWS below).
    ("1.5 BASE 2-4-8", 500, models.MaterialType.CR39, 1.5, "Sun", 0.0, 0.0, 0.0, 0.0, 0.0, None),
    # Plano-only SUN stock (non-prescription), also polarized - distinct from
    # the RX-table "1.5 POLARIZED" prescription rows below (ROW15), which
    # remain ordinary Polarized Rx products, never plano-only.
    ("1.5 POLARIZED", 1200, models.MaterialType.CR39, 1.5, "Sun + Polarized", 0.0, 0.0, 0.0, 0.0, 0.0, None),
    ("1.56 HMC", 380, models.MaterialType.CR39, 1.56, "HMC", -6.0, 6.0, 2.0, 6.0, None, None),
    ("1.56 HMC EXT", 450, models.MaterialType.CR39, 1.56, "HMC EXT", -6.0, 6.0, 4.0, 6.0, None, None),
    ("1.56 BLU STEEL", 600, models.MaterialType.CR39, 1.56, "BLU STEEL", -6.0, 4.0, 2.0, 4.0, None, None),
    ("PLATINUM PLUS", 900, models.MaterialType.CR39, 1.56, "BlueCut", -6.0, 4.0, 4.0, 4.0, None, None),
    ("1.56 SUN", 800, models.MaterialType.CR39, 1.56, "Sun", -6.0, 4.0, 3.0, 4.0, None, None),
    ("1.56 MIRA DRIVE", 1400, models.MaterialType.CR39, 1.56, "MIRA DRIVE", -6.0, 4.0, 2.0, 4.0, None, None),
    ("AeroLite", 600, models.MaterialType.POLYCARBONATE, 1.59, None, -8.0, 6.0, 3.0, 6.0, None, None),
    ("1.6", 800, models.MaterialType.CR39, 1.6, None, -10.0, 6.0, 3.0, 6.0, None, None),
    ("Blu STEEL G2", 1200, models.MaterialType.CR39, 1.6, "G2", -8.0, 4.0, 3.0, 4.0, None, None),
    ("1.67", 1400, models.MaterialType.CR39, 1.67, None, -12.0, -4.0, 3.0, None, None, None),
    ("1.74", 4200, models.MaterialType.CR39, 1.74, None, -14.0, -4.0, 4.0, None, None, None),
]

ROW15 = [
    ("1.5", 1.5, {}),
    ("1.5 TR", 1.5, dict(treatment_band="TR")),
    ("1.5 POLARIZED", 1.5, dict(treatment_band="Polarized")),
    ("1.56 BRC", 1.56, dict(treatment_band="BRC")),
    ("1.56 SUN", 1.56, dict(treatment_band="Sun")),
    ("1.59", 1.59, {}),
    ("1.59 POL", 1.59, dict(treatment_band="Polarized")),
    ("1.59 TR", 1.59, dict(treatment_band="TR")),
    ("1.6", 1.6, {}),
    ("1.6 TR", 1.6, dict(treatment_band="TR")),
    ("1.6 G2", 1.6, dict(treatment_band="G2")),
    ("1.6 G2 GRAY", 1.6, dict(treatment_band="G2", color_variant="Gray")),
    ("1.67", 1.67, {}),
    ("1.67 TR", 1.67, dict(treatment_band="TR")),
    ("1.74", 1.74, {}),
]
OFFICE_ROWS = {"1.5", "1.56 BRC", "1.59", "1.6", "1.6 G2", "1.67", "1.74"}
BIFOCAL_ROWS = {"1.5", "1.56 SUN"}

ROW17_RX_SV = [
    ("1.5", 1.5, {}), ("1.5 (75)", 1.5, dict(design_variant="(75)")),
    ("1.5 (80)", 1.5, dict(design_variant="(80)")), ("1.5 TR", 1.5, dict(treatment_band="TR")),
    ("POLARIZED", 1.5, dict(treatment_band="Polarized")), ("1.56 BRC", 1.56, dict(treatment_band="BRC")),
    ("1.56 SUN", 1.56, dict(treatment_band="Sun")), ("1.59", 1.59, {}),
    ("1.59 POL", 1.59, dict(treatment_band="Polarized")), ("1.59 TR", 1.59, dict(treatment_band="TR")),
    ("1.6", 1.6, {}), ("1.6 TR", 1.6, dict(treatment_band="TR")),
    ("1.6 G2", 1.6, dict(treatment_band="G2")),
    ("1.6 G2 GRAY", 1.6, dict(treatment_band="G2", color_variant="Gray")),
    ("1.67", 1.67, {}), ("1.67 TR", 1.67, dict(treatment_band="TR")), ("1.74", 1.74, {}),
]

PRICE_TABLES = {
    "RX Single Vision": dict(model_name="PLATINUM RX Single Vision", category=models.LensCategory.SINGLE_VISION,
        design_variant=None, rows=ROW17_RX_SV,
        prices={"1.5": 1200, "1.5 (75)": 1200, "1.5 (80)": 1300, "1.5 TR": 3200, "POLARIZED": 2400,
                "1.56 BRC": 1600, "1.56 SUN": 1800, "1.59": 1600, "1.59 POL": 3300, "1.59 TR": 4200,
                "1.6": 2000, "1.6 TR": 5000, "1.6 G2": 2500, "1.6 G2 GRAY": 3500, "1.67": 3000,
                "1.67 TR": 6400, "1.74": 4500}),
    "HD": dict(model_name="PLATINUM HD", category=models.LensCategory.SINGLE_VISION, design_variant="HD", rows=ROW15,
        prices={"1.5": 1700, "1.5 TR": 3600, "1.5 POLARIZED": 3000, "1.56 BRC": 2200, "1.56 SUN": 2450,
                "1.59": 2200, "1.59 POL": 3700, "1.59 TR": 4600, "1.6": 2550, "1.6 TR": 5400,
                "1.6 G2": 3000, "1.6 G2 GRAY": 4000, "1.67": 3500, "1.67 TR": 6800, "1.74": 5050}),
    "HD UT": dict(model_name="PLATINUM HD UT", category=models.LensCategory.SINGLE_VISION, design_variant="HDUT", rows=ROW15,
        prices={"1.5": 2250, "1.5 TR": 4000, "1.5 POLARIZED": 3400, "1.56 BRC": 2750, "1.56 SUN": 3000,
                "1.59": 2750, "1.59 POL": 4200, "1.59 TR": 5000, "1.6": 3100, "1.6 TR": 5800,
                "1.6 G2": 3500, "1.6 G2 GRAY": 4500, "1.67": 3900, "1.67 TR": 7200, "1.74": 5600}),
    "Office": dict(model_name="PLATINUM Office", category=models.LensCategory.SINGLE_VISION, design_variant="Office",
        rows=[r for r in ROW15 if r[0] in OFFICE_ROWS],
        prices={"1.5": 1950, "1.56 BRC": 2450, "1.59": 2450, "1.6": 2800, "1.6 G2": 3200, "1.67": 3550, "1.74": 5300}),
    "Young": dict(model_name="PLATINUM Young", category=models.LensCategory.SINGLE_VISION, design_variant="Young", rows=ROW15,
        prices={"1.5": 1850, "1.5 TR": 3700, "1.5 POLARIZED": 3000, "1.56 BRC": 2350, "1.56 SUN": 2600,
                "1.59": 2350, "1.59 POL": 3800, "1.59 TR": 4700, "1.6": 2700, "1.6 TR": 5500,
                "1.6 G2": 3100, "1.6 G2 GRAY": 4100, "1.67": 3500, "1.67 TR": 6900, "1.74": 5200}),
    "MYO D": dict(model_name="PLATINUM MYO D", category=models.LensCategory.SINGLE_VISION, design_variant="MYO D", rows=ROW15,
        prices={"1.5": 4300, "1.5 TR": 5700, "1.5 POLARIZED": 5450, "1.56 BRC": 4800, "1.56 SUN": 5050,
                "1.59": 4800, "1.59 POL": 5800, "1.59 TR": 6700, "1.6": 5200, "1.6 TR": 6700,
                "1.6 G2": 5550, "1.6 G2 GRAY": 6550, "1.67": 5100, "1.67 TR": 8900, "1.74": 7700}),
    "BI FOCAL": dict(model_name="PLATINUM BI FOCAL", category=models.LensCategory.BIFOCAL, design_variant=None,
        rows=[r for r in ROW15 if r[0] in BIFOCAL_ROWS], prices={"1.5": 1250, "1.56 SUN": 2200}),
    "BI (HS)": dict(model_name="PLATINUM BI (HS)", category=models.LensCategory.BIFOCAL, design_variant=None, rows=ROW15,
        prices={"1.5": 1550, "1.5 TR": 3600, "1.5 POLARIZED": 3000, "1.56 BRC": 2200, "1.56 SUN": 2450,
                "1.59": 2200, "1.59 POL": 3700, "1.59 TR": 4600, "1.6": 2600, "1.6 TR": 5400,
                "1.6 G2": 3000, "1.6 G2 GRAY": 4000, "1.67": 3500, "1.67 TR": 6800, "1.74": 5100}),
    "X-PLORE": dict(model_name="PLATINUM X-PLORE", category=models.LensCategory.PROGRESSIVE, design_variant="X-PLORE", rows=ROW15,
        prices={"1.5": 1800, "1.5 TR": 3700, "1.5 POLARIZED": 3250, "1.56 BRC": 2500, "1.56 SUN": 2800,
                "1.59": 2500, "1.59 POL": 3800, "1.59 TR": 4700, "1.6": 3000, "1.6 TR": 5500,
                "1.6 G2": 3500, "1.6 G2 GRAY": 4600, "1.67": 3900, "1.67 TR": 6900, "1.74": 5750}),
    "X-TEND": dict(model_name="PLATINUM X-TEND", category=models.LensCategory.PROGRESSIVE, design_variant="X-TEND", rows=ROW15,
        prices={"1.5": 2500, "1.5 TR": 4300, "1.5 POLARIZED": 4000, "1.56 BRC": 3250, "1.56 SUN": 3550,
                "1.59": 3250, "1.59 POL": 4400, "1.59 TR": 5300, "1.6": 3750, "1.6 TR": 6000,
                "1.6 G2": 4250, "1.6 G2 GRAY": 5400, "1.67": 4600, "1.67 TR": 7500, "1.74": 6500}),
    "X-TEND UT": dict(model_name="PLATINUM X-TEND UT", category=models.LensCategory.PROGRESSIVE, design_variant="X-TEND UT", rows=ROW15,
        prices={"1.5": 3100, "1.5 TR": 4700, "1.5 POLARIZED": 4550, "1.56 BRC": 3800, "1.56 SUN": 4100,
                "1.59": 3800, "1.59 POL": 4800, "1.59 TR": 5700, "1.6": 4300, "1.6 TR": 6500,
                "1.6 G2": 4800, "1.6 G2 GRAY": 5900, "1.67": 5200, "1.67 TR": 7900, "1.74": 7000}),
    "X-PERIENCE": dict(model_name="PLATINUM X-PERIENCE", category=models.LensCategory.PROGRESSIVE, design_variant="X-PERIENCE", rows=ROW15,
        prices={"1.5": 3500, "1.5 TR": 5000, "1.5 POLARIZED": 5000, "1.56 BRC": 4250, "1.56 SUN": 4550,
                "1.59": 4250, "1.59 POL": 5200, "1.59 TR": 6000, "1.6": 4750, "1.6 TR": 6900,
                "1.6 G2": 5250, "1.6 G2 GRAY": 6400, "1.67": 5600, "1.67 TR": 8300, "1.74": 7500}),
    "X-PERIENCE UT": dict(model_name="PLATINUM X-PERIENCE UT", category=models.LensCategory.PROGRESSIVE, design_variant="X-PERIENCE UT", rows=ROW15,
        prices={"1.5": 4100, "1.5 TR": 5500, "1.5 POLARIZED": 5550, "1.56 BRC": 4800, "1.56 SUN": 5100,
                "1.59": 4800, "1.59 POL": 5600, "1.59 TR": 6500, "1.6": 5300, "1.6 TR": 7300,
                "1.6 G2": 5800, "1.6 G2 GRAY": 6900, "1.67": 6200, "1.67 TR": 8700, "1.74": 8050}),
    "X-PERIENCE T": dict(model_name="PLATINUM X-PERIENCE T", category=models.LensCategory.PROGRESSIVE, design_variant="X-PERIENCE T", rows=ROW15,
        prices={"1.5": 5000, "1.5 TR": 6300, "1.5 POLARIZED": 6500, "1.56 BRC": 5750, "1.56 SUN": 6050,
                "1.59": 5750, "1.59 POL": 6400, "1.59 TR": 7300, "1.6": 6250, "1.6 TR": 8000,
                "1.6 G2": 6750, "1.6 G2 GRAY": 7900, "1.67": 7100, "1.67 TR": 9500, "1.74": 9000}),
}

ZERO_TOLERANCE_ROWS = {"1.5 BASE 2-4-8", "1.5 POLARIZED"}


@pytest.fixture()
def platinum_setup(db):
    co = _mk_company(db, "PLATINUM")
    cat = _mk_catalog(db, co)

    stock_models = {}
    stock_variants = {}
    stock_pricing = {}
    stock_ranges = {}
    for name, price, material, index_value, treatment_band, sph_min, sph_max, cyl_mag, tp_max, tp_min, notes in STOCK:
        lm = _mk_model(db, co, name)
        v = _mk_variant(db, lm, index_value, material=material, treatment_band=treatment_band)
        vp = _mk_pricing(db, v, cat, availability=models.PricingAvailability.STOCK, price=price)
        pr = _mk_range(db, lm, v, vp, sph_min=sph_min, sph_max=sph_max, cyl_mag=cyl_mag,
                       total_power_max=tp_max, total_power_min=tp_min)
        stock_models[name] = lm; stock_variants[name] = v; stock_pricing[name] = vp; stock_ranges[name] = pr

    # "BASE 2-4-8" names Base Curve options (2/4/8), preserved as commercial
    # evidence via design_variant - never an SPH/CYL/Total-Power value.
    stock_variants["1.5 BASE 2-4-8"].design_variant = "Base Curve 2/4/8"
    db.commit()

    rx_models = {}
    rx_pricing = {}   # (table_key, row_name) -> VariantPricing
    for table_key, cfg in PRICE_TABLES.items():
        lm = _mk_model(db, co, cfg["model_name"], cfg["category"])
        rx_models[table_key] = lm
        for row_name, index_value, extra in cfg["rows"]:
            fields = dict(extra)
            if cfg["design_variant"] and "design_variant" not in fields:
                fields["design_variant"] = cfg["design_variant"]
            v = _mk_variant(db, lm, index_value, **fields)
            vp = _mk_pricing(db, v, cat, availability=models.PricingAvailability.RX,
                             price=cfg["prices"][row_name])
            rx_pricing[(table_key, row_name)] = vp

    return dict(company=co, catalog=cat, stock_models=stock_models, stock_variants=stock_variants,
                stock_pricing=stock_pricing, stock_ranges=stock_ranges, rx_models=rx_models, rx_pricing=rx_pricing)


def _all_vp(db, co):
    return (db.query(models.VariantPricing).join(models.LensVariant).join(models.LensModel)
              .filter(models.LensModel.company_id == co.id).all())


# 1. Independent PLATINUM company.
def test_01_independent_company(db, platinum_setup):
    co = platinum_setup["company"]
    other = _mk_company(db, "SomeOtherCo")
    assert co.id != other.id
    assert co.name == "PLATINUM"


# 2. Total VariantPricing = 207.
def test_02_total_variant_pricing(db, platinum_setup):
    assert len(_all_vp(db, platinum_setup["company"])) == 207


# 3. Stock pricing = 16.
def test_03_stock_count(db, platinum_setup):
    co = platinum_setup["company"]
    assert sum(1 for v in _all_vp(db, co) if v.availability == models.PricingAvailability.STOCK) == 16


# 4. RX/manufacturing pricing = 191.
def test_04_rx_count(db, platinum_setup):
    co = platinum_setup["company"]
    assert sum(1 for v in _all_vp(db, co) if v.availability == models.PricingAvailability.RX) == 191


# 5. Stock PowerRange = 16 (one-to-one; no RX row carries a range).
def test_05_stock_power_range_count(db, platinum_setup):
    co = platinum_setup["company"]
    pr_count = (db.query(models.PowerRange).join(models.LensVariant).join(models.LensModel)
                  .filter(models.LensModel.company_id == co.id).count())
    assert pr_count == 16
    rx_with_range = (db.query(models.PowerRange).join(models.VariantPricing, models.PowerRange.pricing_id == models.VariantPricing.id)
                        .join(models.LensVariant, models.PowerRange.variant_id == models.LensVariant.id).join(models.LensModel)
                        .filter(models.LensModel.company_id == co.id, models.VariantPricing.availability == models.PricingAvailability.RX)
                        .count())
    assert rx_with_range == 0


# 6. PLATINUM PLUS: exists as Stock, price=900, index/product mapping
# correct, printed Stock range attached, price provenance user/domain-confirmed.
def test_06_platinum_plus(db, platinum_setup):
    v = platinum_setup["stock_variants"]["PLATINUM PLUS"]
    vp = platinum_setup["stock_pricing"]["PLATINUM PLUS"]
    pr = platinum_setup["stock_ranges"]["PLATINUM PLUS"]
    assert vp.availability == models.PricingAvailability.STOCK
    assert vp.price_pair == Decimal("900.00")
    assert v.index_value == 1.56
    assert v.treatment_band == "BlueCut"
    assert pr is not None and pr.pricing_id == vp.id


# 7. Blu STEEL G2: commercial index=1.60, NOT 1.61; BlueCut/Super UV semantics retained.
def test_07_blu_steel_g2(db, platinum_setup):
    v = platinum_setup["stock_variants"]["Blu STEEL G2"]
    assert v.index_value == 1.6
    assert v.index_value != 1.61
    assert v.treatment_band == "G2"


# 8. AeroLite: index=1.59.
def test_08_aerolite_index(db, platinum_setup):
    v = platinum_setup["stock_variants"]["AeroLite"]
    assert v.index_value == 1.59


# 9. Plus-only Stock range does not match a minus Rx.
def test_09_plus_only_rejects_minus(db, platinum_setup):
    pr = platinum_setup["stock_ranges"]["1.5 (60)"]
    presc_plus = _mk_presc(db, 3.0, name="plus-ok")
    presc_minus = _mk_presc(db, -1.0, name="minus-no")
    ok_plus, _ = matcher.check_power_range(pr, presc_plus, "od")
    ok_minus, _ = matcher.check_power_range(pr, presc_minus, "od")
    assert ok_plus is True
    assert ok_minus is False


# 10. 1.67 and 1.74 negative-only ranges do not match a plus Rx.
def test_10_negative_only_rejects_plus(db, platinum_setup):
    for name in ("1.67", "1.74"):
        pr = platinum_setup["stock_ranges"][name]
        presc_plus = _mk_presc(db, 2.0, name=f"{name}-plus")
        ok_plus, _ = matcher.check_power_range(pr, presc_plus, "od")
        assert ok_plus is False, name
    pr167 = platinum_setup["stock_ranges"]["1.67"]
    presc_in = _mk_presc(db, -6.0, -2.0, name="167-in")
    presc_beyond = _mk_presc(db, -13.0, name="167-beyond")
    assert matcher.check_power_range(pr167, presc_in, "od")[0] is True
    assert matcher.check_power_range(pr167, presc_beyond, "od")[0] is False


# 11. TOTAL POWER constraint is enforced (plus side only; minus side untouched).
def test_11_total_power_constraint_enforced(db, platinum_setup):
    pr = platinum_setup["stock_ranges"]["1.5"]   # sph -6..4, cyl mag 2, total_power_max=4
    within = _mk_presc(db, 3.0, name="tp-within")
    at_boundary = _mk_presc(db, 4.0, name="tp-boundary")
    beyond = _mk_presc(db, 5.0, name="tp-beyond")
    minus_far = _mk_presc(db, -5.0, name="tp-minus-far")   # not total-power-capped
    minus_beyond_box = _mk_presc(db, -6.5, name="tp-minus-beyond-box")
    assert matcher.check_power_range(pr, within, "od")[0] is True
    assert matcher.check_power_range(pr, at_boundary, "od")[0] is True
    assert matcher.check_power_range(pr, beyond, "od")[0] is False
    assert matcher.check_power_range(pr, minus_far, "od")[0] is True
    assert matcher.check_power_range(pr, minus_beyond_box, "od")[0] is False


# 12. CYL limits enforced.
def test_12_cyl_limit_enforced(db, platinum_setup):
    pr = platinum_setup["stock_ranges"]["1.5"]   # cyl magnitude 2
    ok_in, _ = matcher.check_power_range(pr, _mk_presc(db, 3.0, -2.0, name="cyl-in"), "od")
    ok_out, _ = matcher.check_power_range(pr, _mk_presc(db, 3.0, -3.0, name="cyl-out"), "od")
    assert ok_in is True
    assert ok_out is False


# 13. Stock ranges never leak across products.
def test_13_ranges_never_leak(db, platinum_setup):
    pr_60 = platinum_setup["stock_ranges"]["1.5 (60)"]   # plus-only, 0..6
    pr_167 = platinum_setup["stock_ranges"]["1.67"]      # minus-only, -12..-4
    presc = _mk_presc(db, -6.0, -2.0, name="leak-check")  # fits 1.67, not 1.5(60)
    assert matcher.check_power_range(pr_167, presc, "od")[0] is True
    assert matcher.check_power_range(pr_60, presc, "od")[0] is False


# 14. RX no-range rows remain Manufacturing eligible (permanent global RX rule unaffected).
def test_14_rx_no_range_manufacturing_eligible(db, platinum_setup):
    vp = platinum_setup["rx_pricing"][("RX Single Vision", "1.5")]
    assert list(vp.variant.power_ranges) == []
    for sph, cyl in [(-2.0, -1.0), (-25.0, -10.0), (9.0, 0.0)]:
        status = product_search._row_eye_status(vp, _mk_presc(db, sph, cyl, name=f"rx-{sph}"), "od")
        assert status == "eligible", (sph, cyl)


# 15. No fake RX PowerRange anywhere.
def test_15_no_fake_rx_powerrange(db, platinum_setup):
    co = platinum_setup["company"]
    rx_ids = [v.id for v in _all_vp(db, co) if v.availability == models.PricingAvailability.RX]
    count = db.query(models.PowerRange).filter(models.PowerRange.pricing_id.in_(rx_ids)).count()
    assert count == 0


# 16/17. HD = single_vision RX; HD UT = single_vision RX; kept distinct.
def test_16_17_hd_hdut_single_vision_rx(db, platinum_setup):
    for key in ("HD", "HD UT"):
        lm = platinum_setup["rx_models"][key]
        assert lm.category == models.LensCategory.SINGLE_VISION
    for row_name in ("1.5", "1.5 TR"):
        hd_vp = platinum_setup["rx_pricing"][("HD", row_name)]
        hdut_vp = platinum_setup["rx_pricing"][("HD UT", row_name)]
        assert hd_vp.availability == models.PricingAvailability.RX
        assert hdut_vp.availability == models.PricingAvailability.RX
        assert hd_vp.id != hdut_vp.id
        assert hd_vp.variant.design_variant == "HD"
        assert hdut_vp.variant.design_variant == "HDUT"


# 18. Office remains occupational/single-vision representation, RX.
def test_18_office_representation(db, platinum_setup):
    lm = platinum_setup["rx_models"]["Office"]
    assert lm.category == models.LensCategory.SINGLE_VISION
    vp = platinum_setup["rx_pricing"][("Office", "1.5")]
    assert vp.variant.design_variant == "Office"
    assert vp.availability == models.PricingAvailability.RX


# 19. Young remains correctly represented (single_vision, RX, design_variant="Young").
def test_19_young_representation(db, platinum_setup):
    lm = platinum_setup["rx_models"]["Young"]
    assert lm.category == models.LensCategory.SINGLE_VISION
    vp = platinum_setup["rx_pricing"][("Young", "1.5")]
    assert vp.variant.design_variant == "Young"
    assert vp.availability == models.PricingAvailability.RX


# 20. BI FOCAL / BI (HS) = bifocal, RX, no Stock PowerRange.
def test_20_bifocal_representation(db, platinum_setup):
    for key in ("BI FOCAL", "BI (HS)"):
        lm = platinum_setup["rx_models"][key]
        assert lm.category == models.LensCategory.BIFOCAL
    for (key, row) in [("BI FOCAL", "1.5"), ("BI (HS)", "1.5")]:
        vp = platinum_setup["rx_pricing"][(key, row)]
        assert vp.availability == models.PricingAvailability.RX
        assert list(vp.variant.power_ranges) == []


# 21. All six X-designs = progressive, RX.
def test_21_x_designs_progressive_rx(db, platinum_setup):
    for key in ("X-PLORE", "X-TEND", "X-TEND UT", "X-PERIENCE", "X-PERIENCE UT", "X-PERIENCE T"):
        lm = platinum_setup["rx_models"][key]
        assert lm.category == models.LensCategory.PROGRESSIVE, key
        vp = platinum_setup["rx_pricing"][(key, "1.5")]
        assert vp.availability == models.PricingAvailability.RX, key


# 22. Progressive price matrix cell counts: 15 each / 90 total.
def test_22_progressive_matrix_counts(db, platinum_setup):
    x_designs = ("X-PLORE", "X-TEND", "X-TEND UT", "X-PERIENCE", "X-PERIENCE UT", "X-PERIENCE T")
    total = 0
    for key in x_designs:
        n = sum(1 for (k, _), vp in platinum_setup["rx_pricing"].items() if k == key)
        assert n == 15, key
        total += n
    assert total == 90


# 23. Additions are not VariantPricing (this import never created base rows
# from Hard/Mira+/Mira Max/Mira Blue/Mira Drive/Mirror/Tinting/UV/Prism).
def test_23_additions_not_variant_pricing(db, platinum_setup):
    co = platinum_setup["company"]
    addition_names = {"hard", "mira +", "mira plus", "mira max", "mira blue", "mirror",
                      "tinting 1.5", "uv", "prism"}
    model_names = {m.name.lower() for m in db.query(models.LensModel).filter(models.LensModel.company_id == co.id).all()}
    assert not (addition_names & model_names)


# 24. Printed prices preserved exactly (spot-check a representative sample
# across Stock and every RX/Progressive table).
def test_24_printed_prices_preserved(db, platinum_setup):
    assert platinum_setup["stock_pricing"]["1.5"].price_pair == Decimal("250.00")
    assert platinum_setup["stock_pricing"]["1.74"].price_pair == Decimal("4200.00")
    assert platinum_setup["rx_pricing"][("RX Single Vision", "1.67 TR")].price_pair == Decimal("6400.00")
    assert platinum_setup["rx_pricing"][("MYO D", "1.67 TR")].price_pair == Decimal("8900.00")
    assert platinum_setup["rx_pricing"][("X-PERIENCE T", "1.74")].price_pair == Decimal("9000.00")


# 25. No prior manufacturer count changes (proxy: PLATINUM coexists with
# another company's row without cross-counting).
def test_25_no_cross_counting_with_other_companies(db, platinum_setup):
    other = _mk_company(db, "HOYA")
    cat2 = _mk_catalog(db, other)
    lm2 = _mk_model(db, other, "HOYA Model")
    v2 = _mk_variant(db, lm2, 1.6)
    vp2 = models.VariantPricing(variant_id=v2.id, availability=models.PricingAvailability.STOCK,
                                price_pair=Decimal("999.00"), currency="EGP", source_catalog_id=cat2.id)
    db.add(vp2); db.commit()
    assert len(_all_vp(db, platinum_setup["company"])) == 207
    assert len(_all_vp(db, other)) == 1


# 26. Global RX rule unchanged (covered directly by test_14; re-asserted
# against a non-PLATINUM synthetic company for isolation).
def test_26_global_rx_rule_unaffected(db, platinum_setup):
    other = _mk_company(db, "OtherRxCo")
    cat2 = _mk_catalog(db, other)
    lm2 = _mk_model(db, other, "RX Model")
    v2 = _mk_variant(db, lm2, 1.5)
    vp2 = models.VariantPricing(variant_id=v2.id, availability=models.PricingAvailability.RX,
                                price_pair=Decimal("2000.00"), currency="EGP", source_catalog_id=cat2.id)
    db.add(vp2); db.commit(); db.refresh(vp2)
    status = product_search._row_eye_status(vp2, _mk_presc(db, -12.0, -1.0, name="global-rx"), "od")
    assert status == "eligible"


# 27/28. DIVEL overlap safety / Maxxee overlapping-band behavior are generic,
# manufacturer-agnostic mechanisms in product_search.py - unchanged because
# this import touches no generic backend code file at all (see
# test_divel_import.py / test_maxxee_import.py, re-run alongside this file
# for the actual regression proof).
def test_27_28_generic_overlap_mechanisms_untouched(db, platinum_setup):
    import inspect
    assert "PLATINUM" not in inspect.getsource(product_search)


# 29. D1 scalar-diameter column stays dormant (real column, never populated).
def test_29_d1_column_dormant(db, platinum_setup):
    co = platinum_setup["company"]
    variants = (db.query(models.LensVariant).join(models.LensModel)
                  .filter(models.LensModel.company_id == co.id).all())
    assert len(variants) == 16 + 191   # one variant per pricing row (no shared variants)
    assert all(v.diameter is None for v in variants)


# ===== "1.5 BASE 2-4-8" / "1.5 POLARIZED" domain correction: plano-only SUN
# stock, never ordinary tiny-range prescription lenses. =====

# 30. "1.5 BASE 2-4-8": classified Sun, plano-only, Base Curve 2/4/8
# preserved as commercial evidence (never an optical power value).
def test_30_base_2_4_8_sun_plano_base_curve(db, platinum_setup):
    v = platinum_setup["stock_variants"]["1.5 BASE 2-4-8"]
    pr = platinum_setup["stock_ranges"]["1.5 BASE 2-4-8"]
    assert v.treatment_band == "Sun"
    assert v.design_variant == "Base Curve 2/4/8"
    assert pr.sph_min == 0.0 and pr.sph_max == 0.0
    assert pr.cyl_min == 0.0 and pr.cyl_max == 0.0
    assert pr.total_power_min == 0.0 and pr.total_power_max == 0.0 and pr.max_cyl_abs == 0.0
    # "2-4-8" never leaks into any optical field.
    for val in (2.0, 4.0, 8.0, -2.0, -4.0, -8.0):
        assert pr.sph_min != val and pr.sph_max != val


# 31. "1.5 POLARIZED" (Stock): classified Sun, polarized mapping retained,
# plano-only - distinct from the ordinary RX-table Polarized rows.
def test_31_polarized_stock_sun_plano(db, platinum_setup):
    v = platinum_setup["stock_variants"]["1.5 POLARIZED"]
    pr = platinum_setup["stock_ranges"]["1.5 POLARIZED"]
    assert "Sun" in v.treatment_band
    assert "Polarized" in v.treatment_band
    assert pr.sph_min == 0.0 and pr.sph_max == 0.0
    assert pr.total_power_min == 0.0 and pr.total_power_max == 0.0 and pr.max_cyl_abs == 0.0
    # Distinct from the RX-table "1.5 POLARIZED" rows (ordinary Rx product).
    rx_polarized = platinum_setup["rx_pricing"][("HD", "1.5 POLARIZED")]
    assert rx_polarized.variant.treatment_band == "Polarized"
    assert rx_polarized.variant.treatment_band != v.treatment_band
    assert list(rx_polarized.variant.power_ranges) == []   # RX row has no range at all


# 32. Both rows reject every non-zero Rx and accept only exact plano.
def test_32_both_reject_nonzero_accept_only_plano(db, platinum_setup):
    for key in ("1.5 BASE 2-4-8", "1.5 POLARIZED"):
        pr = platinum_setup["stock_ranges"][key]
        assert matcher.check_power_range(pr, _mk_presc(db, 0.0, 0.0, name=f"{key}-plano"), "od")[0] is True
        for sph, cyl in [(0.25, 0.0), (-0.25, 0.0), (0.0, 0.25), (0.0, -0.25), (1.0, -1.0)]:
            ok, _ = matcher.check_power_range(pr, _mk_presc(db, sph, cyl, name=f"{key}-{sph}-{cyl}"), "od")
            assert ok is False, (key, sph, cyl)


# 33. The ordinary +-0.25 Stock coarse-box tolerance never leaks into these
# two rows (would otherwise let SPH 0.25 wrongly pass a printed 0/0 row).
def test_33_no_ordinary_tolerance_leak(db, platinum_setup):
    for key in ("1.5 BASE 2-4-8", "1.5 POLARIZED"):
        pr = platinum_setup["stock_ranges"][key]
        assert pr.total_power_min == 0.0    # G3 hard boundary set on BOTH sides
        assert pr.total_power_max == 0.0
        ok, _ = matcher.check_power_range(pr, _mk_presc(db, 0.25, 0.0, name=f"{key}-tol-leak"), "od")
        assert ok is False, key


# 34. The other 14 Stock products' range behaviors, PLUS-only/MINUS-only
# rules, CYL enforcement, and PLATINUM PLUS / Blu STEEL G2 identities are
# all unaffected by this metadata-only correction.
def test_34_other_stock_products_unaffected(db, platinum_setup):
    pr_60 = platinum_setup["stock_ranges"]["1.5 (60)"]
    assert matcher.check_power_range(pr_60, _mk_presc(db, 3.0, name="60-plus"), "od")[0] is True
    assert matcher.check_power_range(pr_60, _mk_presc(db, -1.0, name="60-minus"), "od")[0] is False
    for key in ("1.67", "1.74"):
        pr = platinum_setup["stock_ranges"][key]
        assert matcher.check_power_range(pr, _mk_presc(db, 2.0, name=f"{key}-plus"), "od")[0] is False
    pr15 = platinum_setup["stock_ranges"]["1.5"]
    assert matcher.check_power_range(pr15, _mk_presc(db, 5.0, name="15-beyond"), "od")[0] is False
    assert matcher.check_power_range(pr15, _mk_presc(db, 3.0, -3.0, name="15-cyl-out"), "od")[0] is False
    assert platinum_setup["stock_pricing"]["PLATINUM PLUS"].price_pair == Decimal("900.00")
    assert platinum_setup["stock_variants"]["Blu STEEL G2"].index_value == 1.6
