"""Canonical customer-facing technology intent (V1.2 core-workflow phase).

Maps EXACT, catalog-proven commercial evidence (coating name / treatment_band /
color_variant, per manufacturer) to manufacturer-agnostic canonical
capabilities: "blue_light", "photo_gray", "photo_brown". A combined intent
(blue_photo_gray / blue_photo_brown) requires ALL of its component
capabilities to be proven on the SAME commercial row - never OR, never
inferred from one capability alone.

This registry is deliberately an EXACT-match lookup, never a substring/fuzzy
scan. Every entry below was verified against the actual 1854-row v12_dev.db
catalog (Phase 4 audit, V1.2 core-workflow task) before being added. A term
that merely CONTAINS a suggestive word ("Blue", "Gray", "Photo") without this
kind of confirmed, purpose-built naming is deliberately left OUT - Sun/Mirror/
Polarized tint colors are never treated as photochromic, and a bare colour
name is never treated as blue-light protection.

Adding a new manufacturer/term: add ONE tuple to _EVIDENCE below, citing the
exact catalog value. Do not add substring/regex matching here - if a term is
ambiguous, leave it out and it will correctly fall through to "not proven".
"""
from decimal import Decimal
from typing import Dict, FrozenSet, NamedTuple, Optional, Set, Tuple

BLUE_LIGHT = "blue_light"
PHOTO_GRAY = "photo_gray"
PHOTO_BROWN = "photo_brown"
IMPACT_RESISTANT = "impact_resistant"

# Hoya_Smart_Guide.pdf PDF p.8: PNX 1.53, "مقاومة كسر عالية جداً".
# Exact PNX model identities: Hoya_Price_List_2025_Updated.pdf pp.4,6,7,9,
# 12,14-16,19-24,26. Neither an arbitrary 1.53 nor a name containing PNX is proof.
_HOYA_PNX_MODELS = frozenset({
    "Hilux PNX", "Nulux PNX", "Sync III PNX", "Amplitude Plus PNX",
    "Daynamic PNX", "Balansis PNX", "iD LifeStyle PNX", "iD MyStyle PNX",
    "iD MySelf PNX", "WorkSmart PNX", "iD WorkStyle PNX",
})
# SCOPE.pdf PDF p.10 (SV), repeated ROW26 identities in pp.3-7,9,11-12:
# HiFlex / HiFlex Relax and PhotoGray versions explicitly say "مقاوم للكسر".
_SCOPE_IMPACT_TERMS = frozenset({
    "HiFlex Impact-Resistant", "HiFlex Relax Impact-Resistant Blue Light",
    "HiFlex PhotoGray Impact-Resistant",
    "HiFlex PhotoGray Relax Impact-Resistant Blue Light",
})
# A generic Trivex/polycarbonate enum or 1.53/1.59 is deliberately insufficient.
# PLATINUM.pdf p.2 prints only 1.59: do not broaden it into impact proof.

# Canonical customer-facing intents (Phase 3). "none" always passes.
INTENTS = (
    "none",
    "blue_light",
    "photo_gray",
    "photo_brown",
    "blue_photo_gray",
    "blue_photo_brown",
)

# intent -> required capability set (AND semantics - every bit must be proven
# on the SAME row). "none" requires nothing (always satisfied).
_REQUIRED: Dict[str, FrozenSet[str]] = {
    "none": frozenset(),
    "blue_light": frozenset({BLUE_LIGHT}),
    "photo_gray": frozenset({PHOTO_GRAY}),
    "photo_brown": frozenset({PHOTO_BROWN}),
    "blue_photo_gray": frozenset({BLUE_LIGHT, PHOTO_GRAY}),
    "blue_photo_brown": frozenset({BLUE_LIGHT, PHOTO_BROWN}),
}

