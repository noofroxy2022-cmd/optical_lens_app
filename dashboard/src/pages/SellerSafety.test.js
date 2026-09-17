import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Simulate } from 'react-dom/test-utils';
import Prescriptions, { PairPrice, sellerHeadline, sellerNeedPayload } from './Prescriptions';
import { prescriptionAPI, companyAPI, lensModelAPI } from '../services/api';

jest.mock('../services/api', () => ({
  prescriptionAPI: { getAll: jest.fn(), search: jest.fn(), update: jest.fn(), create: jest.fn() },
  companyAPI: { getAll: jest.fn() }, lensModelAPI: { getFilterOptions: jest.fn() },
}));

let root, container;
const pf = { status: 'stock_outside', price_pair: '2500', currency: 'EGP',
  provenance: 'single_route', source_pricing_ids: [1], needs_review: false };
const record = { id: 1, od_sph_original: -2, os_sph_original: -2,
  od_cyl_original: -1, os_cyl_original: -1, od_axis_original: 90, os_axis_original: 90,
  od_sph: -2, os_sph: -2, od_cyl: -1, os_cyl: -1, od_axis: 90, os_axis: 90, od_add: 0, os_add: 0 };
const result = { company_name: 'SellerTest', model_name: 'Current Lens', lens_model_id: 1,
  variant_id: 1, coating_id: 1, index_value: 1.5, category: 'single_vision',
  od: {}, os: {}, pair_fulfillment: pf, seller_recommendation_reason: 'Proven' };
const response = { exact_total: 1, best_match: result, seller_alternatives: [], groups: [],
  availability_answer: { code: 'stock_egypt', title: 'OLD SUMMARY', detail: 'Catalog' } };

