"""Catalog Truth Audit (2026-09-18) Section A - the ONE centralized source
for the six catalog-proven, zero-ambiguity ingestion corrections (A1-A6).

Mirrors technology_evidence.py's EXACT-match, heavily-cited registry style:
every guard below fires ONLY for the precise identity the audit proved wrong
against the real catalog PDF, never a fuzzy/substring match, and NEVER
generalized beyond that proven scope (see each function's docstring for the
exact audit citation and the ambiguous/unproven neighbors deliberately left
untouched).

This module is called from exactly two places in app/crud.py
(_prepare_extraction_row and attach_range_to_existing_pricing) - the single
funnel every extraction-confirmation path already uses to resolve
material/design_type/market_scope/price from raw extracted values. Wiring
the corrections in there (rather than backend/release_runtime.db directly,
as the original one-time fix did) means a clean rebuild - drop the db,
re-run extraction/review/confirm from the source PDFs - reproduces every
one of these six corrections automatically, with no manual SQL step.

Every function is a pure, idempotent value transform: given an
already-corrected value, it returns that same value unchanged (each guard
checks the RAW/current value still equals the audit-proven wrong one before
firing), so re-running ingestion any number of times is safe.
"""
from decimal import Decimal
from typing import Optional, Tuple

from app import models

_TRIVEX_1_53_COMPANIES = frozenset({"ZEISS", "Pixel"})


def _corrected_material(company_name: Optional[str], model_name: Optional[str],
                         index_value: Optional[float],
                         material_enum: models.MaterialType) -> models.MaterialType:
    """A1 (ZEISS) / A2 (Pixel) / A3 (HOYA Mineral).

    A1: audit.md A1 - ZEISS_Main_Catalog.pdf p.8 (repeated pp.10,13,15,22)
    prints index 1.53 as "1.53 (Trivex)" three times, with Abbe/Density
    constants distinct from CR39's. Proven for EVERY ZEISS variant at 1.53
    (all 7 in the audited catalog) - not generalized to 1.5/1.6/1.67/1.74.

    A2: audit.md A2 - pixel_phase4_test.pdf p.9 headlines "Pixel Trivex 1.53
    - High Impact Resistant Lens" explicitly. Proven for EVERY Pixel variant
    at 1.53 (all 9 in the audited catalog) - not generalized to other Pixel
    indices.

    A3: audit.md A3 - Hoya_Price_List_2025_Updated.pdf p.28 prints "Mineral
    Lenses" as a distinct line, p.39 confirms it's physically different
    (excluded from the "write on lens" service). Scoped to the "Mineral"
    model by name (its indices vary: 1.52/1.6/1.7/1.81/1.9 - not
    index-scoped like A1/A2). models.MaterialType.GLASS already exists for
    exactly this case (SCOPE precedent).

    Never overrides a material already resolved to something other than the
    audit-proven wrong default (CR39) - idempotent and never clobbers a
    differently-resolved value.
    """
    if material_enum != models.MaterialType.CR39:
        return material_enum
    if company_name in _TRIVEX_1_53_COMPANIES and index_value == 1.53:
        return models.MaterialType.TRIVEX
    if company_name == "HOYA" and (model_name or "").strip().lower() == "mineral":
        return models.MaterialType.GLASS
    return material_enum


_PIXEL_ASPHERICAL_INDEXES = frozenset({1.56, 1.61, 1.67})


def _corrected_design_type(company_name: Optional[str], model_name: Optional[str],
                            category: Optional[str], index_value: Optional[float],
                            design_variant: Optional[str],
                            design_type_enum: models.DesignType,
                            is_asph: bool) -> Tuple[models.DesignType, bool]:
    """A6 (Pixel design_type).

    audit.md A6 - pixel_phase4_test.pdf p.13 proves the plain/base Pixel
    Single-Vision Stock SKU (no design_variant - i.e. neither the "Free Form"
    nor "High Definition" siblings, which stay genuinely Spherical on this
    catalog) is Aspheric at indices 1.56/1.61/1.67 only. Index 1.5 stays
    Spherical (proven), and the audit leaves the analogous 1.53 and 1.74
    plain rows deliberately AMBIGUOUS/unproven (audit.md Section C6) - never
    included here. "Opal" (a distinct model at the same company) is untouched
    since this is proven for the "Pixel" model specifically.

    Never overrides a design_type already resolved to something other than
    the audit-proven wrong default (Spherical, not aspherical).
    """
    if design_type_enum != models.DesignType.SPHERICAL or is_asph:
        return design_type_enum, is_asph
    if (company_name == "Pixel"
            and (model_name or "").strip().lower() == "pixel"
            and category == models.LensCategory.SINGLE_VISION.value
            and index_value in _PIXEL_ASPHERICAL_INDEXES
            and not (design_variant or "").strip()):
        return models.DesignType.ASPHERICAL, True
    return design_type_enum, is_asph


