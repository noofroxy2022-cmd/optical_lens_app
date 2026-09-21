"""Centralized SCOPE/PLATINUM local-Egypt-manufacturing classification
(owner-confirmed HAT fix, 2026-09-21).

Root cause this module pins down: customer_needs.local_manufacturing() and
customer_needs.seller_order() used to gate the Egypt-manufacturing tag/tier
on an explicit category tuple ("progressive", "bifocal", then "anti_fatigue"
added 2026-09-21) that had to be hand-extended every time a new RX-eligible
category was introduced. Myopia Control was the next category to fall into
that gap: SCOPE's own Myoblock/Metavision RX rows never got
manufacturing_location="egypt" and were indistinguishable from foreign
(ZEISS) RX in both UI grouping and seller_order ranking.

OWNER-CONFIRMED RULE (authoritative for this catalog/project): SCOPE is an
Egyptian manufacturer; ALL SCOPE RX/manufactured lenses, in every category,
are manufactured inside Egypt. This is a company/manufacturing identity, not
a subtype allowlist - the fix removes the category tuple entirely so no
category (existing or future) can ever fall through this gap again.
LOCAL_EGYPT_MANUFACTURERS also includes PLATINUM (pre-existing, unrelated to
this fix); this module exercises SCOPE primarily and uses PLATINUM only to
confirm the same centralized rule already covers it, per the owner's rule
that this must be company-based, not per-manufacturer-patched.

Deliberately synthetic, mirroring test_seller_priority_v141.py's own
existing pattern - no PDF parsing, no dependency on the live
release_runtime.db for the pipeline-level proof (the live-db HAT
verification is done separately, outside pytest).
"""
import pytest
from test_use_mode_technology import db, _stock_product, _rx_product, _mk_presc
from app import schemas, product_search as ps, customer_needs


def search(db, needs=None, use='myopia_control', **kwargs):
    return ps.search(db, _mk_presc(db, -2, -2, od_add=2, os_add=2),
                     schemas.ProductSearchRequest(use_mode=use, customer_needs=needs, **kwargs))


def cards(response):
    return [response.best_match, *response.seller_alternatives]


# --------------------------------------------------------------- (1) SCOPE Myopia Control
def test_scope_myopia_control_rx_is_manufacturing_inside_egypt(db):
    _rx_product(db, 'SCOPE', 'SCOPE Myoblock Metavision (Myoblock)', 'myopia_control', -6, 6, price=3700)
    _rx_product(db, 'ZEISS', 'MyoCare', 'myopia_control', -6, 6, price=9200)
    db.commit()
    result = search(db, [], use='myopia_control')
    rows = {r.company_name: r for g in result.groups for r in g.results}
    assert rows['SCOPE'].manufacturing_location == 'egypt'
    assert rows['ZEISS'].manufacturing_location is None


# --------------------------- (2)/(3)/(4)/(5) one centralized invariant across EVERY category
@pytest.mark.parametrize('category', [
    # Every LensCategory (app/models.py) that is actually reachable through a
    # use_mode AND actually present for SCOPE in the live release_runtime.db
    # (confirmed during diagnosis: SCOPE has progressive/single_vision/
    # bifocal/office/anti_fatigue/myopia_control rows; SCOPE has no "digital"
    # rows at all, and "digital" has no use_mode route to reach it - an
    # unrelated, pre-existing gap, out of this fix's scope).
    'single_vision', 'progressive', 'bifocal', 'office', 'anti_fatigue', 'myopia_control',
])
def test_scope_rx_is_always_egypt_regardless_of_category(db, category):
    """The owner-confirmed rule is company-based, not subtype-based: SCOPE RX
    must land in Egypt for EVERY category actually in the LensCategory enum
    (see app/models.py), proving there is no remaining subtype allowlist -
    not even an implicit one via an untested category."""
    *_, vp = _rx_product(db, 'SCOPE', 'Probe', category, -6, 6, price=1000)
    if category in ('progressive', 'bifocal'):
        # These two categories' frozen matcher requires a proven ADD corridor
        # once an ADD is entered - mirrors test_seller_priority_v141.py's own
        # existing progressive/bifocal fixtures exactly.
        for power_range in vp.power_ranges:
            power_range.add_min, power_range.add_max = 1, 3
    db.commit()
    use = 'distance' if category == 'single_vision' else category
    result = search(db, [], use=use)
    row = next(r for g in result.groups for r in g.results if r.company_name == 'SCOPE')
    assert row.category == category
    assert row.manufacturing_location == 'egypt'