# (company_name, field, exact_value) -> proven capability set.
# field is one of "coating", "treatment_band", "color_variant".
# Matching is EXACT on the .strip() value (case-sensitive - every value below
# is copied verbatim from the catalog); never a substring/contains check.
_EVIDENCE: Dict[Tuple[str, str, str], FrozenSet[str]] = {
    # ---- HOYA -------------------------------------------------------------
    # "Long Life Blue Control" is HOYA's own explicit blue-light coating name.
    ("HOYA", "coating", "Long Life Blue Control"): frozenset({BLUE_LIGHT}),
    # RECONCILED (Hoya_Price_List_2025.pdf, pages 7/10/12): "Sensity 2" is
    # explicitly printed as "Hilux 1.5 Sensity 2 ( Gray - Brown - Green )"
    # (p.7) and "Nulux iDENTITY ... Sensity 2 ( Gray - Brown - Green - Blue )"
    # (p.10); "Sensity Original" as "... Sensity Original ( Gray - Brown -
    # Green )" (p.12). Every one of these is ONE printed price per index
    # covering all listed colours (no per-colour price split anywhere in the
    # tables) - the same "combined descriptor proves every named colour"
    # reasoning already used for VISALL's "Gray / Brown". "Blue"/"Green" here
    # are colour options, never blue-light protection (kept separate from
    # BLUE_LIGHT below, per the task's own Sensity-Blue-is-not-BLC warning).
    ("HOYA", "color_variant", "Sensity 2"): frozenset({PHOTO_GRAY, PHOTO_BROWN}),
    ("HOYA", "color_variant", "Sensity Original"): frozenset({PHOTO_GRAY, PHOTO_BROWN}),
    # bare "Photo" color_variant (a handful of Mineral-glass rows) carries no
    # colour list anywhere in the supplied catalog - stays unmapped/ambiguous.

    # ---- ZEISS --------------------------------------------------------------
    # "BlueGuard" is ZEISS's own published blue-light treatment_band name.
    ("ZEISS", "treatment_band", "BlueGuard"): frozenset({BLUE_LIGHT}),
    # "PhotoFusion X" proves photochromic capability only - ZEISS's
    # color_variant column is unpopulated, so Gray/Brown is never proven and
    # no row combines PhotoFusion X with BlueGuard (single-valued field), so
    # no blue_photo_* entry exists for ZEISS.

    # ---- Synchrony ----------------------------------------------------------
    ("Synchrony", "treatment_band", "Blue HMC+"): frozenset({BLUE_LIGHT}),
    ("Synchrony", "treatment_band", "Photo Gray"): frozenset({PHOTO_GRAY}),
    # "Photo Fusion X" (Synchrony) proves photochromic capability only - no
    # colour named - left out. No row combines a Blue* and Photo* value
    # (treatment_band is single-valued), so no blue_photo_* entry.

    # ---- VISALL ---------------------------------------------------------
    ("VISALL", "treatment_band", "BlueCut"): frozenset({BLUE_LIGHT}),
    # "Photochromic" alone proves photochromic capability; colour comes from
    # the paired color_variant value on the SAME row (checked together below,
    # not as an independent color_variant-only rule, to avoid ever reusing a
    # bare "Gray"/"Brown" colour token that means a Sun/Mirror tint for a
    # different manufacturer, e.g. PLATINUM's plano Sun-Gray stock).
    ("VISALL", "treatment_band", "Photochromic"): frozenset(),
    ("VISALL", "treatment_band", "Photochromic + BlueCut"): frozenset({BLUE_LIGHT}),

    # ---- BBGR ---------------------------------------------------------------
    ("BBGR", "treatment_band", "Blu stop"): frozenset({BLUE_LIGHT}),
    # "Neva blu" (BBGR coating) is left OUT: no corroborating evidence proves
    # it names a blue-light technology rather than being a coincidental brand
    # name containing "blu" (Phase 4 - explicitly flagged ambiguous).

    # ---- Maxxee ---------------------------------------------------------
    ("Maxxee", "coating", "Blue U.V"): frozenset({BLUE_LIGHT}),
    ("Maxxee", "treatment_band", "Photo"): frozenset(),  # colour from color_variant
    # Maxxee never combines "Blue U.V" coating with "Photo" treatment_band on
    # the same row (verified) - no blue_photo_* combo exists for Maxxee.

    # ---- DIVEL ITALIA -----------------------------------------------------
    ("DIVEL ITALIA", "coating", "FotoColor Gray"): frozenset({PHOTO_GRAY}),
    ("DIVEL ITALIA", "coating", "FotoColor Brown"): frozenset({PHOTO_BROWN}),
    # "Aria Blue FotoColor GR" names both technologies in one coating value
    # (Blue + FotoColor + GR/Gray, using this manufacturer's own GR=Gray
    # abbreviation already established by "FotoColor Gray"/"FotoColor Brown").
    # No "...FotoColor BR" (Brown) value exists in the catalog, so only the
    # Gray combo is proven for DIVEL.
    ("DIVEL ITALIA", "coating", "Aria Blue FotoColor GR"): frozenset({BLUE_LIGHT, PHOTO_GRAY}),
    # "Blue Natural" is left OUT: ambiguous, no corroborating evidence
    # distinguishes a blue-light meaning from an unrelated tint/brand name.

    # ---- PLATINUM -----------------------------------------------------------
    ("PLATINUM", "treatment_band", "BlueCut"): frozenset({BLUE_LIGHT}),
    # "G2" is proven blue-light ONLY via this catalog's confirmed import notes
    # ("BlueCut + Super UV Protection technology") - the bare treatment_band
    # value "G2" carries no self-evident meaning, so this entry exists solely
    # because of that explicit textual catalog confirmation, not a guess.
    ("PLATINUM", "treatment_band", "G2"): frozenset({BLUE_LIGHT}),
    # "BLU STEEL" is left OUT: sits among PLATINUM's stylistic/tier branding
    # values (X-PERIENCE, X-TEND, Young, HD) with no corroborating note - no
    # confirmed blue-light meaning. PLATINUM's only colour evidence (plain
    # "Gray") is tied to Plano-only SUN stock, never photochromic - no
    # photo_gray/photo_brown entry exists for PLATINUM.

    # ---- SEIKO ----------------------------------------------------------
    ("SEIKO", "treatment_band", "BLUEBLOCK"): frozenset({BLUE_LIGHT}),
    # RECONCILED (Seiko_Pricelist_2025.pdf, p.4 "SEIKO SUN SOLUTIONS / SENSITY"):
    # explicitly names four colours - "Sensity 2 Green", "Sensity 2 Brown",
    # "Sensity 2 Grey", "Sensity 2 Blue" - as options of the ONE "Sensity 2"
    # line (the pricing tables on pp.2-4 print exactly one price per
    # index/design for "SENSITY 2", never a per-colour split), so - as with
    # HOYA/VISALL - the single stored value proves every listed colour.
    # "Sensity 2 Blue" is a COLOUR choice here, never confused with the
    # entirely separate, separately-priced "BLUEBLOCK" coating rows.
    ("SEIKO", "treatment_band", "SENSITY 2"): frozenset({PHOTO_GRAY, PHOTO_BROWN}),
    # RECONCILED (Seiko_Pricelist_2025.pdf, p.5 "SEIKO COATINGS & EXCEPTION"):
    # the marketing paragraph printed directly under the "SRC SCREEN" price
    # row states (Arabic) it helps reduce eye strain from prolonged screen
    # use "and exposure to blue light" (raw extract: "... ﻲﻓ ﺗﻘﻠﻴﻞ إﺟﻬﺎد اﻟﻌﻴﻦ
    # اﻟﻨﺎﺗﺞ ﻋﻦ اﻻﺳﺘﺨﺪام اﻟﻤﻄﻮّل ﻟﻠﺸﺎﺷﺎت واﻟﺘﻌﺮّض ﻟﻠﻀﻮء اﻷزرق"). This is a
    # distinct, explicit blue-light claim - unlike SRC ONE/ROAD/ULTRA/SUN on
    # the same page, whose paragraphs describe anti-reflective/anti-static,
    # driver-glare, or outdoor-contrast benefits with no blue-light mention.
    # The DB stores this coating as coatings.name == "SRC - SCREEN" (stock
    # rows only, both Egypt and Out-Of-Egypt market_scope, indices 1.5/1.6/
    # 1.67/1.74; no RX-route row exists for it) - each row is already its own
    # fully priced identity, so this is Type A (no add-on/price change).
    ("SEIKO", "coating", "SRC - SCREEN"): frozenset({BLUE_LIGHT}),

    # ---- SCOPE ------------------------------------------------------------
    ("SCOPE", "treatment_band", "Relax Blue Light"): frozenset({BLUE_LIGHT}),
    ("SCOPE", "treatment_band", "Relax Blue Light (Semi-Compressed)"): frozenset({BLUE_LIGHT}),
    ("SCOPE", "treatment_band", "Relax HeatGuard Blue Light (Semi-Compressed)"): frozenset({BLUE_LIGHT}),
    # SCOPE.pdf p.10 R13: HiFlex Relax explicitly says protection from blue light.
    ("SCOPE", "treatment_band", "HiFlex Relax Impact-Resistant Blue Light"): frozenset({BLUE_LIGHT}),
    ("SCOPE", "treatment_band", "HiFlex PhotoGray Impact-Resistant"): frozenset({PHOTO_GRAY}),
    ("SCOPE", "treatment_band", "PhotoGray Multi-color (7 shades)"): frozenset({PHOTO_GRAY}),
    ("SCOPE", "treatment_band", "Photo Glass (PhotoGray-Brown Extra Corning French)"): frozenset({PHOTO_GRAY, PHOTO_BROWN}),
    ("SCOPE", "treatment_band", "PhotoGray / PhotoBrown"): frozenset({PHOTO_GRAY, PHOTO_BROWN}),
    ("SCOPE", "treatment_band", "Transitions Gray-Brown"): frozenset({PHOTO_GRAY, PHOTO_BROWN}),
    ("SCOPE", "treatment_band", "Transitions PhotoGray Surface Coloring"): frozenset({PHOTO_GRAY}),
    ("SCOPE", "treatment_band", "Transitions PhotoGray-Brown Surface Coloring"): frozenset({PHOTO_GRAY, PHOTO_BROWN}),
    ("SCOPE", "treatment_band", "Transitions Relax PhotoGray Surface"): frozenset({PHOTO_GRAY}),
    ("SCOPE", "treatment_band", "Transitions Relax PhotoGray-Brown Surface"): frozenset({PHOTO_GRAY, PHOTO_BROWN}),
    ("SCOPE", "treatment_band", "HiFlex PhotoGray Relax Impact-Resistant Blue Light"): frozenset({BLUE_LIGHT, PHOTO_GRAY}),
    ("SCOPE", "treatment_band", "Transitions Relax Gray-Brown Blue Light"): frozenset({BLUE_LIGHT, PHOTO_GRAY, PHOTO_BROWN}),
    ("SCOPE", "treatment_band", "Transitions Relax Gray-Brown Blue Light VV"): frozenset({BLUE_LIGHT, PHOTO_GRAY, PHOTO_BROWN}),
    # "Relax Blue+Yellow Light Contrast" and "Night Rider (Blue+Yellow Light,
    # Day/Night Driving)" are left OUT of blue_light: catalog evidence
    # explicitly names these as a driving-contrast tint technology, a
    # different product purpose than standard blue-light screen protection -
    # treating them as equivalent would be exactly the kind of "Blue" text
    # without matching evidence this registry must avoid.
    # Sun/Mirror/Polarized colour values (Sun Gray, Sun Gray with Revo Mirror,
    # Sun Polarized Gray-Brown-Green, Blue/Yellow/Green/Purple/Rose tint menu)
    # are never treated as photochromic or blue-light evidence.

    # ---- Pixel ------------------------------------------------------------
    # RECONCILED (pixel_phase4_test.pdf):
    #   p.6 "Astro Coating" is described purely as an anti-reflective/
    #   hydrophobic surface treatment - no UV/blue-light claim anywhere -> a
    #   bare "Astro" coating is NEVER blue-light evidence.
    #   p.7 "Astro+ Uv 420 Protection": explicit text "توفر عدسات Astro+ ...
    #   حماية ... من ... الضوء الأزرق عالي الطاقة ... مع تقليل الضوء الأزرق
    #   الضار ضمن نطاق 400-420 نانومتر" (Astro+ provides protection from
    #   high-energy blue light, reducing harmful blue light in the 400-420nm
    #   band) - explicit, textual, unambiguous blue-light-protection proof.
    #   p.7 "Astro+ B Uv 420 Protection" (its own dedicated section): explicit
    #   "حماية فعّالة من الضوء الأزرق عالي الطاقة المنبعث من الشاشات الرقمية"
    #   (effective protection from high-energy blue light from digital
    #   screens) via a stated DUAL mechanism (raw material + coating) - same
    #   conclusion, independently confirmed.
    ("Pixel", "coating", "Astro+"): frozenset({BLUE_LIGHT}),
    ("Pixel", "coating", "Astro+B"): frozenset({BLUE_LIGHT}),
    # p.11 "Transmatic Lens - Pixel": extensive descriptive text (transparent
    # indoors, gradually darkens under sun exposure, returns to clarity
    # instantly indoors, automatic light-adaptive control) - a textbook
    # photochromic description, not just a brand name -> photochromic
    # CAPABILITY proven. "Transition/G/B" carries the same globally-standard
    # trademarked photochromic term. However NO page anywhere in this catalog
    # spells out what the "G"/"B" letters in "Transmatic/G/B",
    # "Transmatic/B/G", "Transmatic/G", "Transition/G/B" mean (no legend, no
    # "Gray"/"Brown" word appears anywhere in the extracted text) - unlike
    # HOYA/SEIKO/VISALL/Maxxee, which all spell the colour out in English.
    # Per the task's explicit instruction ("do not infer abbreviation meaning
    # merely from convention... keep only that specific distinction
    # ambiguous"), photochromic capability is recorded as proven-but-colour-
    # unresolved (empty set - matches the same pattern as VISALL's bare
    # "Photochromic" entry) rather than guessing G=Gray/B=Brown.
    ("Pixel", "color_variant", "Transmatic/G/B"): frozenset(),
    ("Pixel", "color_variant", "Transmatic/B/G"): frozenset(),
    ("Pixel", "color_variant", "Transmatic/G"): frozenset(),
    ("Pixel", "color_variant", "Transition/G/B"): frozenset(),
    # "Polz/G/B", "Polz/G/B/G15" are Polarized - explicitly NOT photochromic
    # (same rule as every other manufacturer). "DWEAR/B" is never described
    # anywhere in the catalog - stays fully unmapped, not even proven
    # photochromic. Neither gets an entry.
}