beforeAll(() => {
  window.matchMedia = () => ({ matches: false, addListener() {}, removeListener() {} });
  global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
  // jsdom's selector engine cannot evaluate AntD's modern generated CSS.
  window.getComputedStyle = () => ({ getPropertyValue: () => '',
    overflowX: 'visible', overflowY: 'visible', width: '0px', height: '0px' });
});
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  jest.clearAllMocks();
  container = document.createElement('div'); document.body.appendChild(container);
  root = createRoot(container);
  prescriptionAPI.getAll.mockResolvedValue({ data: [record] });
  prescriptionAPI.search.mockResolvedValue({ data: response });
  companyAPI.getAll.mockResolvedValue({ data: [] });
  lensModelAPI.getFilterOptions.mockResolvedValue({ data: { lens_models: [], index_value: [], category: [],
    design_variant: [], coating: [], color_variant: [], treatment_band: [] } });
});
afterEach(() => { act(() => root.unmount()); container.remove(); });
const text = () => document.body.textContent;
const settle = async () => { await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); }); };
const click = async (label) => {
  const el = Array.from(document.querySelectorAll('button, label, .ant-collapse-header')).find((x) => x.textContent.trim() === label);
  expect(el).toBeTruthy(); await act(async () => { el.click(); }); await settle();
};
const mountSearch = async () => { await act(async () => root.render(<Prescriptions />)); await settle(); await click('بحث سريع'); };
test('confirmed price is explicitly final and never halved', () => {
  act(() => root.render(<PairPrice pf={pf} />));
  expect(text()).toContain('سعر الزوج النهائي: 2500 EGP / Pair');
  expect(text()).not.toContain('1250');
});
test.each([
  { price_confirmation_note: 'PIXEL Hi Power' },
  { price_confirmation_note: 'DIVEL diameter confirmation' },
  { needs_review: true },
  { price_pair: null, technology_addon: { unit_status: 'UNIT_UNRESOLVED', base_price: 2500 } },
])('collapsed price blocks non-final quotation: %j', (patch) => {
  act(() => root.render(<PairPrice pf={{ ...pf, ...patch }} />));
  expect(text()).toContain('بانتظار تأكيد السعر');
  expect(text()).toContain('السعر الأساسي: 2500');
  expect(text()).not.toContain('سعر الزوج النهائي:');
});
test('headline prefers actionable outside stock over pending Egypt and handles pending/unknown', () => {
  expect(sellerHeadline(response).title).toContain('خارج مصر');
  expect(sellerHeadline({ ...response, best_match: null }).title).toContain('يحتاج تأكيد');
  const unknown = sellerHeadline({ ...response, best_match: { ...result, pair_fulfillment: { ...pf, status: 'stock_market_unknown' } },
    availability_answer: { title: 'STOCK — مكان التوفر غير محدد' } });
  expect(unknown.title).toContain('يحتاج تأكيد'); expect(unknown.detail).not.toContain('داخل مصر');
});
test('combined needs have one canonical AND intent; no restriction stays unrestricted', () => {
  expect(sellerNeedPayload(['blue_light', 'photo_gray'])).toEqual({ customer_needs: ['blue_light', 'photo_gray'] });
  expect(sellerNeedPayload(['blue_light', 'photo_brown']).customer_needs).toEqual(['blue_light', 'photo_brown']);
  expect(sellerNeedPayload([])).toEqual({ customer_needs: [] });
});
test('advanced price change clears Best Choice and summary; explicit search repopulates', async () => {
  await mountSearch(); expect(text()).toContain('نتائج العدسات المطابقة');
  await click('مرشحات متقدمة');
  await click('بحث'); expect(text()).toContain('نتائج العدسات المطابقة');
  await click('إحصاءات البحث والتوصيات الفنية');
  expect(text()).toContain('خيارات الزوج');
  const field = Array.from(document.querySelectorAll('.ant-input-number-input')).find((x) => x.placeholder === 'الكل');
  await act(async () => Simulate.change(field, { target: { value: '2000' } })); await settle();
  expect(text()).not.toContain('نتائج العدسات المطابقة'); expect(text()).not.toContain('خيارات الزوج');
  await click('بحث'); expect(text()).toContain('نتائج العدسات المطابقة');
  expect(prescriptionAPI.search.mock.calls.at(-1)[1].filters.max_price).toBe(2000);
});
test('use and primary need changes invalidate results; combined need is directly selectable', async () => {
  await mountSearch(); await click('قراءة — عدسة أحادية');
  expect(text()).not.toContain('نتائج العدسات المطابقة'); await click('بحث');
  await click('حماية من الضوء الأزرق'); await click('Photo Gray');
  expect(text()).not.toContain('نتائج العدسات المطابقة');
  expect(text()).not.toContain('خيارات متقدمة: تقنية إضافية');
  await click('بحث');
  expect(prescriptionAPI.search.mock.calls.at(-1)[1]).toMatchObject({ use_mode: 'reading', customer_needs: ['blue_light', 'photo_gray'] });
});
test('editing uses original values, saves ADD, clears old results and waits for Search', async () => {
  await mountSearch(); await click('قراءة — عدسة أحادية'); await click('بحث');
  await click('تعديل الوصفة الأصلية');
  expect(Number(document.querySelector('#od_sph').value)).toBe(-2);
  await act(async () => {
    Simulate.change(document.querySelector('#od_add'), { target: { value: '2' } });
    Simulate.change(document.querySelector('#os_add'), { target: { value: '2' } });
  });
  prescriptionAPI.update.mockResolvedValue({ data: { ...record, od_add: 2, os_add: 2 } });
  const calls = prescriptionAPI.search.mock.calls.length;
  await click('حفظ التعديل'); await settle();
  expect(prescriptionAPI.update).toHaveBeenCalledWith(1, expect.objectContaining({ od: { sph: -2, cyl: -1, axis: 90, add: 2 } }));
  expect(text()).not.toContain('نتائج العدسات المطابقة');
  expect(prescriptionAPI.search).toHaveBeenCalledTimes(calls);
  await click('بحث'); expect(prescriptionAPI.search).toHaveBeenCalledTimes(calls + 1);
  expect(prescriptionAPI.search.mock.calls.at(-1)[1].use_mode).toBe('reading');
});

