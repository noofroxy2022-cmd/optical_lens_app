"""Catalog scope regressions, independent examples and seller-level contracts."""
import pytest

from test_use_mode_technology import db, _rx_product, _mk_presc
from test_commercial_safety_v132 import seller, results
from app import models, customer_needs, technology_evidence as te


def identity(company, **changes):
    args = dict(company_name=company, availability_route="rx", missing=frozenset({te.BLUE_LIGHT}),
                category="single_vision", index_value=1.5, design_type="spherical",
                design_variant=None, design_tier=None, treatment_band=None, color_variant=None,
                market_scope="Out Of Egypt")
    args.update({
        "HOYA": dict(model_name="Hilux", coating_name="Hi Vision Aqua"),
        "Pixel": dict(model_name="Pixel", coating_name="Astro", color_variant="Clear", design_variant="Free Form"),
        "Maxxee": dict(model_name="Maxxee", coating_name="H.M.C"),
    }[company])
    args.update(changes)
    return args


def make_product(db, args):
    _, _, v, vp = _rx_product(
        db, args["company_name"], args["model_name"], args["category"], -6, 6,
        coating_code=args["coating_name"], color_variant=args["color_variant"],
        treatment_band=args["treatment_band"], index_value=args["index_value"],
        market_scope=args["market_scope"], price=5000)
    v.design_type = models.DesignType(args["design_type"])
    v.design_variant, v.design_tier = args["design_variant"], args["design_tier"]
    vp.power_ranges[0].add_min, vp.power_ranges[0].add_max = 1, 3
    db.commit()
    return v, vp


# Independent catalog examples, covering each HOYA family and Maxxee page.
POSITIVE = [
    identity("HOYA"),
    identity("HOYA", model_name="Nulux PNX", index_value=1.53, coating_name="Super Hi Vision"),
    identity("HOYA", model_name="Nulux TF", index_value=1.74, coating_name="Long Life UV Control"),
    identity("HOYA", model_name="Nulux iDENTITY", index_value=1.67,
             coating_name="Long Life UV Control", color_variant="Sensity 2"),
    identity("HOYA", model_name="Sync III", index_value=1.74, coating_name="Super Hi Vision"),
    identity("HOYA", model_name="Amplitude Plus", category="progressive", index_value=1.67,
             coating_name="Super Hi Vision"),
    identity("HOYA", model_name="Daynamic PNX", category="progressive", index_value=1.53,
             coating_name="Super Hi Vision"),
    identity("HOYA", model_name="Balansis PNX", category="progressive", index_value=1.53,
             coating_name="Super Hi Vision", color_variant="Sensity 2"),
    *[identity("HOYA", model_name=model, category="progressive", coating_name="Long Life UV Control")
      for model in ("iD LifeStyle", "iD MyStyle", "iD MySelf")],
    # Occupational/Office (Special Lenses architecture, 2026-09-19): these
    # three were reclassified progressive -> office; see
    # app/catalog_corrections.py OCCUPATIONAL_OFFICE_MODELS.
    identity("HOYA", model_name="iD WorkStyle", category="office", coating_name="Long Life UV Control"),
    identity("HOYA", model_name="WorkSmart", category="office", coating_name="Super Hi Vision"),
    identity("HOYA", model_name="Supereader B", category="office"),
    identity("HOYA", model_name="Bi-Focal", category="bifocal", design_variant="Curve Top C28"),
    identity("Pixel"),
    identity("Pixel", index_value=1.74, color_variant="Transition/G/B", design_variant="High Definition"),
    identity("Maxxee"),
    identity("Maxxee", index_value=1.74, design_type="aspherical", coating_name="H.M.C+"),
    identity("Maxxee", index_value=1.53, treatment_band="Photo", color_variant="Gray/Brown", market_scope=None),
    *[identity("Maxxee", category="progressive", design_variant=design, market_scope=None)
      for design in ("Basic", "Plus")],
    identity("Maxxee", category="progressive", design_variant="Premium", design_tier="Active - Experience",
             market_scope=None, treatment_band="Photo", color_variant="Gray/Brown/Green"),
    identity("Maxxee", category="progressive", design_variant="Individual Premium", design_tier="Active - Experience",
             coating_name="H.M.C+", market_scope=None),
]


@pytest.mark.parametrize("args", POSITIVE)
def test_proven_identity_reaches_only_pending_seller_completion(db, args):
    offer = te.addon_completion(**args)
    assert offer is not None and offer.unit_status == te.UNIT_UNRESOLVED
    make_product(db, args)
    p = _mk_presc(db, -2, -2, od_add=2, os_add=2)
    # Category-classification review (2026-09-19): this used to assume only
    # "progressive" or "distance" ever appeared here - true before HOYA
    # Bi-Focal's category correction (progressive -> bifocal) and the
    # Occupational/Office correction (progressive -> office) added the
    # "bifocal" and "office" entries to POSITIVE above.
    _mode = {"progressive": "progressive", "bifocal": "bifocal",
             "office": "office"}.get(args["category"], "distance")
    response = seller(db, p, mode=_mode)
    assert response.exact_total == 1
    assert response.best_match is None and not response.seller_alternatives
    r = results(response)[0]
    assert r.pair_fulfillment.price_pair is None
    assert r.pair_fulfillment.technology_addon.unit_status == te.UNIT_UNRESOLVED
    assert te.UNIT_CONFIRMATION_NOTE in r.pair_fulfillment.price_confirmation_note
    assert not customer_needs.actionable(r)