# Type B optional fulfillment. V1.3.3 applicability is an exact catalog-identity
# whitelist (addon_scope_evidence.py), independent of printed amount/unit proof.
# Source audit: HOYA Price List 2025 pp.9/10/12/16/19-24/26/27;
# pixel_phase4_test.pdf p.16; Maxxee By Hoya 2025 pp.3-8.
# Sensity Original prerequisites are NOT composed automatically.
UNIT_PAIR_PROVEN = "UNIT_PAIR_PROVEN"
UNIT_PER_LENS_PROVEN = "UNIT_PER_LENS_PROVEN"
UNIT_UNRESOLVED = "UNIT_UNRESOLVED"
UNIT_CONFIRMATION_NOTE = (
    "وحدة رسوم الإضافة غير مثبتة (للزوج أم للعدسة) — السعر النهائي يحتاج تأكيد المعمل."
)


class AddonCompletion(NamedTuple):
    price: Decimal
    label: str
    capabilities: FrozenSet[str]
    unit_status: str


class AddonOffer(NamedTuple):
    label: str                                   # catalog-printed add-on name, shown verbatim to the seller
    price: Decimal                                # printed amount; unit requires independent evidence
    capability: str                               # canonical capability this add-on proves
    applicable_indexes: Optional[FrozenSet[float]] = None
    unit_status: str = UNIT_UNRESOLVED
    categories: Optional[FrozenSet[str]] = None
    designs: Optional[FrozenSet[str]] = None
    markets: Optional[FrozenSet[str]] = None

