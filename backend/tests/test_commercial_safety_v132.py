"""Strict catalog limits and fail-closed seller quotations; synthetic DB only."""
from decimal import Decimal

import pytest
from test_use_mode_technology import db, _mk_presc, _stock_product, _rx_product
from app import models, schemas, product_search, customer_needs, technology_evidence as te
from app.lens_matcher import LensMatcherFinal
from app.pixel_addons_evidence import HI_POWER_CONFIRMATION_NOTE


def seller(db, p, need="screens_blue_light", mode="distance", **kwargs):
    return product_search.search(db, p, schemas.ProductSearchRequest(
        customer_need=need, use_mode=mode, **kwargs))


def results(response):
    return [r for group in response.groups for r in group.results]


@pytest.mark.parametrize("route", ["stock", "rx"])
@pytest.mark.parametrize("field,lo,hi", [("sph", -6, 6), ("cyl", -4, -1), ("add", 1, 3)])
@pytest.mark.parametrize("edge,offset,passes", [("lo", 0, True), ("hi", 0, True),
                                               ("lo", -.25, False), ("hi", .25, False)])
def test_strict_explicit_boundaries(db, route, field, lo, hi, edge, offset, passes):
    factory = _stock_product if route == "stock" else _rx_product
    _, _, _, vp = factory(db, "Test", "Explicit", "progressive", -6, 6, -4, -1)
    pr = vp.power_ranges[0]
    pr.add_min, pr.add_max = 1, 3
    db.commit()
    values = dict(sph=0, cyl=-2, add=2)
    values[field] = (lo if edge == "lo" else hi) + offset
    p = _mk_presc(db, values["sph"], values["sph"],
                 od_cyl=values["cyl"], os_cyl=values["cyl"],
                 od_add=values["add"], os_add=values["add"])
    assert LensMatcherFinal().check_power_range(pr, p)[0] is passes
    response = seller(db, p, "none", "progressive")
    assert bool(response.best_match) is passes


@pytest.mark.parametrize("design", ["Free Form", "High Definition"])
def test_pixel_proven_scope(design):
    offer = te.addon_completion("Pixel", "rx", frozenset({te.BLUE_LIGHT}),
                               category="single_vision", design_variant=design, index_value=1.5,
                               market_scope="Out Of Egypt", model_name="Pixel", coating_name="Astro",
                               color_variant="Clear", design_type="spherical")
    assert offer.label == "Blue Cut Coating"
    assert offer.unit_status == te.UNIT_UNRESOLVED


@pytest.mark.parametrize("patch", [dict(category="progressive"), dict(category="bifocal"),
    dict(category=None), dict(design_variant="Premium"), dict(design_variant=None),
    dict(market_scope="Egypt"), dict(market_scope=None), dict(availability_route="stock_outside"),
    dict(index_value=None), dict(index_value=1.6)])
def test_pixel_scope_rejects_unproven_dimensions(patch):
    args = dict(company_name="Pixel", availability_route="rx", missing=frozenset({te.BLUE_LIGHT}),
                category="single_vision", design_variant="Free Form", market_scope="Out Of Egypt",
                index_value=1.5, model_name="Pixel", coating_name="Astro",
                color_variant="Clear", design_type="spherical")
    args.update(patch)
    assert te.addon_completion(**args) is None


@pytest.mark.parametrize("category", ["progressive", "bifocal", "single_vision"])
def test_pixel_scope_seller_end_to_end(db, category):
    _, _, v, vp = _rx_product(db, "Pixel", "Pixel", category, -6, 6, coating_code="Astro", color_variant="Clear")
    v.design_variant, vp.market_scope = "Free Form", "Out Of Egypt"
    vp.power_ranges[0].add_min, vp.power_ranges[0].add_max = 1, 3
    db.commit()
    p = _mk_presc(db, -2, -2, od_add=2, os_add=2)
    response = seller(db, p, mode="distance" if category == "single_vision" else category)
    assert response.exact_total == (1 if category == "single_vision" else 0)
    assert response.best_match is None
    for r in results(response):
        assert r.pair_fulfillment.price_pair is None
        assert HI_POWER_CONFIRMATION_NOTE in r.pair_fulfillment.price_confirmation_note


@pytest.mark.parametrize("pricing_id,design,index,price", [
    (553, "Premium", 1.56, 10500), (561, "Core", 1.61, 8500),
    (562, "Advance", 1.61, 10500), (563, "Premium", 1.61, 12500)])
@pytest.mark.parametrize("note", [None, "", "   "])
def test_pixel_missing_confirmation_patterns(db, pricing_id, design, index, price, note):
    _, _, v, vp = _rx_product(db, "Pixel", "Pixel", "progressive", -6, 6,
                              index_value=index, price=price)
    # Mirror the four audited rows: RX without explicit ranges, no lab state.
    for pr in list(vp.power_ranges):
        db.delete(pr)
    db.flush()
    v.design_variant = design
    vp.id, vp.market_scope, vp.price_confirmation_note = pricing_id, "Out Of Egypt", note
    db.commit()
    db.expire_all()
    response = seller(db, _mk_presc(db, -2, -2, od_add=2, os_add=2), "none", "progressive")
    assert response.best_match is None and not response.seller_alternatives
    r = results(response)[0]
    assert r.pair_fulfillment.price_pair == Decimal(price)  # never adds Hi Power
    assert r.pair_fulfillment.price_confirmation_note == HI_POWER_CONFIRMATION_NOTE
    assert not r.seller_recommendation_reason
    assert not customer_needs.actionable(r)
    assert db.get(models.VariantPricing, pricing_id).price_confirmation_note == note


