"""V1.4.1 seller ranking and multi-need safety, isolated synthetic catalogs."""
from decimal import Decimal
import pytest
from pydantic import ValidationError
from test_use_mode_technology import db, _stock_product, _rx_product, _mk_presc
from app import schemas, product_search as ps, customer_needs, technology_evidence as te


def search(db, needs=None, use='distance', **kwargs):
    return ps.search(db, _mk_presc(db, -2, -2, od_add=2, os_add=2),
                     schemas.ProductSearchRequest(use_mode=use, customer_needs=needs, **kwargs))


def cards(response):
    return [response.best_match, *response.seller_alternatives]


def score_expensive_high(monkeypatch):
    original = ps._per_eye_results
    def scored(*args, **kwargs):
        rows = original(*args, **kwargs)
        for row in rows:
            row.match_score = 99 if row.model_name == 'Expensive' else 1
        return rows
    monkeypatch.setattr(ps, '_per_eye_results', scored)


@pytest.mark.parametrize('tier', ['egypt', 'outside', 'rx'])
def test_same_tier_price_precedes_score_and_next_two_follow_same_rule(db, monkeypatch, tier):
    for name, price in [('Expensive', 3300), ('Cheap', 1250), ('Middle', 2000)]:
        factory = _rx_product if tier == 'rx' else _stock_product
        *_, vp = factory(db, 'Other', name, 'single_vision', -6, 6, price=price)
        if tier == 'outside':
            vp.market_scope = 'Out Of Egypt'
    db.commit()
    score_expensive_high(monkeypatch)
    result = search(db, [])
    assert [r.pair_fulfillment.price_pair for r in cards(result)] == [1250, 2000, 3300]
    assert result.seller_alternatives[-1].match_score == 99


def test_availability_precedes_price_pending_and_unknown_never_recommended(db):
    for name, price, market, note in [('Egypt', 3000, 'Egypt', None),
            ('Outside', 1000, 'Out Of Egypt', None), ('Unknown', 1, None, None),
            ('Pending', 1, 'Egypt', 'Confirm price')]:
        *_, vp = _stock_product(db, 'Other', name, 'single_vision', -6, 6, price=price)
        vp.market_scope = market
        vp.price_confirmation_note = note
    _rx_product(db, 'Other', 'RX', 'single_vision', -6, 6, price=100)
    db.commit()
    result = search(db, [])
    assert [r.model_name for r in cards(result)] == ['Egypt', 'Outside', 'RX']
    assert result.exact_total == 5
    assert any(g.key == 'stock_market_unknown' and g.count == 1 for g in result.groups)


@pytest.mark.parametrize('category', ['progressive', 'bifocal'])
@pytest.mark.parametrize('cheaper_company', ['SCOPE', 'PLATINUM'])
def test_local_manufacturing_tier_has_no_fixed_brand_order(db, monkeypatch, category, cheaper_company):
    for company in ['SCOPE', 'PLATINUM', 'Other']:
        name = 'Cheap' if company == cheaper_company else 'Expensive'
        price = 9450 if company == cheaper_company else 10300
        *_, vp = _rx_product(db, company, name, category, -6, 6, price=100 if company == 'Other' else price)
        for power_range in vp.power_ranges:
            power_range.add_min, power_range.add_max = 1, 3
    db.commit()
    score_expensive_high(monkeypatch)
    result = search(db, [], use=category)
    assert result.best_match.company_name == cheaper_company
    assert [r.pair_fulfillment.price_pair for r in cards(result)] == [9450, 10300, 100]
    assert all(r.manufacturing_location == 'egypt' for r in cards(result)[:2])
    assert result.seller_alternatives[-1].manufacturing_location is None
    assert 'تصنيع داخل مصر' in result.best_match.seller_recommendation_reason


def test_other_progressive_rx_price_order_and_score_tiebreak(db, monkeypatch):
    for name, price in [('Expensive', 10300), ('Cheap', 9450), ('Same', 9450)]:
        *_, vp = _rx_product(db, 'Other', name, 'progressive', -6, 6, price=price)
        for power_range in vp.power_ranges:
            power_range.add_min, power_range.add_max = 1, 3
    db.commit()
    score_expensive_high(monkeypatch)
    result = search(db, [], use='progressive')
    assert [r.pair_fulfillment.price_pair for r in cards(result)] == [9450, 9450, 10300]
    a, b = cards(result)[:2]
    a.match_score, b.match_score = 10, 90
    assert customer_needs.seller_order(b) < customer_needs.seller_order(a)