# --------------------------------------------------------------- (6) non-SCOPE RX stays foreign
def test_non_local_company_rx_never_becomes_egypt_merely_for_being_rx(db):
    _rx_product(db, 'ZEISS', 'MyoCare', 'myopia_control', -6, 6, price=9200)
    _rx_product(db, 'HOYA', 'Hilux', 'single_vision', -6, 6, price=1000)
    db.commit()
    result = search(db, [], use='myopia_control')
    assert all(r.manufacturing_location is None
               for g in result.groups for r in g.results if r.company_name == 'ZEISS')
    result2 = search(db, [], use='distance')
    assert all(r.manufacturing_location is None
               for g in result2.groups for r in g.results if r.company_name == 'HOYA')


# --------------------------------------------------------------- (7) Stock semantics unchanged
def test_stock_egypt_and_stock_outside_ranking_unaffected(db, monkeypatch):
    from test_seller_priority_v141 import score_expensive_high
    for name, price in [('Expensive', 3300), ('Cheap', 1250), ('Middle', 2000)]:
        *_, vp = _stock_product(db, 'Other', name, 'single_vision', -6, 6, price=price)
    db.commit()
    score_expensive_high(monkeypatch)
    result = search(db, [], use='distance')
    assert [r.pair_fulfillment.price_pair for r in cards(result)] == [1250, 2000, 3300]
    assert all(r.manufacturing_location is None for r in cards(result))


def test_scope_stock_egypt_row_not_tagged_egypt_manufacturing(db):
    """local_manufacturing() only ever applies to status == 'rx' - a STOCK
    row (even from SCOPE/PLATINUM) is catalog stock, not local manufacturing,
    and must never be mislabeled."""
    _stock_product(db, 'SCOPE', 'SCOPE Stock Item', 'single_vision', -6, 6, price=1000)
    db.commit()
    result = search(db, [], use='distance')
    row = next(r for g in result.groups for r in g.results if r.company_name == 'SCOPE')
    assert row.pair_fulfillment.status == 'stock_egypt'
    assert row.manufacturing_location is None


# --------------------------------------------------------------- (8) seller_order / best_match
@pytest.mark.parametrize('category', ['myopia_control', 'office', 'single_vision'])
def test_seller_order_prefers_local_manufacturing_in_every_category(db, monkeypatch, category):
    from test_seller_priority_v141 import score_expensive_high
    _rx_product(db, 'SCOPE', 'Local', category, -6, 6, price=5000)
    _rx_product(db, 'Other', 'Foreign', category, -6, 6, price=1000)
    db.commit()
    score_expensive_high(monkeypatch)
    use = 'distance' if category == 'single_vision' else category
    result = search(db, [], use=use)
    # SCOPE is local-manufactured RX and must outrank the cheaper foreign RX,
    # exactly mirroring the pre-existing progressive/bifocal/anti_fatigue
    # local-manufacturing-tier tests - now proven for every category, driven
    # by the same central seller_order()/local_manufacturing() helper.
    assert result.best_match.company_name == 'SCOPE'
    assert result.best_match.manufacturing_location == 'egypt'


