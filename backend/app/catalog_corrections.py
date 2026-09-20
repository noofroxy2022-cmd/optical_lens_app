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
from typing import Dict, FrozenSet, Optional, Tuple

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


# Special Lenses architecture (owner-confirmed, 2026-09-19): the seller/search
# top-level grouping "Special Lenses" is NOT a new LensCategory - it is a
# seller/search grouping over catalog-proven subtype categories that already
# fit the existing schema. "Occupational / Office" is the first proven
# subtype family; models.LensCategory.OFFICE already existed in the schema
# (models.py, unused until now) and required no migration. Future proven
# families (Young/Anti-Fatigue, Myopia Control, ...) get their own new
# LensCategory member the same way, never a schema redesign.
OCCUPATIONAL_OFFICE_MODELS: Dict[str, FrozenSet[str]] = {
    # Hoya_Price_List_2025_Updated.pdf pp.25-26, headed "Occupational Lenses
    # (RX)" - never "Progressive Lenses (RX)". Currently stored as
    # category=PROGRESSIVE (a known pre-existing importer quirk, see
    # addon_scope_evidence.py / progressive_add_evidence.py's own
    # excluded-model lists, which document this exact gap).
    "HOYA": frozenset({
        "Supereader B", "WorkSmart", "WorkSmart PNX",
        "iD WorkStyle", "iD WorkStyle PNX",
    }),
    # SCOPE catalog: "Office Design / Indoor" section with explicit near/
    # intermediate working-distance descriptions. Currently stored as
    # category=SINGLE_VISION.
    "SCOPE": frozenset({
        "SCOPE Office Doctor", "SCOPE Office Officestar",
    }),
}

# SCOPE.pdf p.9 "Young Lenses / عدسات ضد الإجهاد للشباب": explicit catalog
# text - designed for ages 18-40, relieves strain/headache from heavy
# electronic-device use and prolonged reading; improves reading/intermediate
# vision (especially the lower lens area) while remaining usable at distance/
# driving. Currently stored as category=SINGLE_VISION. Strict scope: ONLY
# this proven SCOPE product - PLATINUM "Young" (bare price table, no catalog
# description) and BBGR "Anti-Fatigue"/"Extenso" (bare price table, no
# catalog description; owner already confirmed BBGR identity is not to be
# changed) are deliberately excluded for insufficient evidence, and ZEISS
# "SmartLife Young" is deliberately excluded because ZEISS's OWN catalog
# heading classifies it as Single Vision, not a Special Lenses subtype.
ANTI_FATIGUE_MODELS: Dict[str, FrozenSet[str]] = {
    "SCOPE": frozenset({"SCOPE Young Shabab"}),
}

# Owner clarification (2026-09-19): "Myopia Control" is ONE generic,
# functional Special Lenses subtype - never a manufacturer/product name.
# Different manufacturers use different commercial names for products
# serving this same function (SCOPE "Myoblock/Metavision", ZEISS "MyoCare" /
# "MyoCare S" / "MyoActive", ...); all proven members map to the SAME
# models.LensCategory.MYOPIA_CONTROL / use_mode="myopia_control" - never a
# per-product category such as a hypothetical "MYOBLOCK" or "MYOCARE". This
# dict is exactly the extension point for a later manufacturer: add one more
# `"COMPANY": frozenset({"Exact Product Name", ...})` entry once THAT
# product's own catalog evidence (or explicit owner confirmation) proves it
# belongs here - never a substring/name-pattern match on "Myo" or similar,
# and never a seller-UI or category redesign.
#
# SCOPE.pdf pp.13-15 "Myoblock Lenses / عدسات مايوبلوك لإيقاف تدهور النظر
# عند الأطفال" ("...to stop vision deterioration in children") and "myoblock
# reduces the myopia progression": explicit myopia-control purpose. Printed
# power range (Sph -0.50 to -10.00, Cyl to -4.00) is representable via the
# existing PowerRange sph/cyl fields - no new eligibility mechanism. Currently
# stored as category=SINGLE_VISION. PLATINUM "MYO D" (bare price table, no
# catalog description - open owner question, not resolved) is deliberately
# excluded.
#
# ZEISS_Main_Catalog.pdf pp.51-52 "ZEISS MyoCare Lenses": MyoCare (C.A.R.E.,
# 7mm central zone, +4.6D defocus) and MyoCare S (C.A.R.E., 9mm central zone,
# +3.8D defocus) - two catalog-proven distinct optical designs, both ingested
# (owner-confirmed 2026-09-19/20) via app/zeiss_myopia_control_evidence.py's
# reconcile(), which creates them directly with this category (they are new
# products, not a reclassification of an existing wrong-categoried row).
# Listed here too so a future re-import via the standard extraction path
# would resolve to the same category. ZEISS MyoActive remains PROVEN but NOT
# added here: its own catalog page prints "Available from 1st October 2026"
# (after the current project date) and its power-range chart is combined
# with MyoCare/MyoCare S RX 1.6/1.59 with no per-product split proven
# separately - a separate ingestion task, not a category question.
MYOPIA_CONTROL_MODELS: Dict[str, FrozenSet[str]] = {
    "SCOPE": frozenset({"SCOPE Myoblock Metavision (Myoblock)"}),
    "ZEISS": frozenset({"MyoCare", "MyoCare S"}),
}