# Route keys never include Stock. HOYA now uses the same exact identity
# validation as PIXEL/Maxxee instead of the misleading Sensity index caption.
# All printed amounts remain informational: no source proves surcharge units.
_ADDON_EVIDENCE: Dict[Tuple[str, str, Optional[str]], Dict[str, AddonOffer]] = {
    ("Maxxee", "rx", None): {
        BLUE_LIGHT: AddonOffer(label="Blue HMC+", price=Decimal("1300"), capability=BLUE_LIGHT),
    },
    ("Pixel", "rx", None): {
        BLUE_LIGHT: AddonOffer(label="Blue Cut Coating", price=Decimal("1000"), capability=BLUE_LIGHT,
                              applicable_indexes=frozenset({1.5, 1.53, 1.56, 1.61, 1.67, 1.74}),
                              categories=frozenset({"single_vision"}),
                              designs=frozenset({"Free Form", "High Definition"}),
                              markets=frozenset({"Out Of Egypt"})),
    },
    ("HOYA", "rx", None): {
        BLUE_LIGHT: AddonOffer(label="BLC", price=Decimal("1500"), capability=BLUE_LIGHT),
    },
}


def missing_capabilities(intent: Optional[str], capabilities: Set[str]) -> FrozenSet[str]:
    """Which capabilities `intent` still requires beyond what `capabilities`
    already proves. Empty when already satisfied or intent is none/unknown."""
    if not intent or intent == "none":
        return frozenset()
    required = _REQUIRED.get(intent)
    if required is None:
        return frozenset()
    return frozenset(required - capabilities)