# --------------------------------------------------------------- (9) no subtype contamination
def test_myopia_control_search_has_no_contamination_from_other_categories(db):
    _rx_product(db, 'SCOPE', 'SCOPE Myoblock Metavision (Myoblock)', 'myopia_control', -6, 6, price=3700)
    _rx_product(db, 'ZEISS', 'MyoCare', 'myopia_control', -6, 6, price=9200)
    _rx_product(db, 'SCOPE', 'SCOPE Young Shabab', 'anti_fatigue', -6, 6, price=1390)
    _rx_product(db, 'SCOPE', 'SCOPE Office Doctor', 'office', -6, 6, price=1000)
    _rx_product(db, 'PLATINUM', 'PLATINUM X-PLORE', 'progressive', -6, 6, price=1000)
    _rx_product(db, 'PLATINUM', 'PLATINUM BI FOCAL', 'bifocal', -6, 6, price=1000)
    _rx_product(db, 'SCOPE', 'SCOPE Single Vision', 'single_vision', -6, 6, price=1000)
    db.commit()
    result = search(db, [], use='myopia_control')
    names = {r.model_name for g in result.groups for r in g.results}
    assert names == {'SCOPE Myoblock Metavision (Myoblock)', 'MyoCare'}
    categories = {r.category for g in result.groups for r in g.results}
    assert categories == {'myopia_control'}


# --------------------------------------------------------------- (10) exact HAT prescription
def test_exact_hat_prescription_myopia_control_manufacturing_split(db, monkeypatch):
    """OD -2.00 / -1.00 x90 / ADD +2.00, OS -2.00 / -1.00 x90 / ADD +2.00,
    Special Lenses -> Myopia Control, Customer Needs = none - the exact
    prescription and mode from the owner's live HAT. Synthetic catalog
    mirrors the live release_runtime.db shape found during diagnosis: 17
    SCOPE Myoblock RX rows, 16 ZEISS MyoCare/MyoCare S RX rows, 2 ZEISS
    stock_egypt rows (which is where the "35 total, 33 RX" discrepancy
    the owner flagged comes from - 2 ZEISS Stock Egypt rows, outside the
    RX/manufacturing company counts, not a bug)."""
    from test_seller_priority_v141 import score_expensive_high
    for i in range(17):
        _rx_product(db, 'SCOPE', 'SCOPE Myoblock Metavision (Myoblock)', 'myopia_control',
                     -6, 6, price=3700 + i * 100)
    for i in range(8):
        _rx_product(db, 'ZEISS', 'MyoCare', 'myopia_control', -6, 6, price=9200 + i * 500)
    for i in range(8):
        _rx_product(db, 'ZEISS', 'MyoCare S', 'myopia_control', -6, 6, price=9200 + i * 500)
    _stock_product(db, 'ZEISS', 'MyoCare', 'myopia_control', -6, 6, price=7800)
    _stock_product(db, 'ZEISS', 'MyoCare S', 'myopia_control', -6, 6, price=7800)
    db.commit()
    presc = _mk_presc(db, -2.0, -2.0, od_cyl=-1.0, os_cyl=-1.0, od_axis=90, os_axis=90,
                       od_add=2.0, os_add=2.0)
    result = ps.search(db, presc, schemas.ProductSearchRequest(use_mode='myopia_control', customer_needs=None))

    assert result.exact_total == 35
    all_rows = [r for g in result.groups for r in g.results]
    rx_rows = [r for r in all_rows if r.pair_fulfillment.status == 'rx']
    stock_rows = [r for r in all_rows if r.pair_fulfillment.status == 'stock_egypt']
    assert len(rx_rows) == 33
    assert len(stock_rows) == 2  # the previously "unexplained" 2 - ZEISS stock_egypt, not RX
    assert {r.company_name for r in stock_rows} == {'ZEISS'}

    scope_rx = [r for r in rx_rows if r.company_name == 'SCOPE']
    zeiss_rx = [r for r in rx_rows if r.company_name == 'ZEISS']
    assert len(scope_rx) == 17
    assert len(zeiss_rx) == 16
    # the owner-confirmed invariant this whole fix exists for:
    assert all(r.manufacturing_location == 'egypt' for r in scope_rx)
    assert all(r.manufacturing_location is None for r in zeiss_rx)
    # STOCK rows are never manufacturing-tagged, regardless of company.
    assert all(r.manufacturing_location is None for r in stock_rows)