@pytest.mark.parametrize("company,treatment", [("VISALL", "Photochromic"), ("Maxxee", "Photo")])
@pytest.mark.parametrize("color,cap", [("Gray", te.PHOTO_GRAY), ("Brown", te.PHOTO_BROWN)])
def test_photo_requires_treatment_and_colour(company, treatment, color, cap):
    assert cap in te.proven_capabilities(company, None, treatment, color)
    for ordinary in [None, "Tint", "Sun", "Mirror", "Polarized", "BlueCut"]:
        assert cap not in te.proven_capabilities(company, None, ordinary, color)
    for ordinary_color in [None, "Sun Gray", "Sun Brown", "Mirror", "Polarized"]:
        assert cap not in te.proven_capabilities(company, None, treatment, ordinary_color)


@pytest.mark.parametrize("company", ["VISALL", "Maxxee"])
@pytest.mark.parametrize("color,need", [("Gray", "photochromic_gray"), ("Brown", "photochromic_brown")])
def test_ordinary_colour_never_becomes_seller_photo_result(db, company, color, need):
    _stock_product(db, company, "Tint", "single_vision", -6, 6, color_variant=color)
    response = seller(db, _mk_presc(db, -2, -2), need)
    assert not results(response) and response.best_match is None


@pytest.mark.parametrize("index,allowed", [(1.5, True), (1.6, True), (1.67, True),
                                           (1.53, False), (1.74, False), (None, False), (1.671, False)])
def test_hoya_restricted_index(index, allowed):
    offer = te.addon_completion("HOYA", "rx", frozenset({te.BLUE_LIGHT}), "Sensity 2", index,
                                model_name="Nulux iDENTITY", coating_name="Long Life UV Control",
                                category="single_vision", design_type="spherical", market_scope="Out Of Egypt")
    assert (offer is not None) is allowed


@pytest.mark.parametrize("company,color,label,amount", [
    ("Maxxee", None, "Blue HMC+", 1300), ("HOYA", "Sensity 2", "BLC", 1500),
    ("Pixel", None, "Blue Cut Coating", 1000)])
def test_seller_addon_unit_unresolved_contract(db, company, color, label, amount):
    model, coating = {"HOYA": ("Nulux iDENTITY", "Long Life UV Control"),
                      "Pixel": ("Pixel", "Astro"), "Maxxee": ("Maxxee", "H.M.C")}[company]
    _, _, v, vp = _rx_product(db, company, model, "single_vision", -6, 6,
                              color_variant="Clear" if company == "Pixel" else color,
                              coating_code=coating, market_scope="Out Of Egypt", price=5000)
    if company == "Pixel":
        v.design_variant, vp.market_scope = "High Definition", "Out Of Egypt"
        db.commit()
    response = seller(db, _mk_presc(db, -2, -2))
    assert response.exact_total == 1
    assert response.best_match is None and not response.seller_alternatives
    r = results(response)[0]
    pf = r.pair_fulfillment
    assert pf.status == "rx"
    assert pf.technology_addon.base_price == Decimal(5000)
    assert pf.technology_addon.label == label
    assert pf.technology_addon.addon_price == Decimal(amount)
    assert pf.technology_addon.unit_status == te.UNIT_UNRESOLVED
    assert pf.price_pair is None
    assert te.UNIT_CONFIRMATION_NOTE in pf.price_confirmation_note
    assert not r.seller_recommendation_reason and not customer_needs.actionable(r)
    payload = response.model_dump(mode="json")
    assert payload["best_match"] is None
    assert all(row["pair_fulfillment"]["price_pair"] is None
               for group in payload["groups"] for row in group["results"])


@pytest.mark.parametrize("unit,multiplier", [(te.UNIT_PAIR_PROVEN, 1), (te.UNIT_PER_LENS_PROVEN, 2)])
def test_seller_proven_unit_arithmetic_isolated_fixture(db, monkeypatch, unit, multiplier):
    # Test-only evidence, never a claim about the real Maxxee catalog.
    key = ("Maxxee", "rx", None)
    offer = te._ADDON_EVIDENCE[key][te.BLUE_LIGHT]._replace(unit_status=unit)
    monkeypatch.setitem(te._ADDON_EVIDENCE, key, {te.BLUE_LIGHT: offer})
    _rx_product(db, "Maxxee", "Maxxee", "single_vision", -6, 6, price=5000,
                coating_code="H.M.C", market_scope="Out Of Egypt")
    response = seller(db, _mk_presc(db, -2, -2))
    r = response.best_match
    assert customer_needs.actionable(r)
    assert r.pair_fulfillment.price_pair == Decimal(5000 + multiplier * 1300)
    assert not r.pair_fulfillment.price_confirmation_note
    assert "سعر الزوج النهائي" in r.seller_recommendation_reason


def test_included_preferred_and_strict_blue_photo_and(db):
    _rx_product(db, "Maxxee", "Maxxee", "single_vision", -6, 6, price=100,
                coating_code="H.M.C", market_scope="Out Of Egypt")
    _stock_product(db, "VISALL", "Included", "single_vision", -6, 6, price=1000,
                   treatment_band="Photochromic + BlueCut", color_variant="Gray")
    p = _mk_presc(db, -2, -2)
    response = seller(db, p)
    assert response.best_match.model_name == "Included"
    assert response.best_match.pair_fulfillment.technology_addon is None
    response = seller(db, p, "none", technology_intent="blue_photo_gray")
    assert response.exact_total == 1 and response.best_match.model_name == "Included"
    response = seller(db, p, "none", technology_intent="blue_photo_brown")
    assert response.exact_total == 0 and response.best_match is None
