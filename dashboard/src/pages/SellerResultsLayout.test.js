import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { sellerSections, ManufacturerCoverage } from './Prescriptions';

const row = (id, index, price, extra = {}) => ({
  lens_model_id: id, variant_id: id, coating_id: 1, company_name: 'PIXEL',
  model_name: `Lens ${id}`, index_value: index, match_score: 100 - id,
  pair_fulfillment: { status: 'stock_egypt', provenance: 'single_route', price_pair: price,
    currency: 'EGP', source_pricing_ids: [id] }, ...extra,
});
const group = (key, results) => ({ key, results, count: results.length });

test.each(['distance', 'reading'])('SV sections have Egypt, OOE, RX then separate unknown: %s', (use_mode) => {
  const result = sellerSections({ use_mode, groups: [group('stock_market_unknown', [row(4, 1.5, 1)]),
    group('rx', [row(3, 1.5, 1)]), group('stock_out_of_egypt', [row(2, 1.5, 1)]),
    group('stock_egypt', [row(1, 1.5, 1)])] });
  expect(result.map((s) => s.key)).toEqual(['stock_egypt', 'stock_out_of_egypt', 'rx', 'stock_market_unknown']);
  expect(result[3].label).toContain('غير محدد');
});

// RECONCILED (owner-confirmed business clarification, 2026-09-22): withdraws
// the former "HAT-01" index-ascending-then-price rule these tests used to
// lock in. Index is NOT a required priority ahead of price - a lower-index
// lens can legitimately cost more once technology/coating/photochromic
// capability is factored in - so the frontend must display each group's
// results EXACTLY as the backend returns them (product_search._order_key:
// availability/status tier -> route provenance -> price ascending ->
// match_score, with a null/unresolved price already sorting last via its own
// sentinel) and never re-derive a competing notion of priority.

test.each([[], ['blue_light'], ['photo_gray'], ['photo_brown'], ['impact_resistant'], ['blue_light', 'photo_gray']].map((needs) => [needs]))(
  'A. frontend preserves backend result order exactly, regardless of need %j', (customer_needs) => {
    // Deliberately NOT price/index-sorted here - mirrors a real backend
    // response where price/match_score/provenance already decided the order;
    // a mix of indices, a pending-price row, and a null-price row are
    // interleaved in whatever sequence the backend produced.
    const pending = row(4, 1.56, 1);
    pending.pair_fulfillment.price_confirmation_note = 'Confirm';
    const unresolved = row(5, 1.53, null);
    unresolved.pair_fulfillment.technology_addon = { unit_status: 'UNIT_UNRESOLVED', base_price: 1 };
    const rows = [row(7, 1.5, 700), row(6, 1.56, 850), pending, unresolved, row(2, 1.53, 20), row(1, 1.56, 10)];
    const input = [...rows];
    const sections = sellerSections({ use_mode: 'distance', customer_needs,
      groups: [group('stock_egypt', rows)] });
    expect(sections[0].results.map((r) => r.variant_id)).toEqual(rows.map((r) => r.variant_id));
    expect(rows).toEqual(input); // never reorder/mutate the response or prices
  });

// B. The real defect this fix resolves: a higher-index but CHEAPER result
// (already ranked first by the backend) must appear before a lower-index
// but MORE EXPENSIVE one - mirrors the real audited case (PLATINUM "BLU
// STEEL", index 1.56, 600 EGP, ranked first by the backend ahead of a
// Maxxee 1.50/1250 EGP row that an index-first rule would have shown first).
test('B. higher-index cheaper result stays ahead of a lower-index pricier one when the backend returns it that way', () => {
  const rows = [row(1, 1.56, 600), row(2, 1.56, 900), row(3, 1.56, 1100),
    row(4, 1.6, 1200), row(5, 1.5, 1250), row(6, 1.5, 1300)];
  const sorted = sellerSections({ use_mode: 'distance', groups: [group('stock_egypt', rows)] })[0].results;
  expect(sorted.map((r) => r.variant_id)).toEqual([1, 2, 3, 4, 5, 6]);
});

// C. The recommended row (identified elsewhere by matching best_match's
// pricing-row identity, see SellerSafety.test.js F3) is now visually
// consistent with the first displayed result whenever the backend's own
// order already puts it there - the seller no longer sees a different row
// first while the recommended badge sits further down.
test('C. backend-recommended row (first in backend order) is also first in the displayed section', () => {
  const rows = [row(1, 1.56, 600), row(2, 1.56, 900), row(4, 1.6, 1200), row(5, 1.5, 1250)];
  const sorted = sellerSections({ use_mode: 'distance', groups: [group('stock_egypt', rows)] })[0].results;
  expect(sorted[0].variant_id).toBe(1); // the backend's best_match-equivalent row
});

test.each(['progressive', 'bifocal', 'office', 'anti_fatigue', 'myopia_control'])('E. local tier before other RX, backend order preserved within each, not brand: %s', (use_mode) => {
  // Already in backend order (index/price mixed, exactly as _order_key would
  // return it) - the local/other split must only FILTER, never reorder.
  const rows = [row(4, 1.5, 200, { company_name: 'PLATINUM', manufacturing_location: 'egypt' }),
    row(3, 1.5, 300, { company_name: 'SCOPE', manufacturing_location: 'egypt' }),
    row(2, 1.56, 100, { company_name: 'SCOPE', manufacturing_location: 'egypt' }),
    row(1, 1.5, 1, { company_name: 'HOYA' })];
  const sections = sellerSections({ use_mode, groups: [group('stock_egypt', []), group('rx', rows)] });
  expect(sections.map((s) => s.key)).toEqual(['rx']);
  expect(sections[0].tiers.map((t) => t.key)).toEqual(['local', 'other']);
  // filtering to local (egypt) keeps the backend's relative order: 4, 3, 2. Non-local: 1.
  expect(sections[0].tiers[0].results.map((r) => r.variant_id)).toEqual([4, 3, 2]);
  expect(sections[0].tiers[1].results.map((r) => r.variant_id)).toEqual([1]);
});

test('coverage counts all pages and labels pending DIVEL without implying final price', () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const el = document.createElement('div');
  const root = createRoot(el);
  const rows = Array.from({ length: 52 }, (_, i) => row(i, 1.5, 700));
  const divel = row(1067, 1.56, 2150, { company_name: 'DIVEL' });
  divel.pair_fulfillment.price_confirmation_note = 'Diameter';
  act(() => root.render(<ManufacturerCoverage groups={[group('stock_egypt', [...rows, divel])]} />));
  expect(el.textContent).toContain('PIXEL 52');
  expect(el.textContent).toContain('DIVEL 1 — يحتاج تأكيد');
  act(() => root.unmount());
});


test('suppressed empty RX has no primary section', () => {
  const sections = sellerSections({ use_mode: 'distance', groups: [
    group('stock_egypt', [row(1, 1.5, 700)]), group('rx', []),
    group('stock_market_unknown', [row(2, 1.5, 800)])] });
  expect(sections.map((s) => s.key)).toEqual(['stock_egypt', 'stock_out_of_egypt', 'stock_market_unknown']);
});