@pytest.mark.parametrize("company", ["HOYA", "Pixel", "Maxxee"])
@pytest.mark.parametrize("patch", [
    {"model_name": None}, {"model_name": "Unrelated"}, {"model_name": "Hilux extra"},
    {"index_value": None}, {"index_value": 1.8}, {"index_value": 1.501},
    {"coating_name": None}, {"coating_name": "Unproven"},
    {"design_type": None}, {"design_type": "double_aspherical"},
    {"design_variant": "Unproven"}, {"design_tier": "Unproven"},
    {"treatment_band": "Unproven"}, {"color_variant": "Unproven"},
    {"category": None}, {"category": "bifocal"}, {"category": "office"},
    {"market_scope": "Egypt"}, {"availability_route": "stock_outside"},
])
def test_missing_or_wrong_identity_fails_closed(company, patch):
    assert te.addon_completion(**identity(company, **patch)) is None


@pytest.mark.parametrize("args", [
    identity("HOYA", model_name="Hilux", color_variant="Sensity Original", coating_name="Super Hi Vision"),
    identity("HOYA", model_name="Sync III", color_variant="Sensity Original", coating_name="Super Hi Vision"),
    identity("HOYA", model_name="Amplitude Plus", category="progressive", color_variant="Sensity Original"),
    identity("HOYA", model_name="Daynamic", category="progressive", color_variant="Sensity Original", coating_name="Super Hi Vision"),
    identity("HOYA", model_name="Nulux iDENTITY", index_value=1.74, color_variant="Sensity 2", coating_name="Long Life UV Control"),
    identity("HOYA", model_name="Hilux", coating_name="Sun Pro ( Up To Base 8 )"),
    identity("Pixel", category="progressive"), identity("Pixel", category="bifocal"),
    identity("Pixel", design_variant="Premium"), identity("Pixel", market_scope=None),
    identity("Pixel", color_variant=None), identity("Pixel", color_variant="Transition/G/B"),
    identity("Pixel", index_value=1.56, color_variant="Transmatic/G/B"),
    identity("Pixel", index_value=1.67, coating_name="Astro+", color_variant="Transmatic/G/B"),
    identity("Maxxee", index_value=1.74, coating_name="H.M.C+"),
    identity("Maxxee", index_value=1.67),
    identity("Maxxee", index_value=1.53, treatment_band="Photo", color_variant="Gray/Brown/Green", market_scope=None),
    identity("Maxxee", category="progressive", design_variant="Basic", index_value=1.74,
             design_type="aspherical", coating_name="H.M.C+", market_scope=None),
    identity("Maxxee", category="progressive", design_variant="Premium", market_scope=None),
])
def test_cross_table_combinations_and_prerequisites_rejected(args):
    assert te.addon_completion(**args) is None


@pytest.mark.parametrize("intent", ["blue_light", "blue_photo_gray", "blue_photo_brown"])
def test_sensity_original_prerequisite_rejected_by_seller(db, intent):
    args = identity("HOYA", color_variant="Sensity Original", coating_name="Super Hi Vision")
    make_product(db, args)
    response = seller(db, _mk_presc(db, -2, -2), need="none", technology_intent=intent)
    assert response.exact_total == 0 and response.best_match is None


@pytest.mark.parametrize("company,coating,index", [("HOYA", "Long Life Blue Control", 1.5),
                                                    ("Pixel", "Astro+", 1.56), ("Maxxee", "Blue U.V", 1.5)])
def test_included_blue_never_duplicates_addon(db, company, coating, index):
    args = identity(company, coating_name=coating, index_value=index)
    make_product(db, args)
    response = seller(db, _mk_presc(db, -2, -2))
    assert response.exact_total == 1
    assert results(response)[0].pair_fulfillment.technology_addon is None
    assert results(response)[0].pair_fulfillment.price_pair == 5000


def test_pixel_abbreviations_do_not_gain_photo_capabilities():
    # RECONCILED (owner-confirmed HAT fix, 2026-09-21): "Transmatic/G/B" and
    # "Transition/G/B" are proven TR/Transition products and now correctly
    # DO gain photo_gray+photo_brown - see
    # test_pixel_transmatic_proves_photo_gray_and_photo_brown in
    # test_use_mode_technology.py. "Polz/G/B" (Polarized, not photochromic)
    # and "DWEAR/B" (never described in the catalog) remain unproven and stay
    # in this negative-safety check.
    for color in ("Polz/G/B", "DWEAR/B"):
        caps = te.proven_capabilities("Pixel", "Astro", None, color)
        assert te.PHOTO_GRAY not in caps and te.PHOTO_BROWN not in caps