def corrected_identity(*, company_name: Optional[str], model_name: Optional[str],
                        category: Optional[str], index_value: Optional[float],
                        design_variant: Optional[str],
                        material_enum: models.MaterialType,
                        design_type_enum: models.DesignType,
                        is_asph: bool) -> Tuple[models.MaterialType, models.DesignType, bool]:
    """Single entry point for the LensVariant-identity corrections (A1/A2/A3
    material, A6 design_type). Called once, centrally, from crud.py wherever
    a LensVariant's identity fields are resolved from extraction data -
    never scattered per-manufacturer branching in crud.py itself."""
    material_enum = _corrected_material(company_name, model_name, index_value, material_enum)
    design_type_enum, is_asph = _corrected_design_type(
        company_name, model_name, category, index_value, design_variant,
        design_type_enum, is_asph)
    return material_enum, design_type_enum, is_asph


def _corrected_market_scope(company_name: Optional[str], coating_name: Optional[str],
                             index_value: Optional[float], availability: Optional[str],
                             is_asph: bool, market_scope: Optional[str]) -> Optional[str]:
    """A4 (Maxxee market_scope).

    audit.md A4 - "Maxxee By Hoya P.L 2025 - R-1-1.pdf" p.2 explicitly
    captions the **1.6 ASPH** H.M.C+ Stock row "Stock Out Of Egypt (5-7
    Days)", but it was resolved as market_scope='Egypt'. Scoped tightly to
    this exact commercial identity, including design (is_asph): the sibling
    1.56 ASPH H.M.C+ Stock row is genuinely 'Egypt' in the catalog, and a
    Spherical row at the same company/coating/index/availability is a
    different, unproven identity - neither may be flipped by a broader
    company/coating/index-only rule.
    """
    if (market_scope or "").strip().lower() != "egypt":
        return market_scope
    if (company_name == "Maxxee" and (coating_name or "").strip() == "H.M.C+"
            and index_value == 1.6 and is_asph
            and (availability or "").strip().lower() == "stock"):
        return "Out Of Egypt"
    return market_scope


_ASTRO_WRONG_TO_PROVEN_RATE = {
    Decimal("1300"): Decimal("900"),
    Decimal("1400"): Decimal("1000"),
}


def _corrected_price(company_name: Optional[str], coating_name: Optional[str],
                      index_value: Optional[float], availability: Optional[str],
                      market_scope: Optional[str], price: Optional[Decimal]) -> Optional[Decimal]:
    """A5 (Pixel Astro price).

    audit.md A5 - pixel_phase4_test.pdf p.13: Pixel's "Astro" coating (Stock,
    Egypt, index 1.56) was priced at the "Astro+B" rate (1300/1400) instead
    of Astro's own proven rate (900/1000). Deliberately a narrow VALUE remap
    of exactly the two proven-wrong prices on this exact identity - never a
    blanket "any Astro/1.56/Egypt price" rule, and never invents a price for
    a band this identity doesn't already have (see audit.md Section G item 5:
    only the 3 existing rows are corrected, no 4th band is fabricated).
    """
    if price is None:
        return price
    if (company_name == "Pixel" and (coating_name or "").strip() == "Astro"
            and index_value == 1.56
            and (availability or "").strip().lower() == "stock"
            and (market_scope or "").strip().lower() == "egypt"):
        return _ASTRO_WRONG_TO_PROVEN_RATE.get(price, price)
    return price


def corrected_pricing(*, company_name: Optional[str], coating_name: Optional[str],
                       index_value: Optional[float], availability: Optional[str],
                       is_asph: bool, market_scope: Optional[str],
                       price: Optional[Decimal]) -> Tuple[Optional[str], Optional[Decimal]]:
    """Single entry point for the VariantPricing corrections (A4 market_scope,
    A5 price). Called from BOTH crud.py sites that resolve a commercial
    identity's market_scope - _prepare_extraction_row (which writes
    VariantPricing) and attach_range_to_existing_pricing (which only reads
    it, to match an existing row) - so a range-only extraction's own
    identity match always agrees with the corrected, persisted value rather
    than recomputing a stale pre-correction one independently."""
    corrected_scope = _corrected_market_scope(company_name, coating_name, index_value,
                                               availability, is_asph, market_scope)
    corrected_price = _corrected_price(company_name, coating_name, index_value,
                                        availability, market_scope, price)
    return corrected_scope, corrected_price