test.each(['PIXEL Hi Power', 'DIVEL diameter confirmation'])('pending table row is safe without expanding: %s', async (note) => {
  prescriptionAPI.search.mockResolvedValue({ data: { ...response, best_match: null,
    groups: [{ key: 'rx', label: 'Pending Catalog', count: 1, results: [{ ...result,
      pair_fulfillment: { ...pf, status: 'rx', price_confirmation_note: note } }] }] } });
  await mountSearch();
  const row = document.querySelector('.ant-table-row[data-row-key="1-1-1"]')
    || Array.from(document.querySelectorAll('.ant-table-row')).find((el) => el.textContent.includes('Current Lens'));
  expect(row).toBeTruthy();
  expect(row.textContent).toContain('بانتظار تأكيد السعر');
  expect(row.textContent).toContain('السعر الأساسي: 2500');
  expect(row.textContent).not.toContain('سعر الزوج النهائي:');
  expect(document.querySelector('.ant-table-expanded-row')).toBeNull();
});
test.each(['od', 'os'])('blank %s Axis with cylinder is blocked, explicit zero is preserved', async (eye) => {
  await mountSearch(); await click('تعديل الوصفة الأصلية');
  await act(async () => Simulate.change(document.querySelector(`#${eye}_axis`), { target: { value: '' } }));
  await click('حفظ التعديل');
  expect(text()).toContain('أدخل AXIS لهذه العين عند وجود CYL غير صفر');
  expect(prescriptionAPI.update).not.toHaveBeenCalled();
  prescriptionAPI.update.mockResolvedValue({ data: { ...record, od_axis: 0, od_axis_original: 0 } });
  await act(async () => Simulate.change(document.querySelector(`#${eye}_axis`), { target: { value: '0' } }));
  await click('حفظ التعديل');
  expect(prescriptionAPI.update.mock.calls[0][1][eye].axis).toBe(0);
});

test('a late search response cannot restore results after criteria change', async () => {
  await mountSearch(); await click('مرشحات متقدمة');
  let resolve;
  prescriptionAPI.search.mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
  await click('بحث');
  const field = Array.from(document.querySelectorAll('.ant-input-number-input')).find((x) => x.placeholder === 'الكل');
  await act(async () => Simulate.change(field, { target: { value: '2000' } }));
  await act(async () => resolve({ data: response })); await settle();
  expect(text()).not.toContain('نتائج العدسات المطابقة');
  expect(text()).not.toContain('خيارات الزوج');
});

test('zero cylinder allows blank Axis for both eyes without sending zero', async () => {
  await mountSearch(); await click('تعديل الوصفة الأصلية');
  await act(async () => {
    ['od', 'os'].forEach((eye) => {
      Simulate.change(document.querySelector(`#${eye}_cyl`), { target: { value: '0' } });
      Simulate.change(document.querySelector(`#${eye}_axis`), { target: { value: '' } });
    });
  });
  prescriptionAPI.update.mockResolvedValue({ data: record });
  await click('حفظ التعديل');
  const sent = prescriptionAPI.update.mock.calls[0][1];
  expect(sent.od).toMatchObject({ cyl: 0, axis: null });
  expect(sent.os).toMatchObject({ cyl: 0, axis: null });
});


test('exact manufacturer coverage is visible above paginated tables', async () => {
  prescriptionAPI.search.mockResolvedValue({ data: { ...response, best_match: null,
    groups: [{ key: 'rx', label: 'Hidden RX', count: 3, results: [
      { ...result, company_name: 'PIXEL' }, { ...result, company_name: 'PIXEL' },
      { ...result, company_name: 'DIVEL', pair_fulfillment: { ...pf, price_confirmation_note: 'Diameter' } },
    ] }] } });
  await mountSearch();
  const coverage = document.querySelector('[aria-label="نتائج مطابقة أخرى"]');
  expect(coverage.textContent).toContain('PIXEL 2');
  expect(coverage.textContent).toContain('DIVEL 1 — يحتاج تأكيد');
  expect(coverage.textContent).not.toContain('PIXEL 2 — يحتاج تأكيد');
  expect(document.querySelector('[data-seller-section="rx"] .ant-table-row').textContent).toContain('Current Lens');
});