def addon_completion(company_name: Optional[str], availability_route: str,
                      missing: FrozenSet[str], color_variant: Optional[str] = None,
                      index_value: Optional[float] = None,
                      category: Optional[str] = None,
                      design_variant: Optional[str] = None,
                      market_scope: Optional[str] = None,
                      *, model_name: Optional[str] = None,
                      coating_name: Optional[str] = None,
                      treatment_band: Optional[str] = None,
                      design_type: Optional[str] = None,
                      design_tier: Optional[str] = None,
                      ) -> Optional[AddonCompletion]:
    """If a PROVEN add-on combination can supply EVERY capability in
    `missing` for this company+route(+color_variant/index scope where the
    evidence requires it), return amount, label, capabilities and unit status.
    An unresolved unit is informational only, never a final pair surcharge.
    Otherwise None - fails closed, never partially
    completes a combination (e.g. blue proven via add-on but photo_gray still
    missing must return None, not a half-satisfied result). Tries the row's
    own color_variant scope first, then the company/route-wide (None) scope -
    never the reverse, so a colour-restricted add-on is never accidentally
    reached by an unrelated row."""
    if not missing or not company_name:
        return None
    from app.addon_scope_evidence import proves_addon_scope
    if not proves_addon_scope(
            company_name, model_name=model_name, category=category, index_value=index_value,
            design_type=design_type, design_variant=design_variant, design_tier=design_tier,
            treatment_band=treatment_band, color_variant=color_variant,
            coating_name=coating_name, market_scope=market_scope):
        return None
    scope_keys = [color_variant, None] if color_variant is not None else [None]
    for scope_key in scope_keys:
        scope = _ADDON_EVIDENCE.get((company_name, availability_route, scope_key))
        if not scope:
            continue
        total = Decimal("0")
        units = set()
        labels = []
        supplied: Set[str] = set()
        ok = True
        for cap in missing:
            offer = scope.get(cap)
            if offer is None:
                ok = False
                break
            if (offer.applicable_indexes is not None
                    and (index_value is None or index_value not in offer.applicable_indexes)):
                ok = False
                break
            if any(allowed is not None and value not in allowed for allowed, value in (
                    (offer.categories, category), (offer.designs, design_variant),
                    (offer.markets, market_scope))):
                ok = False
                break
            units.add(offer.unit_status)
            # PER_LENS means the cited charge applies to each of the two lenses.
            total += offer.price * (2 if offer.unit_status == UNIT_PER_LENS_PROVEN else 1)
            labels.append(offer.label)
            supplied.add(cap)
        if ok:
            unit = (next(iter(units)) if len(units) == 1 else UNIT_UNRESOLVED)
            if unit not in (UNIT_PAIR_PROVEN, UNIT_PER_LENS_PROVEN):
                unit = UNIT_UNRESOLVED
            return AddonCompletion(total, " + ".join(sorted(labels)), frozenset(supplied), unit)
    return None