def corrected_category(company_name: Optional[str], model_name: Optional[str],
                        category_enum: models.LensCategory) -> models.LensCategory:
    """HOYA "Bi-Focal" (category-classification review, 2026-09-19).

    Hoya_Price_List_2025_Updated.pdf p.27 explicitly headers this product
    "Bi-Focal Lenses (RX)" - never "Progressive Lenses (RX)". The prior
    category=PROGRESSIVE was already self-documented as wrong, not
    intentional, in addon_scope_evidence.py's own comment ("Category below
    is the current importer representation, not a claim that bifocals are
    optically progressive"). models.LensCategory.BIFOCAL already exists and
    is actively used by 4 other manufacturers (Pixel, BBGR, PLATINUM, SCOPE)
    - not a novel schema usage.

    Deliberately narrow: matches ONLY this one HOYA model by exact name.
    Never touches HOYA's genuine "...Progressive Lenses (RX)" families
    (Amplitude Plus, Balansis, Daynamic, iD LifeStyle/MyStyle/MySelf).
    "Mineral" - once left for separate review because the catalog proved it
    mixes a plain and a genuinely-progressive sub-line under one model - is
    now resolved by the dedicated model-split in
    app/hoya_mineral_summit_evidence.py (owner-confirmed 2026-09-20), not by
    this function. Idempotent: a row already BIFOCAL is returned unchanged.

    Occupational/Office (Special Lenses architecture, 2026-09-19): HOYA's
    Supereader B / WorkSmart(+PNX) / iD WorkStyle(+PNX) and SCOPE's Office
    Doctor / Office Officestar are the SAME owner-confirmed "Occupational /
    Office" Special Lenses subtype (see OCCUPATIONAL_OFFICE_MODELS above for
    the exact catalog citations). Deliberately does NOT touch: ZEISS (catalog
    has an Office Lenses section but no rows are currently ingested), PLATINUM
    "Office" (weaker evidence per the 2026-09-19 audit), or BBGR "Anti-Fatigue"
    (no preserved per-product identity in the DB). Idempotent: a row already
    OFFICE is returned unchanged.

    Young/Anti-Fatigue and Myopia Control (Special Lenses architecture,
    2026-09-19): SCOPE's Young/Shabab and Myoblock/Metavision are each their
    own proven, distinct Special Lenses subtype (see ANTI_FATIGUE_MODELS /
    MYOPIA_CONTROL_MODELS above for the exact catalog citations) - never
    folded into OFFICE or into each other, since each is a materially
    different catalog-proven purpose. Idempotent: a row already in its target
    category is returned unchanged.
    """
    if (company_name == "HOYA" and (model_name or "").strip().lower() == "bi-focal"
            and category_enum == models.LensCategory.PROGRESSIVE):
        return models.LensCategory.BIFOCAL
    if model_name in OCCUPATIONAL_OFFICE_MODELS.get(company_name, frozenset()):
        return models.LensCategory.OFFICE
    if model_name in ANTI_FATIGUE_MODELS.get(company_name, frozenset()):
        return models.LensCategory.ANTI_FATIGUE
    if model_name in MYOPIA_CONTROL_MODELS.get(company_name, frozenset()):
        return models.LensCategory.MYOPIA_CONTROL
    return category_enum


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
