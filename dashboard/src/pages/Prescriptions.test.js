import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { PairAnswer } from './Prescriptions';

let container;
let root;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const base = {
  status: 'rx', currency: 'EGP', provenance: 'single_route',
  source_pricing_ids: [553], needs_review: false, reason: 'RX catalog availability',
};

test('unresolved add-on shows base and listed amount, with no computed final quote or internal ID', () => {
  act(() => root.render(<PairAnswer pf={{
    ...base, price_pair: null, price_confirmation_note: 'Unit pending confirmation',
    technology_addon: {
      base_price: '5000', addon_price: '1300', label: 'Blue HMC+', unit_status: 'UNIT_UNRESOLVED',
    },
  }} />));
  const text = container.textContent;
  expect(text).toContain('5000');
  expect(text).toContain('1300');
  expect(text).toContain('Blue HMC+');
  expect(text).toContain('السعر النهائي غير مؤكد');
  expect(text).toContain('Unit pending confirmation');
  expect(text).not.toContain('6300');
  expect(text).not.toContain('553');
  expect(text).not.toContain('السعر المختلط');
});

test('PIXEL provisional base price is explicitly pending confirmation', () => {
  act(() => root.render(<PairAnswer pf={{
    ...base, price_pair: '10500', price_confirmation_note: 'Hi Power confirmation required',
  }} />));
  expect(container.textContent).toContain('10500');
  expect(container.textContent).toContain('السعر بانتظار التأكيد');
  expect(container.textContent).toContain('Hi Power confirmation required');
  expect(container.textContent).not.toContain('11500');
});

test('a proven pair surcharge retains its total and included pricing remains unchanged', () => {
  act(() => root.render(<PairAnswer pf={{
    ...base, price_pair: '6300', technology_addon: {
      base_price: '5000', addon_price: '1300', label: 'Fixture add-on', unit_status: 'UNIT_PAIR_PROVEN',
    },
  }} />));
  expect(container.textContent).toContain('الإجمالي 6300 EGP');
  expect(container.textContent).not.toContain('بانتظار');
  act(() => root.render(<PairAnswer pf={{ ...base, price_pair: '5000' }} />));
  expect(container.textContent).toContain('5000 EGP / Pair');
  expect(container.textContent).not.toContain('إضافة');
});
