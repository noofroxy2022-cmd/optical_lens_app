"""Permanent seller safety tests: synthetic catalogs, never production DB."""
from decimal import Decimal
import pytest
from test_use_mode_technology import (db, _mk_presc, _stock_product, _rx_product)
from app import schemas, product_search, customer_needs, models


def search(db, p, need="none", **kwargs):
    return product_search.search(db, p, schemas.ProductSearchRequest(
        customer_need=need, use_mode="distance", **kwargs))


@pytest.mark.parametrize("need,term", [
    (need, term) for need, terms in customer_needs.SCOPE_ROWS.items() for term in terms])
def test_exact_catalog_evidence(need, term):
    assert customer_needs.proves(need, "SCOPE", term)
    assert not customer_needs.proves(need, "Other", term)
    assert not customer_needs.proves(need, "SCOPE", term + " unknown")


@pytest.mark.parametrize("need", ["best_optical_clarity", "unknown", "frame_rimless"])
def test_unproven_needs_fail_closed(db, need):
    r = search(db, _mk_presc(db, -2, -2), need)
    assert r.availability_answer.code == "validation_error"
    assert r.best_match is None and not r.seller_alternatives and not r.alternatives


@pytest.mark.parametrize("field,value", [("od_axis", 181), ("os_add", -1), ("os_axis", -1)])
def test_invalid_rx_blocks_search(db, field, value):
    p = _mk_presc(db, -2, -2)
    setattr(p, field, value)
    r = search(db, p)
    assert r.availability_answer.code == "validation_error"
    assert r.best_match is None


def test_unknown_technology_and_conflict(db):
    p = _mk_presc(db, -2, -2)
    for tech in ("unknown", "photo_brown"):
        r = search(db, p, "screens_blue_light", technology_intent=tech)
        assert r.availability_answer.code == "validation_error"


def test_top_three_are_need_safe_and_fully_priced(db):
    for n in range(4):
        _stock_product(db, "HOYA", f"Blue {n}", schemas.LensCategory.SINGLE_VISION,
                       -6, 6, coating_code="Long Life Blue Control", price=1000 + n * 100)
    _stock_product(db, "Other", "Cheap ordinary", schemas.LensCategory.SINGLE_VISION,
                   -6, 6, price=10)
    r = search(db, _mk_presc(db, -2, -2), "screens_blue_light")
    assert r.exact_total == 4
    assert len(r.seller_alternatives) == 2
    cards = [r.best_match, *r.seller_alternatives]
    assert len({x.variant_id for x in cards}) == 3
    assert [x.pair_fulfillment.price_pair for x in cards] == [Decimal(1000), Decimal(1100), Decimal(1200)]
    for x in cards:
        assert customer_needs.actionable(x)
        assert "سعر الزوج النهائي" in x.seller_recommendation_reason
        assert "Long Life Blue Control" in x.seller_recommendation_reason


def test_pending_price_never_recommended(db):
    _stock_product(db, "HOYA", "Pending", schemas.LensCategory.SINGLE_VISION, -6, 6)
    vp = db.query(models.VariantPricing).one()
    vp.price_confirmation_note = "Confirm surcharge"
    db.commit()
    r = search(db, _mk_presc(db, -2, -2))
    assert r.exact_total == 1  # informational catalog semantics retained
    assert r.best_match is None and not r.seller_alternatives


@pytest.mark.parametrize("patch", [
    {"status": "split"}, {"status": "eligibility_unknown"},
    {"status": "stock_market_unknown"}, {"status": "unavailable"},
    {"needs_review": True}, {"provenance": "unproven_mixed"},
    {"price_pair": None}, {"price_pair": Decimal(0)},
    {"price_pair": Decimal(-1)}, {"source_pricing_ids": []},
    {"currency": None}, {"price_confirmation_note": "Pending"},
])
def test_every_recommendation_gate(db, patch):
    _stock_product(db, "HOYA", "Plain", schemas.LensCategory.SINGLE_VISION, -6, 6)
    r = search(db, _mk_presc(db, -2, -2)).best_match
    assert customer_needs.actionable(r)
    r.pair_fulfillment = r.pair_fulfillment.model_copy(update=patch)
    assert not customer_needs.actionable(r)


def test_seller_requires_explicit_use_mode(db):
    r = product_search.search(db, _mk_presc(db, -2, -2),
                             schemas.ProductSearchRequest(customer_need="none"))
    assert r.availability_answer.code == "validation_error"


@pytest.mark.parametrize("mode,category", [("reading", "single_vision"),
    ("bifocal", "bifocal"), ("progressive", "progressive")])
def test_seller_category_boundary(db, mode, category):
    for cat in ("single_vision", "bifocal", "progressive"):
        _stock_product(db, "HOYA", cat, cat, -6, 6, add_min=0, add_max=3)
    p = _mk_presc(db, -2, -2, od_add=2, os_add=2)
    r = product_search.search(db, p, schemas.ProductSearchRequest(customer_need="none", use_mode=mode))
    assert r.best_match.category == category
    assert all(x.category == category for g in r.groups for x in g.results)


def test_category_conflict_is_not_silently_overwritten(db):
    filters = schemas.LensFilters(category="progressive")
    r = search(db, _mk_presc(db, -2, -2), mode="targeted", filters=filters)
    assert r.availability_answer.code == "validation_error"
    assert filters.category == "progressive"


def test_targeted_fallback_cannot_drop_need(db):
    _stock_product(db, "Other", "Plain", schemas.LensCategory.SINGLE_VISION, -6, 6)
    r = search(db, _mk_presc(db, -2, -2), "driving", mode="targeted",
               filters=schemas.LensFilters(index_value=1.74))
    assert r.best_match is None and not r.seller_alternatives and not r.alternatives


@pytest.mark.parametrize("need", list(customer_needs.SCOPE_ROWS))
def test_scope_need_end_to_end(db, need):
    term = sorted(customer_needs.SCOPE_ROWS[need])[0]
    _rx_product(db, "SCOPE", "Proven", schemas.LensCategory.SINGLE_VISION, -6, 6,
                treatment_band=term)
    _rx_product(db, "Other", "Unproven", schemas.LensCategory.SINGLE_VISION, -6, 6,
                treatment_band=term)
    r = search(db, _mk_presc(db, -2, -2), need)
    assert r.exact_total == 1
    assert r.best_match.company_name == "SCOPE"
    assert term in r.best_match.seller_recommendation_reason


def test_high_impact_resistance_need_routes_through_central_capability_rule(db):
    """audit.md Section G item 3: the "high_impact_resistance" seller need
    must no longer be gated by a hardcoded SCOPE-only check
    (customer_needs.proves); it must defer entirely to
    technology_evidence.proven_capabilities' single central impact-resistance
    rule, exactly like screens_blue_light/photochromic_* already do."""
    _rx_product(db, "SCOPE", "HiFlexProven", schemas.LensCategory.SINGLE_VISION, -6, 6,
                index_value=1.56, treatment_band="HiFlex Impact-Resistant")
    _rx_product(db, "PLATINUM", "IndexProven", schemas.LensCategory.SINGLE_VISION, -6, 6,
                index_value=1.59)
    _rx_product(db, "Other", "Unproven", schemas.LensCategory.SINGLE_VISION, -6, 6,
                index_value=1.5)
    r = search(db, _mk_presc(db, -2, -2), "high_impact_resistance")
    assert r.exact_total == 2
    assert {x.model_name for g in r.groups for x in g.results} == {"HiFlexProven", "IndexProven"}
    assert "high_impact_resistance" not in customer_needs.SCOPE_ROWS
