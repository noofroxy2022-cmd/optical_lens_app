"""Unit tests for app/catalog_corrections.py - the single centralized source
of the Catalog Truth Audit (2026-09-18) Section A1-A6 corrections.

Fast, isolated, no DB: exercises the pure functions directly to pin the exact
proven scope (company, model, index, design_variant, coating - never a
blanket/company-wide or index-wide rule beyond what audit.md proves).
See test_audit_a1_a6_pipeline_persistence.py for the end-to-end ingestion
proof, and test_audit_a1_a6_data_corrections.py for the live-db check.
"""
from decimal import Decimal

from app import models
from app import catalog_corrections as cc


def _identity(company_name, index_value, material_enum=models.MaterialType.CR39,
              model_name="Some Model", category=models.LensCategory.SINGLE_VISION.value,
              design_variant=None, design_type_enum=models.DesignType.SPHERICAL, is_asph=False):
    return cc.corrected_identity(
        company_name=company_name, model_name=model_name, category=category,
        index_value=index_value, design_variant=design_variant,
        material_enum=material_enum, design_type_enum=design_type_enum, is_asph=is_asph)


# --------------------------------------------------------------- A1 (ZEISS)
def test_a1_zeiss_1_53_becomes_trivex():
    material, _, _ = _identity("ZEISS", 1.53)
    assert material == models.MaterialType.TRIVEX


def test_a1_zeiss_other_indices_stay_untouched():
    for idx in (1.5, 1.6, 1.67, 1.74):
        material, _, _ = _identity("ZEISS", idx)
        assert material == models.MaterialType.CR39


def test_a1_non_zeiss_at_1_53_untouched():
    material, _, _ = _identity("Other", 1.53)
    assert material == models.MaterialType.CR39


# --------------------------------------------------------------- A2 (Pixel)
def test_a2_pixel_1_53_becomes_trivex():
    material, _, _ = _identity("Pixel", 1.53)
    assert material == models.MaterialType.TRIVEX


def test_a2_pixel_other_indices_stay_untouched():
    for idx in (1.5, 1.56, 1.61, 1.67, 1.74):
        material, _, _ = _identity("Pixel", idx)
        assert material == models.MaterialType.CR39


# --------------------------------------------------------------- A3 (HOYA Mineral)
def test_a3_hoya_mineral_becomes_glass_regardless_of_index():
    for idx in (1.52, 1.6, 1.7, 1.81, 1.9):
        material, _, _ = _identity("HOYA", idx, model_name="Mineral",
                                    category=models.LensCategory.PROGRESSIVE.value)
        assert material == models.MaterialType.GLASS


def test_a3_hoya_non_mineral_model_untouched():
    material, _, _ = _identity("HOYA", 1.6, model_name="Nulux PNX")
    assert material == models.MaterialType.CR39


def test_a3_never_overrides_an_already_resolved_material():
    # Guard: only ever fires when the raw/extracted value is still the
    # audit-proven wrong default (CR39) - never clobbers a differently
    # resolved value (e.g. a future correctly-POLYCARBONATE Mineral row).
    material, _, _ = _identity("HOYA", 1.6, model_name="Mineral",
                                material_enum=models.MaterialType.POLYCARBONATE)
    assert material == models.MaterialType.POLYCARBONATE


# --------------------------------------------------------------- A6 (Pixel design_type)
def test_a6_pixel_single_vision_base_sku_at_proven_indices_becomes_aspherical():
    for idx in (1.56, 1.61, 1.67):
        _, design_type, is_asph = _identity("Pixel", idx, model_name="Pixel")
        assert design_type == models.DesignType.ASPHERICAL
        assert is_asph is True


def test_a6_does_not_generalize_to_other_indices():
    for idx in (1.5, 1.53, 1.74):
        _, design_type, is_asph = _identity("Pixel", idx, model_name="Pixel")
        assert design_type == models.DesignType.SPHERICAL
        assert is_asph is False


def test_a6_does_not_generalize_to_other_models_or_design_variants():
    # Opal (a different model) stays untouched even at a proven index.
    _, design_type, is_asph = _identity("Pixel", 1.56, model_name="Opal")
    assert design_type == models.DesignType.SPHERICAL and is_asph is False
    # Free Form / High Definition siblings at the same index are proven
    # (still) Spherical on this catalog - only the plain/base SKU is Aspheric.
    _, design_type, is_asph = _identity("Pixel", 1.56, model_name="Pixel", design_variant="Free Form")
    assert design_type == models.DesignType.SPHERICAL and is_asph is False


