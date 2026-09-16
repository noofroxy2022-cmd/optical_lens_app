"""Exact normalized identities from the V1.3.3 original-catalog audit.

These are applicability keys, NOT price-unit evidence. No database reads,
substring matching, inferred colour meanings, or prerequisite composition.
None is an explicitly absent field in a catalog identity, never a wildcard.
HOYA's importer stores occupational/bifocal models as progressive and leaves
several commercial subdesigns unexpanded. Preserve those exact model identities;
do not invent new subdesign aliases or change catalog data here.
"""


def _catalog_identities():
    rows = {"HOYA": set(), "Pixel": set(), "Maxxee": set()}

    def add(company, model, category, index, coating, *, geometry="spherical",
            design=None, tier=None, treatment=None, color=None, market=None):
        rows[company].add((model, category, index, geometry, design, tier,
                           treatment, color, coating, market))

    # Hoya_Price_List_2025[_Updated].pdf, PDF p.9: special-order SV.
    # PNX is part of the normalized model name, not a fuzzy name alias.
    def hoya(model, category, index, coating, color=None, design=None):
        add("HOYA", model, category, index, coating, color=color,
            design=design, market="Out Of Egypt")

    aqua, super_hv, uv = "Hi Vision Aqua", "Super Hi Vision", "Long Life UV Control"
    for model in ("Hilux", "Nulux"):
        for index in (1.5, 1.53, 1.6, 1.67):
            hoya(model + (" PNX" if index == 1.53 else ""), "single_vision",
                 index, aqua if index == 1.5 else super_hv)
    for model in ("Nulux", "Nulux TF"):
        hoya(model, "single_vision", 1.74, uv)
    # p.10 Nulux iDENTITY V+. Clear and Sensity 2 have different index sets.
    for index in (1.5, 1.6, 1.67, 1.74):
        hoya("Nulux iDENTITY", "single_vision", index, uv)
        if index != 1.74:
            hoya("Nulux iDENTITY", "single_vision", index, uv, "Sensity 2")
    # p.16 Sync III; pp.19-24 progressive. Sensity Original is deliberately
    # absent: pp.12/16/19/20 require a separately priced Sensity 2 upgrade.
    for model, category, indexes, coating in (
        ("Sync III", "single_vision", (1.5, 1.53, 1.6, 1.67, 1.74), super_hv),
        ("Amplitude Plus", "progressive", (1.5, 1.53, 1.6, 1.67), aqua),
        ("Daynamic", "progressive", (1.5, 1.53, 1.6, 1.67), super_hv),
        ("Balansis", "progressive", (1.5, 1.53, 1.6, 1.67, 1.74), super_hv),
        ("iD LifeStyle", "progressive", (1.5, 1.53, 1.6, 1.67, 1.74), uv),
        ("iD MyStyle", "progressive", (1.5, 1.53, 1.6, 1.67, 1.74), uv),
        ("iD MySelf", "progressive", (1.5, 1.53, 1.6, 1.67, 1.74), uv),
    ):
        for index in indexes:
            name = model + (" PNX" if index == 1.53 else "")
            base = super_hv if model == "Amplitude Plus" and index == 1.67 else coating
            hoya(name, category, index, base)
            if model in ("Balansis", "iD LifeStyle", "iD MyStyle", "iD MySelf") and index != 1.74:
                hoya(name, category, index, base, "Sensity 2")
    # p.26 occupational; p.27 bifocal. Category below is the current importer
    # representation, not a claim that bifocals are optically progressive.
    for model, indexes, coating in (
        ("Supereader B", (1.5, 1.6), aqua),
        ("WorkSmart", (1.5, 1.53, 1.6), super_hv),
        ("iD WorkStyle", (1.5, 1.53, 1.6), uv),
    ):
        for index in indexes:
            hoya(model + (" PNX" if index == 1.53 else ""), "progressive", index, coating)
    for design, index, color in (("Flat Top S28", 1.5, None),
                                 ("Curve Top C28", 1.5, None),
                                 ("Curve Top C28", 1.6, None),
                                 ("Flat Top", 1.5, "Sensity 2"),
                                 ("Curve Top", 1.5, "Sensity 2")):
        hoya("Bi-Focal", "progressive", index, aqua, color, design)

    # pixel_phase4_test.pdf p.16 only. G/B strings are identity keys ONLY.
    pixel_bases = {
        1.5: (("Astro", "Clear"), ("Astro", "Transmatic/G/B"),
              ("Astro", "Polz/G/B/G15"), ("Astro", "DWEAR/B")),
        1.53: (("Astro", "Clear"), ("Astro", "Transition/G/B")),
        1.56: (("Astro", "Clear"), ("Astro+", "Clear")),
        1.61: (("Astro", "Clear"), ("Astro", "Transmatic/G/B"),
               ("Astro", "Polz/G/B"), ("Astro+", "Clear")),
        1.67: (("Astro", "Clear"), ("Astro", "Transmatic/G/B"),
               ("Astro", "Polz/G/B"), ("Astro+", "Clear")),
        1.74: (("Astro", "Clear"), ("Astro", "Transition/G/B")),
    }
    for index, bases in pixel_bases.items():
        for coating, color in bases:
            for design in ("Free Form", "High Definition"):
                add("Pixel", "Pixel", "single_vision", index, coating,
                    color=color, design=design, market="Out Of Egypt")

    # Maxxee By Hoya P.L 2025 - R-1-1.pdf pp.3-4, SPH/ASPH SV.
    for index in (1.5, 1.53, 1.6, 1.67, 1.74):
        coating = "H.M.C" if index < 1.67 else "H.M.C+"
        color = "Gray/Brown" if index == 1.53 else "Gray/Brown/Green"
        for geometry in ("spherical", "aspherical"):
            if index == 1.74 and geometry == "spherical":
                continue
            add("Maxxee", "Maxxee", "single_vision", index, coating,
                geometry=geometry, market="Out Of Egypt")
            if index != 1.74:
                add("Maxxee", "Maxxee", "single_vision", index, coating,
                    geometry=geometry, treatment="Photo", color=color)
    # pp.5-8. Geometry is the exact current normalized representation;
    # commercial design and tier are independently required.
    for design in ("Basic", "Plus", "Premium", "Individual Premium"):
        tier = "Active - Experience" if design in ("Premium", "Individual Premium") else None
        indexes = (1.5, 1.53, 1.6, 1.67, 1.74) if tier else (1.5, 1.53, 1.6, 1.67)
        for index in indexes:
            geometry = "spherical" if index < 1.67 else "aspherical"
            coating = "H.M.C+" if design == "Individual Premium" or index >= 1.67 else "H.M.C"
            add("Maxxee", "Maxxee", "progressive", index, coating,
                geometry=geometry, design=design, tier=tier)
            if index != 1.74:
                add("Maxxee", "Maxxee", "progressive", index, coating,
                    geometry=geometry, design=design, tier=tier, treatment="Photo",
                    color="Gray/Brown" if index == 1.53 else "Gray/Brown/Green")
    return {company: frozenset(identities) for company, identities in rows.items()}


CATALOG_IDENTITIES = _catalog_identities()


def proves_addon_scope(company, *, model_name, category, index_value, design_type,
                       design_variant, design_tier, treatment_band, color_variant,
                       coating_name, market_scope):
    """Require every identifying field; absent optional fields match only None."""
    identity = (model_name, category, index_value, design_type, design_variant,
                design_tier, treatment_band, color_variant, coating_name, market_scope)
    return identity in CATALOG_IDENTITIES.get(company, ())