def proven_capabilities(company_name: Optional[str], coating_name: Optional[str],
                         treatment_band: Optional[str], color_variant: Optional[str], *,
                         model_name: Optional[str] = None, index_value: Optional[float] = None,
                         material: Optional[str] = None) -> Set[str]:
    """Union of every EXACT-match evidence rule this row satisfies. Never a
    substring/fuzzy match - only values registered verbatim in _EVIDENCE."""
    if not company_name:
        return set()
    caps: Set[str] = set()
    if ((company_name == "HOYA" and model_name in _HOYA_PNX_MODELS and index_value == 1.53)
            or (company_name == "SCOPE" and treatment_band in _SCOPE_IMPACT_TERMS
                and index_value == 1.56)):
        caps.add(IMPACT_RESISTANT)
    for field, value in (("coating", coating_name), ("treatment_band", treatment_band),
                          ("color_variant", color_variant)):
        if not value:
            continue
        hit = _EVIDENCE.get((company_name, field, value.strip()))
        if hit:
            caps |= hit
    # Bare colours are never evidence of a photochromic treatment.
    photo_treatments = {"VISALL": {"Photochromic", "Photochromic + BlueCut"},
                        "Maxxee": {"Photo"}}
    photo_colours = {
        "VISALL": {"Gray": {PHOTO_GRAY}, "Brown": {PHOTO_BROWN},
                   "Gray / Brown": {PHOTO_GRAY, PHOTO_BROWN}},
        "Maxxee": {"Gray": {PHOTO_GRAY}, "Brown": {PHOTO_BROWN},
                   "Gray/Brown": {PHOTO_GRAY, PHOTO_BROWN},
                   "Gray/Brown/Green": {PHOTO_GRAY, PHOTO_BROWN}},
    }
    if (treatment_band or "").strip() in photo_treatments.get(company_name, set()):
        caps |= photo_colours[company_name].get((color_variant or "").strip(), set())
    return caps


def satisfies(intent: Optional[str], capabilities: Set[str]) -> bool:
    """Hard AND check: every capability the intent requires must be present.
    "none"/None always satisfies (no technology requirement was requested)."""
    if not intent or intent == "none":
        return True
    required = _REQUIRED.get(intent)
    if required is None:
        # unknown intent string - fail closed rather than silently ignore it
        return False
    return required.issubset(capabilities)
