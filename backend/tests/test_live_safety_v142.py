"""Focused V1.4.2 policy, diameter and null-ADD regressions."""
import pytest
from app import models, schemas, product_search as ps, customer_needs
from test_use_mode_technology import _stock_product, _rx_product, _mk_presc, _mk_pricing, _mk_range
from test_prescription_safety_v14 import db, client


def search(db, use='distance', needs=None, add=2):
    p = _mk_presc(db, -2, -2, od_add=add, os_add=add)
    return ps.search(db, p, schemas.ProductSearchRequest(use_mode=use, customer_needs=needs or []))


def rows(r):
    return [x for g in r.groups for x in g.results]


@pytest.mark.parametrize('use', ['distance', 'reading'])
@pytest.mark.parametrize('market', ['Egypt', 'Out Of Egypt', None, 'pending', 'out_of_range'])
def test_sv_fallback_after_actionable_stock(db, use, market):
    *_, stock = _stock_product(db, 'Other', 'Stock', 'single_vision', -6, 6)
    stock.market_scope = market if market not in ('pending', 'out_of_range') else 'Egypt'
    if market == 'pending': stock.price_confirmation_note = 'Confirm'
    if market == 'out_of_range':
        for pr in stock.power_ranges: pr.sph_min, pr.sph_max = 8, 10
    _rx_product(db, 'Other', 'RX', 'single_vision', -6, 6)
    db.commit()
    r = search(db, use)
    assert any(x.pair_fulfillment.status == 'rx' for x in rows(r)) == (market not in ('Egypt', 'Out Of Egypt'))
    assert r.exact_total == len(rows(r))


def test_needs_filter_before_fallback(db):
    _stock_product(db, 'Other', 'Plain', 'single_vision', -6, 6)
    _rx_product(db, 'HOYA', 'Blue', 'single_vision', -6, 6, coating_code='Long Life Blue Control')
    r = search(db, needs=['blue_light'])
    assert [x.model_name for x in rows(r)] == ['Blue']
    assert rows(r)[0].pair_fulfillment.status == 'rx'


@pytest.mark.parametrize('use', ['progressive', 'bifocal'])
def test_multifocal_rx_not_suppressed(db, use):
    _stock_product(db, 'Other', 'Stock', use, -6, 6)
    *_, rx = _rx_product(db, 'Other', 'RX', use, -6, 6)
    for pr in rx.power_ranges: pr.add_min, pr.add_max = 1, 3
    db.commit()
    assert any(x.pair_fulfillment.status == 'rx' for x in rows(search(db, use)))


@pytest.mark.parametrize('price', [850, 1300, 1600, 2150])
@pytest.mark.parametrize('ambiguous', [False, True])
def test_diameter_resolves_bands_per_diameter(db, price, ambiguous):
    _, model, variant, first = _stock_product(db, 'DIVEL ITALIA', 'Lens', 'single_vision', -4, 4, cyl_min=-2, cyl_max=2, price=price)
    first.power_ranges[0].notes = 'Ø65'
    for band, (diameter, cost) in enumerate([(70, price + (50 if ambiguous else 0)), (65, price+150), (70, price+150)]):
        vp = models.VariantPricing(variant_id=variant.id, source_catalog_id=first.source_catalog_id, availability=models.PricingAvailability.STOCK, price_pair=cost, currency='EGP', market_scope='Egypt', power_scope=f'band-{band}')
        db.add(vp); db.commit()
        pr = _mk_range(db, model, variant, vp, -4, 0, -4, 0)
        pr.notes = f'Ø{diameter}'
    db.commit()
    r = rows(search(db))[0]
    assert bool(r.pair_fulfillment.price_confirmation_note) == ambiguous
    assert customer_needs.actionable(r) == (not ambiguous)
    assert r.pair_fulfillment.price_pair == price


@pytest.mark.parametrize('add', ['omitted', None, 0, 2])
def test_add_roundtrip_create_edit_response(client, db, add):
    eye = dict(sph=-2, cyl=-1, axis=90)
    if add != 'omitted': eye['add'] = add
    expected = None if add == 'omitted' else add
    created = client.post('/prescriptions/', json={'od':eye, 'os':eye}).json()
    pid = created['id']
    for method in ('get', 'put'):
        response = getattr(client, method)(f'/prescriptions/{pid}', **({'json':{'od':eye,'os':eye}} if method=='put' else {}))
        assert response.status_code == 200
        assert response.json()['od_add'] == response.json()['os_add'] == expected
    stored = db.get(models.Prescription, pid)
    assert stored.od_add == stored.os_add == expected


@pytest.mark.parametrize('use', ['reading', 'progressive', 'bifocal'])
@pytest.mark.parametrize('add', [None, 0])
def test_missing_usable_add_still_blocks(db, use, add):
    r = search(db, use, add=add)
    assert r.availability_answer.code == 'validation_error'
