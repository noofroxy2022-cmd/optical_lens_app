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

test.each([[], ['blue_light'], ['photo_gray'], ['photo_brown'], ['impact_resistant'], ['blue_light', 'photo_gray']].map((needs) => [needs]))(
  'index then confirmed price then pending, regardless of need %j or match score', (customer_needs) => {
    const pending = row(4, 1.5, 1);
    pending.pair_fulfillment.price_confirmation_note = 'Confirm';
    const unresolved = row(5, 1.5, null);
    unresolved.pair_fulfillment.technology_addon = { unit_status: 'UNIT_UNRESOLVED', base_price: 1 };
    const rows = [row(1, 1.56, 10), row(2, 1.53, 20), pending, unresolved,
      row(6, 1.5, 850), row(7, 1.5, 700)];
    const input = [...rows];
    const sorted = sellerSections({ use_mode: 'distance', customer_needs,
      groups: [group('stock_egypt', rows)] })[0].results;
    expect(sorted.map((r) => r.variant_id)).toEqual([7, 6, 4, 5, 2, 1]);
    expect(rows).toEqual(input); // never reorder/mutate the response or prices
  });

test.each(['progressive', 'bifocal'])('local tier before other RX, index/price not brand: %s', (use_mode) => {
  const rows = [row(1, 1.5, 1, { company_name: 'HOYA' }),
    row(2, 1.56, 100, { company_name: 'SCOPE', manufacturing_location: 'egypt' }),
    row(3, 1.5, 300, { company_name: 'SCOPE', manufacturing_location: 'egypt' }),
    row(4, 1.5, 200, { company_name: 'PLATINUM', manufacturing_location: 'egypt' })];
  const sections = sellerSections({ use_mode, groups: [group('stock_egypt', []), group('rx', rows)] });
  expect(sections.map((s) => s.key)).toEqual(['rx']);
  expect(sections[0].tiers.map((t) => t.key)).toEqual(['local', 'other']);
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