@pytest.mark.parametrize('needs,expected', [
    (['blue_light'], {'Blue', 'Both'}), (['photo_gray'], {'Photo', 'Both'}),
    (['photo_brown'], {'Photo', 'Both'}), (['blue_light', 'photo_gray'], {'Both'}),
    (['blue_light', 'photo_brown'], {'Both'}),
    (['blue_light', 'photo_gray', 'photo_brown'], {'Both'}),
    ([], {'Plain', 'Blue', 'Photo', 'Both'}),
])
def test_list_needs_require_same_offer_and_keep_scalar_compatibility(db, needs, expected):
    for name, coat, color in [('Plain', None, None), ('Blue', 'Long Life Blue Control', None),
            ('Photo', None, 'Sensity 2'), ('Both', 'Long Life Blue Control', 'Sensity 2')]:
        _rx_product(db, 'HOYA', name, 'single_vision', -6, 6, coating_code=coat, color_variant=color)
    result = search(db, needs)
    assert {r.model_name for g in result.groups for r in g.results} == expected
    assert result.customer_needs == needs
    legacy = search(db, None, customer_need='screens_blue_light')
    assert {r.model_name for g in legacy.groups for r in g.results} == {'Blue', 'Both'}


def test_scalar_and_list_are_conjunctive_and_no_unsafe_fallback(db):
    _rx_product(db, 'HOYA', 'Blue', 'single_vision', -6, 6, coating_code='Long Life Blue Control')
    r = search(db, ['impact_resistant'], customer_need='screens_blue_light',
               mode='targeted', filters=schemas.LensFilters(index_value=1.74))
    assert not r.best_match and not r.alternatives and not r.availability_intelligence
    with pytest.raises(ValidationError):
        schemas.ProductSearchRequest(customer_needs=['unproven'])


@pytest.mark.parametrize('company,model,index,term,expected', [
    ('HOYA', 'Nulux PNX', 1.53, None, True),
    ('HOYA', 'Nulux PNX extra', 1.53, None, False),
    ('HOYA', 'Nulux PNX', 1.59, None, False),
    ('Other', 'Nulux PNX', 1.53, None, False),
    ('Other', 'Trivex', 1.53, None, False),
    ('Other', 'Polycarbonate', 1.59, None, False),
    ('PLATINUM', 'Unknown 1.59', 1.59, None, False),
    ('SCOPE', 'SCOPE SV Standard', 1.56, 'HiFlex Impact-Resistant', True),
])
def test_impact_uses_proven_identity_not_index_material_or_fuzzy_name(company, model, index, term, expected):
    caps = te.proven_capabilities(company, None, term, None, model_name=model,
                                  index_value=index, material='polycarbonate')
    assert ('impact_resistant' in caps) == expected


def test_blue_and_impact_are_strict_and(db):
    for name, term in [('Impact', 'HiFlex Impact-Resistant'),
            ('Both', 'HiFlex Relax Impact-Resistant Blue Light'), ('Blue', 'Relax Blue Light')]:
        _rx_product(db, 'SCOPE', name, 'single_vision', -6, 6, index_value=1.56, treatment_band=term)
    result = search(db, ['blue_light', 'impact_resistant'])
    assert {r.model_name for g in result.groups for r in g.results} == {'Both'}


@pytest.mark.parametrize('coating', ['Astro+', 'Astro+B'])
def test_pixel_explicit_page7_evidence_is_not_residual_color_inference(coating):
    assert 'blue_light' in te.proven_capabilities('Pixel', coating, None, None)
    assert 'blue_light' not in te.proven_capabilities('Other', coating, None, None)
    assert 'blue_light' not in te.proven_capabilities('Pixel', 'Astro', None, 'Blue')


def test_new_list_cannot_unlock_unresolved_hoya_addon(db):
    _rx_product(db, 'HOYA', 'Hilux', 'single_vision', -6, 6, index_value=1.5,
                coating_code='Hi Vision Aqua', market_scope='Out Of Egypt')
    result = search(db, ['blue_light'])
    assert result.exact_total == 1 and result.best_match is None
    row = next(r for g in result.groups for r in g.results)
    assert row.pair_fulfillment.technology_addon.unit_status == 'UNIT_UNRESOLVED'
    assert row.pair_fulfillment.price_pair is None
    assert row.pair_fulfillment.price_confirmation_note


def test_pending_local_manufacturing_retains_location_without_recommendation(db):
    *_, vp = _rx_product(db, 'PLATINUM', 'Pending', 'progressive', -6, 6)
    for power_range in vp.power_ranges:
        power_range.add_min, power_range.add_max = 1, 3
    vp.price_confirmation_note = 'Confirm final price'
    db.commit()
    result = search(db, [], use='progressive')
    assert result.best_match is None and not result.seller_alternatives
    rows = [r for g in result.groups for r in g.results]
    assert len(rows) == 1 and rows[0].manufacturing_location == 'egypt'
    assert not customer_needs.actionable(rows[0])