test.each([
  ['حماية من الضوء الأزرق', 'blue_light'], ['Photo Gray', 'photo_gray'],
  ['Photo Brown', 'photo_brown'], ['مقاومة للكسر', 'impact_resistant'],
])('four visible need toggles: %s sends canonical list and deselects to unrestricted', async (label, need) => {
  await mountSearch();
  const buttons = document.querySelector('[role="group"][aria-label="احتياج العميل"]').querySelectorAll('button');
  expect(buttons).toHaveLength(4);
  expect(prescriptionAPI.search.mock.calls.at(-1)[1]).toMatchObject({ customer_needs: [] });
  await click(label); expect(text()).not.toContain('نتائج العدسات المطابقة');
  await click('بحث');
  const payload = prescriptionAPI.search.mock.calls.at(-1)[1];
  expect(payload.customer_needs).toEqual([need]);
  expect(payload.technology_intent).toBeUndefined();
  expect(payload.customer_need).toBeUndefined();
  await click(label); await click('بحث');
  expect(prescriptionAPI.search.mock.calls.at(-1)[1].customer_needs).toEqual([]);
});

test('need change while request is pending rejects its late response', async () => {
  await mountSearch();
  let resolve;
  prescriptionAPI.search.mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
  await click('بحث'); await click('حماية من الضوء الأزرق'); await click('مقاومة للكسر');
  await act(async () => resolve({ data: response })); await settle();
  expect(text()).not.toContain('نتائج العدسات المطابقة');
  await click('بحث');
  expect(prescriptionAPI.search.mock.calls.at(-1)[1].customer_needs).toEqual(['blue_light', 'impact_resistant']);
});

test('local manufacturing label comes from the result; generic RX is not called foreign', () => {
  const local = { ...result, manufacturing_location: 'egypt', pair_fulfillment: { ...pf, status: 'rx' } };
  expect(sellerHeadline({ ...response, best_match: local }).title).toContain('تصنيع داخل مصر');
  expect(sellerHeadline({ ...response, best_match: { ...local, manufacturing_location: null } }).title).not.toContain('خارج مصر');
});

test('primary tables replace recommendation cards and paginate without hiding manufacturer counts', async () => {
  const rows = Array.from({ length: 20 }, (_, i) => ({ ...result, variant_id: i + 1,
    company_name: i === 19 ? 'DIVEL' : 'PIXEL', model_name: `Catalog Lens ${i + 1}`,
    pair_fulfillment: { ...pf, status: 'stock_egypt', source_pricing_ids: [i + 1],
      price_confirmation_note: i === 19 ? 'Diameter confirmation' : null } }));
  prescriptionAPI.search.mockResolvedValue({ data: { ...response, exact_total: 20,
    best_match: rows[0], seller_alternatives: rows.slice(1, 3),
    groups: [{ key: 'stock_egypt', count: 20, results: rows }] } });
  await mountSearch();
  const section = document.querySelector('[data-seller-section="stock_egypt"]');
  expect(section.textContent).toContain('STOCK داخل مصر — 20 نتيجة');
  expect(section.textContent).toContain('PIXEL 19');
  expect(section.textContent).toContain('DIVEL 1 — يحتاج تأكيد');
  expect(section.querySelectorAll('.ant-table-row')).toHaveLength(15);
  expect(text()).not.toContain('⭐ أفضل خيار للزوج');
  expect(text()).not.toContain('بديل 1');
  expect(section.querySelector('thead').textContent).not.toContain('الدرجة');
  expect(document.querySelectorAll('.ant-table-expanded-row')).toHaveLength(0);
});