def test_a6_does_not_generalize_to_other_categories():
    _, design_type, is_asph = _identity(
        "Pixel", 1.56, model_name="Pixel", category=models.LensCategory.PROGRESSIVE.value)
    assert design_type == models.DesignType.SPHERICAL and is_asph is False


def test_a6_never_overrides_an_already_resolved_design_type():
    _, design_type, is_asph = _identity(
        "Pixel", 1.56, model_name="Pixel", design_type_enum=models.DesignType.DOUBLE_ASPHERICAL, is_asph=True)
    assert design_type == models.DesignType.DOUBLE_ASPHERICAL


# --------------------------------------------------------------- A4 (Maxxee market_scope)
def _pricing(company_name, coating_name, index_value, availability="stock",
             market_scope="Egypt", price=Decimal("1000"), is_asph=True):
    return cc.corrected_pricing(
        company_name=company_name, coating_name=coating_name, index_value=index_value,
        availability=availability, is_asph=is_asph, market_scope=market_scope, price=price)


def test_a4_maxxee_1_6_asph_hmc_plus_stock_egypt_becomes_out_of_egypt():
    scope, _ = _pricing("Maxxee", "H.M.C+", 1.6, is_asph=True)
    assert scope == "Out Of Egypt"


def test_a4_does_not_generalize_to_sibling_index():
    scope, _ = _pricing("Maxxee", "H.M.C+", 1.56)
    assert scope == "Egypt"


def test_a4_does_not_generalize_to_other_coatings_or_companies():
    scope, _ = _pricing("Maxxee", "H.M.C", 1.6)
    assert scope == "Egypt"
    scope, _ = _pricing("Other", "H.M.C+", 1.6)
    assert scope == "Egypt"


def test_a4_never_overrides_an_already_corrected_scope():
    scope, _ = _pricing("Maxxee", "H.M.C+", 1.6, market_scope="Out Of Egypt")
    assert scope == "Out Of Egypt"


def test_a4_does_not_generalize_to_spherical_sibling():
    # Review finding: audit.md A4 proves this ONLY for the "1.6 ASPH H.M.C+
    # Stock" row. A Spherical sibling at the exact same
    # company/coating/index/availability/market_scope is a DIFFERENT,
    # unproven commercial identity and must stay untouched.
    scope, _ = _pricing("Maxxee", "H.M.C+", 1.6, is_asph=False)
    assert scope == "Egypt"


# --------------------------------------------------------------- A5 (Pixel Astro price)
def test_a5_pixel_astro_1_56_stock_egypt_remaps_to_proven_rate():
    _, price = _pricing("Pixel", "Astro", 1.56, price=Decimal("1300.00"))
    assert price == Decimal("900")
    _, price = _pricing("Pixel", "Astro", 1.56, price=Decimal("1400.00"))
    assert price == Decimal("1000")


def test_a5_does_not_invent_a_fourth_band_or_touch_other_prices():
    # Any price other than the two catalog-proven wrong values passes through
    # untouched - never generalized into "any Astro/1.56/Egypt price gets
    # remapped", and never used to fabricate a new row/band.
    _, price = _pricing("Pixel", "Astro", 1.56, price=Decimal("700.00"))
    assert price == Decimal("700.00")


def test_a5_does_not_generalize_to_other_indices_or_coatings():
    _, price = _pricing("Pixel", "Astro", 1.5, price=Decimal("1300.00"))
    assert price == Decimal("1300.00")
    _, price = _pricing("Pixel", "Astro+B", 1.56, price=Decimal("1300.00"))
    assert price == Decimal("1300.00")


def test_a5_does_not_generalize_to_rx_or_out_of_egypt_routes():
    _, price = _pricing("Pixel", "Astro", 1.56, availability="rx", price=Decimal("1300.00"))
    assert price == Decimal("1300.00")
    _, price = _pricing("Pixel", "Astro", 1.56, market_scope="Out Of Egypt", price=Decimal("1300.00"))
    assert price == Decimal("1300.00")
