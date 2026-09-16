import React, { useEffect, useState } from 'react';
import {
  Table, Button, Modal, Descriptions, Tag, message, Popconfirm, Form, Input, InputNumber,
  Row, Col, Card, Empty, Alert, Radio, Select, Collapse, Divider, Space,
} from 'antd';
import {
  EyeOutlined, DeleteOutlined, PlusOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import { prescriptionAPI, companyAPI, lensModelAPI } from '../services/api';

const { Panel } = Collapse;

const errMsg = (error, fallback) => {
  const d = error?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d.length) return d.map((x) => x.msg || JSON.stringify(x)).join(' | ');
  if (d && typeof d === 'object') return d.message || JSON.stringify(d);
  return error?.response?.data?.message || fallback;
};

const availLabel = (v) => (v === 'stock' ? <Tag color="green">STOCK</Tag> : <Tag color="orange">RX</Tag>);

// CR39 presentation rule: ordinary CR39 is not a selling point - show only the
// index. Named materials (PNX, EYAS, EYNOA, polycarbonate, trivex, high-index …)
// stay visible. DB is unchanged; this is display-only.
const ORDINARY_MATERIAL = new Set(['cr39', 'cr-39', 'cr 39', 'plastic', 'standard', 'organic', '']);
const materialLabel = (material) => {
  const m = (material || '').toString().trim();
  if (ORDINARY_MATERIAL.has(m.toLowerCase())) return null;
  return m;
};
const indexMaterialText = (material, indexValue) => {
  const idxTxt = indexValue != null ? `Index ${Number(indexValue).toFixed(2)}` : 'Index —';
  const mat = materialLabel(material);
  return mat ? `${mat} · ${idxTxt}` : idxTxt;
};

// ---- V1.0.2 per-eye / pair helpers ----
const PAIR_STATUS_AR = {
  stock_egypt: '🇪🇬 STOCK داخل مصر',
  stock_outside: '🌍 STOCK خارج مصر',
  stock_market_unknown: '❔ STOCK — مكان التوفر غير محدد',
  rx: '🏭 RX / تصنيع',
  split: '⚠️ مصدر غير موحد',
  unavailable: '❌ غير متوفر',
  eligibility_unknown: '❓ توافق الوصفة غير مؤكد',
};
const PAIR_STATUS_COLOR = {
  stock_egypt: 'green', stock_outside: 'gold', stock_market_unknown: 'cyan',
  rx: 'orange', split: 'volcano', unavailable: 'red',
  eligibility_unknown: 'default',
};
const yn = (b) => (b ? <span style={{ color: '#52c41a' }}>✅</span> : <span style={{ color: '#cf1322' }}>❌</span>);

// OD/OS × (Egypt / Outside / RX) verified-availability matrix (§8).
const PairMatrix = ({ od, os }) => (
  <table style={{ borderCollapse: 'collapse', fontSize: 13 }}>
    <thead>
      <tr>
        <th style={{ padding: '2px 10px', textAlign: 'right' }} />
        <th style={{ padding: '2px 10px' }}>OD</th>
        <th style={{ padding: '2px 10px' }}>OS</th>
      </tr>
    </thead>
    <tbody>
      <tr><td style={{ padding: '2px 10px' }}>STOCK داخل مصر</td><td align="center">{yn(od.stock_egypt)}</td><td align="center">{yn(os.stock_egypt)}</td></tr>
      <tr><td style={{ padding: '2px 10px' }}>STOCK خارج مصر</td><td align="center">{yn(od.stock_outside)}</td><td align="center">{yn(os.stock_outside)}</td></tr>
      <tr><td style={{ padding: '2px 10px' }}>STOCK — سوق غير محدد</td><td align="center">{yn(od.stock_market_unknown)}</td><td align="center">{yn(os.stock_market_unknown)}</td></tr>
      <tr><td style={{ padding: '2px 10px' }}>RX / تصنيع</td><td align="center">{yn(od.rx)}</td><td align="center">{yn(os.rx)}</td></tr>
    </tbody>
  </table>
);

// "أفضل حل موحد للزوج" + a pair price only when provenance is proven (§4/§8/§2).
export const PairAnswer = ({ pf }) => {
  const priced = pf.price_pair != null;
  const unproven = pf.provenance === 'unproven_mixed';
  const unknownEligibility = pf.status === 'eligibility_unknown';
  return (
    <div>
      <div>
        <b>أفضل حل موحد للزوج: </b>
        <Tag color={PAIR_STATUS_COLOR[pf.status]}>{PAIR_STATUS_AR[pf.status] || pf.status}</Tag>
        {(pf.status === 'stock_egypt' || pf.status === 'stock_outside' || pf.status === 'stock_market_unknown') &&
          <span style={{ color: '#888', fontSize: 12 }}>— حسب الكتالوج</span>}
        {pf.needs_review && <Tag color="volcano" style={{ marginRight: 6 }}>بحاجة لمراجعة</Tag>}
      </div>
      <div style={{ marginTop: 4 }}>
        {/* eligibility_unknown: never label this line "السعر" - price_pair is
            always null here (backend never exposes a catalog price as an
            actionable pair price while power eligibility is unresolved), so
            this deliberately reads as a compatibility question, not a price. */}
        <b>{unknownEligibility ? 'توافق الوصفة: ' : pf.price_confirmation_note ? 'السعر بانتظار التأكيد: ' : 'السعر: '}</b>
        {priced
          ? <span>{`${pf.price_pair} ${pf.currency || ''} / Pair`}</span>
          : pf.price_confirmation_note
            ? <span style={{ color: '#ad6800' }}>بانتظار تأكيد المعمل — لا يوجد سعر نهائي مؤكد</span>
            : unknownEligibility
            ? <span style={{ color: '#cf1322' }}>غير مؤكد بسبب نطاق القوة — يحتاج مراجعة قبل اعتماد الطلب</span>
            : unproven
              ? <span style={{ color: '#cf1322' }}>غير محسوب — مصدر تسعير غير مثبت (unproven mixed pricing provenance)</span>
              : <span style={{ color: '#cf1322' }}>السعر المختلط: غير محسوب — غير مثبت في الكتالوج</span>}
      </div>
      {/* An unresolved surcharge unit must never display a computed total. */}
      {pf.technology_addon && (
        <div style={{ marginTop: 4, color: '#0958d9', fontSize: 12, background: '#e6f4ff',
                     border: '1px solid #91caff', borderRadius: 4, padding: '4px 8px' }}>
          ℹ️ إضافة لتوفير التكنولوجيا المطلوبة —
          الأساس {pf.technology_addon.base_price} {pf.currency}؛ {pf.technology_addon.label} {pf.technology_addon.addon_price} {pf.currency}
          {pf.technology_addon.unit_status === 'UNIT_UNRESOLVED'
            ? ' — وحدة الإضافة بانتظار التأكيد؛ السعر النهائي غير مؤكد'
            : ` — الإجمالي ${pf.price_pair} ${pf.currency}`}
        </div>
      )}
      {/* Generic, catalog-driven caveat: base price/eligibility above are
          already proven either way - this never hides the price, never
          marks the lens unavailable, and never touches RX eligibility. Text
          comes entirely from the backend (VariantPricing.price_confirmation_note);
          this component has no manufacturer-specific wording of its own. */}
      {pf.price_confirmation_note && (
        <div style={{ marginTop: 4, color: '#ad6800', fontSize: 12, background: '#fffbe6',
                     border: '1px solid #ffe58f', borderRadius: 4, padding: '4px 8px' }}>
          ⚠️ {pf.price_confirmation_note}
        </div>
      )}
      <div style={{ marginTop: 4, color: '#666', fontSize: 12 }}>{pf.reason}</div>
    </div>
  );
};

// display-only labels for the fixed LensCategory enum; the canonical value sent
// to the backend always stays the raw catalog string (never one of these labels)
const CATEGORY_LABELS = {
  single_vision: 'Single Vision',
  progressive: 'Progressive',
  bifocal: 'Bifocal',
  office: 'Office',
  digital: 'Digital',
};

const ANSWER_TYPE = {
  stock_egypt: 'success', stock_out_of_egypt: 'warning', stock_market_unknown: 'warning',
  rx_only: 'warning', split: 'warning', none: 'error', validation_error: 'error',
};

// V1.2 core-workflow: customer-facing use-mode / technology-intent labels.
// Values sent to the backend are the canonical English tokens (see
// backend/app/technology_evidence.py); labels are Arabic display text only.
const USE_MODE_OPTIONS = [
  { value: 'distance', label: 'مسافات' },
  { value: 'reading', label: 'قراءة' },
  { value: 'bifocal', label: 'Bifocal' },
  { value: 'progressive', label: 'Progressive' },
];
const CUSTOMER_NEED_OPTIONS = [
  { value: 'none', label: 'بدون احتياج إضافي' },
  { value: 'screens_blue_light', label: 'الشاشات / ترشيح الضوء الأزرق' },
  { value: 'photochromic_gray', label: 'فوتوكروميك رمادي' },
  { value: 'photochromic_brown', label: 'فوتوكروميك بني' },
  { value: 'driving', label: 'القيادة' },
  { value: 'sun', label: 'الشمس' },
  { value: 'thinner_lens', label: 'عدسة رقيقة حسب الكتالوج' },
  { value: 'high_impact_resistance', label: 'مقاومة الصدمات حسب الكتالوج' },
  { value: 'best_optical_clarity', label: 'أفضل نقاء بصري — الدليل غير كافٍ', disabled: true },
];

const TECHNOLOGY_OPTIONS = [
  { value: 'none', label: 'عادي' },
  { value: 'blue_light', label: 'حماية من الضوء الأزرق' },
  { value: 'photo_gray', label: 'Photo Gray' },
  { value: 'photo_brown', label: 'Photo Brown' },
  { value: 'blue_photo_gray', label: 'Blue + Photo Gray' },
  { value: 'blue_photo_brown', label: 'Blue + Photo Brown' },
];

// Canonical proven-pair statuses (backend PairFulfillment.status) that may
// render as the green "⭐ أفضل خيار للزوج" Best Choice card - the ONLY
// statuses that represent a verified, priced route for BOTH eyes together
// WITH a proven availability route/location.
// "unavailable" / "eligibility_unknown" / "split" must never be treated as a
// proven "best choice", no matter how informative the surfaced candidate is.
// "stock_market_unknown" (Phase 3C) is deliberately EXCLUDED here (Phase 3C
// final micro-fix): it IS a proven STOCK price/eligibility for both eyes,
// and still renders as a normal, priced, optically-compatible result in its
// own group - but its stock LOCATION (Egypt / Out Of Egypt) is unproven, so
// it must never wear the same green "verified location" Best Choice badge
// as stock_egypt/stock_outside/rx.
const ACTIONABLE_PAIR_STATUSES = ['stock_egypt', 'stock_outside', 'rx'];
const isActionableBestMatch = (best) => (
  !!best
  && !!best.pair_fulfillment
  && ACTIONABLE_PAIR_STATUSES.includes(best.pair_fulfillment.status)
  && best.pair_fulfillment.price_pair != null
  && Number(best.pair_fulfillment.price_pair) > 0
  && best.pair_fulfillment.provenance === 'single_route'
  && !best.pair_fulfillment.needs_review
  && !best.pair_fulfillment.price_confirmation_note
);

const EMPTY_FACETS = { lens_models: [], index_value: [], category: [], design_variant: [], coating: [], color_variant: [], treatment_band: [] };

// Maps PairFulfillment.status (the proven pair-level route) to the matching
// LensSearchGroup.key so the decision-relevant group can be opened by default.
// Note the deliberate naming difference between the two enums for the same
// concept: pair status "stock_outside" vs. group key "stock_out_of_egypt".
const STATUS_TO_DEFAULT_GROUP_KEY = {
  stock_egypt: 'stock_egypt',
  stock_outside: 'stock_out_of_egypt',
  stock_market_unknown: 'stock_market_unknown',
  rx: 'rx',
  split: 'split',
  eligibility_unknown: 'eligibility_unknown',
};

// Computes which result groups should start expanded for a given search
// response: the group matching the proven best-pair route, plus the
// eligibility_unknown group (when populated) since it always represents
// rows that need employee review regardless of the best-pair outcome.
const defaultOpenGroupKeys = (data) => {
  if (!data || !Array.isArray(data.groups)) return [];
  const openKeys = new Set();
  const status = data.best_match?.pair_fulfillment?.status;
  const mappedKey = status && STATUS_TO_DEFAULT_GROUP_KEY[status];
  if (mappedKey && data.groups.some((g) => g.key === mappedKey && g.count > 0)) {
    openKeys.add(mappedKey);
  }
  const reviewGroup = data.groups.find((g) => g.key === 'eligibility_unknown' && g.count > 0);
  if (reviewGroup) openKeys.add(reviewGroup.key);
  return Array.from(openKeys);
};

const Prescriptions = () => {
  const [prescriptions, setPrescriptions] = useState([]);
  const [selected, setSelected] = useState(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [loading, setLoading] = useState(false);

  const [createVisible, setCreateVisible] = useState(false);
  const [createForm] = Form.useForm();
  const [creating, setCreating] = useState(false);

  // ---- product search panel ----
  const [searchVisible, setSearchVisible] = useState(false);
  const [searchFor, setSearchFor] = useState(null);
  const [searching, setSearching] = useState(false);
  const [searchData, setSearchData] = useState(null);
  // Which result-group Collapse panels are open. Controlled (not
  // defaultActiveKey) because the search Modal/Collapse instance persists
  // across repeated searches within one session (see the effect below) -
  // defaultActiveKey would only apply once, on first mount.
  const [activePanelKeys, setActivePanelKeys] = useState([]);
  // V1.2 core-workflow: what the customer wants made (distance/reading/
  // bifocal/progressive) and a manufacturer-agnostic technology need. Both
  // are independent of `mode` (automatic vs targeted) below - the employee
  // still enters the doctor's prescription only once and never computes a
  // Reading power or a manufacturer's own technology naming by hand.
  const [usageMode, setUsageMode] = useState('distance');
  const [customerNeed, setCustomerNeed] = useState('none');
  const [technologyIntent, setTechnologyIntent] = useState('none');
  const [mode, setMode] = useState('automatic');
  const [companies, setCompanies] = useState([]);
  const [filters, setFilters] = useState({});
  // Catalog-driven distinct-options facets for every targeted-search dimension
  // (V1.0.1 UX hotfix). Populated from GET /lens-models/filter-options, which is
  // recomputed on every filter change against whichever OTHER filters are
  // currently active - a true cascading AND intersection with no fixed order and
  // no manufacturer-specific branching. Product/company are NOT required for any
  // of these to be populated.
  const [facets, setFacets] = useState(EMPTY_FACETS);
  // remembers product names seen in any earlier facets response, so a selected
  // Product can still show its real name even if it drops out of a later,
  // narrower options list (it must stay selected regardless - see withSelected)
  const [modelNameById, setModelNameById] = useState({});

  useEffect(() => {
    loadPrescriptions();
    companyAPI.getAll().then((r) => setCompanies(r.data)).catch(() => {});
  }, []);

  // Resets which result groups are open only when a genuinely NEW search
  // response arrives (a new searchData object, including the null reset at
  // the start of a search). Manual panel toggles the user makes afterward
  // only touch activePanelKeys, so they are never overridden until the next
  // real search response lands.
  useEffect(() => {
    setActivePanelKeys(defaultOpenGroupKeys(searchData));
  }, [searchData]);

  const loadPrescriptions = async () => {
    setLoading(true);
    try {
      const res = await prescriptionAPI.getAll();
      setPrescriptions(res.data);
    } catch (error) {
      message.error(errMsg(error, 'فشل تحميل الوصفات'));
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await prescriptionAPI.delete(id);
      message.success('تم الحذف');
      loadPrescriptions();
    } catch (error) {
      message.error(errMsg(error, 'فشل الحذف'));
    }
  };

  const viewDetails = (record) => {
    setSelected(record);
    setModalVisible(true);
  };

  const handleCreate = async (values) => {
    setCreating(true);
    try {
      const payload = {
        customer_name: values.customer_name || null,
        customer_phone: values.customer_phone || null,
        pd: values.pd ?? null,
        notes: values.notes || null,
        od: { sph: values.od_sph, cyl: values.od_cyl ?? 0, axis: values.od_axis ?? 0, add: values.od_add ?? 0 },
        os: { sph: values.os_sph, cyl: values.os_cyl ?? 0, axis: values.os_axis ?? 0, add: values.os_add ?? 0 },
      };
      const res = await prescriptionAPI.create(payload);
      message.success('تم إنشاء الوصفة');
      setCreateVisible(false);
      createForm.resetFields();
      await loadPrescriptions();
      openSearch(res.data);
    } catch (error) {
      message.error(errMsg(error, 'فشل إنشاء الوصفة'));
    } finally {
      setCreating(false);
    }
  };

  const openSearch = (record) => {
    setSearchFor(record);
    setSearchData(null);
    setMode('automatic');
    setUsageMode('distance');
    setCustomerNeed('none');
    setTechnologyIntent('none');
    setFilters({});
    setFacets(EMPTY_FACETS);
    setModelNameById({});
    setSearchVisible(true);
    // explicit null/'none' overrides - never rely on possibly-stale usageMode/
    // technologyIntent state left over from a previous prescription's session
    // (same lesson as the P1 Collapse fix: this Modal instance persists across
    // openSearch calls, so a closure-read of current state here could be stale).
    runSearch(record, 'automatic', {}, 'distance', 'none', 'none');
    refreshFacetOptions({});
  };

  // params accepted by GET /lens-models/filter-options; company_id/lens_model_id
  // are NOT required - every dimension is independently optional (V1.0.1 UX hotfix)
  const buildFacetParams = (f) => {
    const p = {};
    if (f.company_id) p.company_id = f.company_id;
    if (f.lens_model_id) p.lens_model_id = f.lens_model_id;
    if (f.index_value != null && f.index_value !== '') p.index_value = f.index_value;
    if (f.category) p.category = f.category;
    if (f.design_variant) p.design_variant = f.design_variant;
    if (f.coating) p.coating = f.coating;
    if (f.color_variant) p.color_variant = f.color_variant;
    if (f.treatment_band) p.treatment_band = f.treatment_band;
    if (f.availability && f.availability !== 'both') p.availability = f.availability;
    if (f.market_scope && f.market_scope !== 'all') p.market_scope = f.market_scope;
    return p;
  };

  // Recomputes every facet's distinct-OPTIONS-TO-OFFER list against whichever
  // OTHER filters are currently active (true cascading AND intersection, no
  // fixed selection order). This ONLY changes what the dropdowns show next -
  // it must NEVER clear a filter the user already picked. A user-selected value
  // is part of the requested specification and stays selected even if the fresh
  // intersection no longer contains it (search may then legitimately return 0).
  const refreshFacetOptions = async (nextFilters) => {
    try {
      const r = await lensModelAPI.getFilterOptions(buildFacetParams(nextFilters));
      const d = r.data || EMPTY_FACETS;
      setFacets(d);
      if (d.lens_models.length) {
        setModelNameById((m) => {
          const next = { ...m };
          d.lens_models.forEach((mm) => { next[mm.id] = mm.name; });
          return next;
        });
      }
    } catch (e) { /* non-fatal - filters stay optional, options just don't refresh */ }
  };

  // TRUE parent-identity check, used ONLY when Company or Product itself
  // changes. Scoped to ONLY that entity (company_id, or company_id+lens_model_id)
  // with none of the sibling commercial filters applied, so it answers "does
  // this value exist AT ALL under the new entity" - not "is it still compatible
  // with whatever else happens to be selected right now". Only a value that
  // fails THIS identity check may be explicitly cleared (spec section 2/5D/5E);
  // no other filter change is ever allowed to clear a sibling filter.
  const clearIdentityInvalidChildren = async (scopeParams, next, { checkProduct }) => {
    try {
      const r = await lensModelAPI.getFilterOptions(scopeParams);
      const d = r.data || EMPTY_FACETS;
      const out = { ...next };
      if (checkProduct && out.lens_model_id != null && !d.lens_models.some((m) => m.id === out.lens_model_id)) out.lens_model_id = undefined;
      if (out.category && !d.category.includes(out.category)) out.category = undefined;
      if (out.index_value != null && !d.index_value.includes(out.index_value)) out.index_value = undefined;
      if (out.design_variant && !d.design_variant.includes(out.design_variant)) out.design_variant = undefined;
      if (out.color_variant && !d.color_variant.includes(out.color_variant)) out.color_variant = undefined;
      if (out.treatment_band && !d.treatment_band.includes(out.treatment_band)) out.treatment_band = undefined;
      if (out.coating && !d.coating.some((c) => c.code === out.coating)) out.coating = undefined;
      return out;
    } catch (e) {
      return next; // non-fatal - never clear a user selection just because this check failed
    }
  };

  const onCompanyChange = async (companyId) => {
    let next = { ...filters, company_id: companyId };
    if (companyId) {
      next = await clearIdentityInvalidChildren({ company_id: companyId }, next, { checkProduct: true });
    }
    setFilters(next);
    refreshFacetOptions(next);
  };

  const onModelChange = async (modelId) => {
    let next = { ...filters, lens_model_id: modelId };
    if (modelId) {
      next = await clearIdentityInvalidChildren({ company_id: filters.company_id, lens_model_id: modelId }, next, { checkProduct: false });
    }
    setFilters(next);
    refreshFacetOptions(next);
  };

  // Every other catalog-driven field: set the value and refresh what the OTHER
  // dropdowns offer next - never clear any sibling filter. No fixed order.
  const onFilterFieldChange = (key) => (value) => {
    const next = { ...filters, [key]: value };
    setFilters(next);
    refreshFacetOptions(next);
  };

  // Keeps a user-selected value visible/selected in its Select even when the
  // freshly computed options no longer contain it (spec: never silently drop a
  // selected filter). Injects it back in, visually flagged as currently
  // unreachable with the rest of the selection, instead of vanishing.
  const withSelected = (options, selectedValue, fallbackLabel) => {
    if (selectedValue == null || options.some((o) => o.value === selectedValue)) return options;
    return [...options, { value: selectedValue, label: `${fallbackLabel} ⚠️ غير متاح بهذه المرشحات` }];
  };

  const buildFilterPayload = () => {
    const f = filters;
    const out = {};
    if (f.company_id) out.company_id = f.company_id;
    if (f.lens_model_id) out.lens_model_id = f.lens_model_id;
    if (f.index_value != null && f.index_value !== '') out.index_value = Number(f.index_value);
    if (f.category) out.category = f.category;
    if (f.design_variant) out.design_variant = f.design_variant;
    if (f.coating) out.coating = f.coating;
    if (f.color_variant) out.color_variant = f.color_variant;
    if (f.treatment_band) out.treatment_band = f.treatment_band;
    if (f.availability && f.availability !== 'both') out.availability = f.availability;
    if (f.market_scope && f.market_scope !== 'all') out.market_scope = f.market_scope;
    if (f.max_price != null && f.max_price !== '') out.max_price = Number(f.max_price);
    return out;
  };

  const runSearch = async (record, useMode, rawFilters, usageModeOverride, technologyIntentOverride, needOverride) => {
    const m = useMode ?? mode;
    const um = usageModeOverride !== undefined ? usageModeOverride : usageMode;
    const ti = technologyIntentOverride !== undefined ? technologyIntentOverride : technologyIntent;
    setSearching(true);
    setSearchData(null);
    try {
      const payload = { mode: m, customer_need: needOverride !== undefined ? needOverride : customerNeed };
      if (m === 'targeted') payload.filters = rawFilters ?? buildFilterPayload();
      if (um) payload.use_mode = um;
      if (ti && ti !== 'none') payload.technology_intent = ti;
      const res = await prescriptionAPI.search(record.id, payload);
      setSearchData(res.data);
    } catch (error) {
      message.error(errMsg(error, 'فشل البحث'));
    } finally {
      setSearching(false);
    }
  };

  const columns = [
    { title: 'العميل', dataIndex: 'customer_name', key: 'customer_name', render: (v) => v || '—' },
    { title: 'OD SPH', dataIndex: 'od_sph', key: 'od_sph' },
    { title: 'OS SPH', dataIndex: 'os_sph', key: 'os_sph' },
    { title: 'PD', dataIndex: 'pd', key: 'pd', render: (v) => v || '—' },
    { title: 'التاريخ', dataIndex: 'created_at', key: 'created_at', render: (v) => new Date(v).toLocaleString('ar-SA') },
    {
      title: 'الإجراءات',
      key: 'actions',
      render: (_, record) => (
        <>
          <Button icon={<ThunderboltOutlined />} size="small" type="primary" onClick={() => openSearch(record)} style={{ marginRight: 8 }}>
            بحث سريع
          </Button>
          <Button icon={<EyeOutlined />} size="small" onClick={() => viewDetails(record)} style={{ marginRight: 8 }}>عرض</Button>
          <Popconfirm title="هل أنت متأكد؟" onConfirm={() => handleDelete(record.id)}>
            <Button danger icon={<DeleteOutlined />} size="small">حذف</Button>
          </Popconfirm>
        </>
      ),
    },
  ];

  // ---- V1.0.2 exact result = one commercial option (PerEyeProductResult) ----
  const resultColumns = [
    { title: 'الشركة', key: 'company', width: 100, render: (_, r) => r.company_name || '—' },
    { title: 'الموديل', key: 'model', width: 140, render: (_, r) => r.model_name || '—' },
    { title: 'المادة / Index', key: 'idx', width: 150, render: (_, r) => indexMaterialText(r.material, r.index_value) },
    { title: 'الفئة', key: 'category', width: 100, render: (_, r) => r.category || '—' },
    { title: 'التصميم', key: 'design', width: 120, render: (_, r) => r.design_variant || '—' },
    { title: 'الطلاء', key: 'coating', width: 120, render: (_, r) => r.coating_name || r.coating_code || '—' },
    { title: 'التقنية / اللون', key: 'tech', width: 120, render: (_, r) => r.color_variant || '—' },
    { title: 'OD', key: 'od', width: 70, align: 'center', render: (_, r) => <Tag color={PAIR_STATUS_COLOR[r.od.best] || 'default'}>{({ stock_egypt: 'مصر', stock_outside: 'خارج', stock_market_unknown: 'سوق؟', rx: 'RX', unknown: '؟', none: '—' })[r.od.best]}</Tag> },
    { title: 'OS', key: 'os', width: 70, align: 'center', render: (_, r) => <Tag color={PAIR_STATUS_COLOR[r.os.best] || 'default'}>{({ stock_egypt: 'مصر', stock_outside: 'خارج', stock_market_unknown: 'سوق؟', rx: 'RX', unknown: '؟', none: '—' })[r.os.best]}</Tag> },
    { title: 'حل الزوج', key: 'pair', width: 130, render: (_, r) => <Tag color={PAIR_STATUS_COLOR[r.pair_fulfillment.status]}>{PAIR_STATUS_AR[r.pair_fulfillment.status]}</Tag> },
    { title: 'سعر الزوج', key: 'price', width: 130, render: (_, r) => (r.pair_fulfillment.price_pair != null
      ? `${r.pair_fulfillment.price_pair} ${r.pair_fulfillment.currency || ''} / Pair`
      : <span style={{ color: '#cf1322' }}>{r.pair_fulfillment.status === 'eligibility_unknown' ? 'غير مؤكد (نطاق القوة)' : 'غير محسوب'}</span>) },
    { title: 'الدرجة', key: 'score', width: 64, render: (_, r) => r.match_score?.toFixed(1) },
  ];

  const rowKey = (r) => `${r.lens_model_id}-${r.variant_id}-${r.coating_id}`;

  const renderResultCard = (r) => (
    <>
      {r.seller_recommendation_reason && (
        <Alert type="info" message={r.seller_recommendation_reason} style={{ marginBottom: 10 }} />
      )}
      <Descriptions size="small" column={3} bordered style={{ marginBottom: 10 }}>
        <Descriptions.Item label="الشركة">{r.company_name || '—'}</Descriptions.Item>
        <Descriptions.Item label="الموديل">{r.model_name}</Descriptions.Item>
        <Descriptions.Item label="المادة / Index">{indexMaterialText(r.material, r.index_value)}</Descriptions.Item>
        <Descriptions.Item label="الفئة">{r.category || '—'}</Descriptions.Item>
        <Descriptions.Item label="التصميم">{r.design_variant || '—'}</Descriptions.Item>
        <Descriptions.Item label="الطلاء">{r.coating_name || r.coating_code || '—'}</Descriptions.Item>
        <Descriptions.Item label="التقنية / اللون">{r.color_variant || '—'}</Descriptions.Item>
        <Descriptions.Item label="الدرجة">{r.match_score?.toFixed(1)}</Descriptions.Item>
        <Descriptions.Item label="العملة">{r.currency}</Descriptions.Item>
      </Descriptions>
      <Row gutter={16}>
        <Col><PairMatrix od={r.od} os={r.os} /></Col>
        <Col flex="auto"><PairAnswer pf={r.pair_fulfillment} /></Col>
      </Row>
    </>
  );

  // ---- alternatives still carry a frozen-matcher LensMatchResult ----
  const renderLensMatchCard = (r) => (
    <Descriptions size="small" column={3} bordered>
      <Descriptions.Item label="الشركة">{r.lens_model?.company?.name || '—'}</Descriptions.Item>
      <Descriptions.Item label="الموديل">{r.lens_model?.name}</Descriptions.Item>
      <Descriptions.Item label="المادة / Index">{indexMaterialText(r.variant?.material, r.variant?.index_value)}</Descriptions.Item>
      <Descriptions.Item label="الفئة">{r.lens_model?.category}</Descriptions.Item>
      <Descriptions.Item label="التصميم">{r.design_variant || r.variant?.design_variant || '—'}</Descriptions.Item>
      <Descriptions.Item label="الطلاء">{r.coating_name || r.coating_code || '—'}</Descriptions.Item>
      <Descriptions.Item label="التقنية / اللون">{r.color_variant || r.variant?.color_variant || '—'}</Descriptions.Item>
      <Descriptions.Item label="سعر التجزئة (زوج)">{`${r.price_pair} ${r.currency}`}</Descriptions.Item>
      <Descriptions.Item label="التوفر">
        {availLabel(r.availability)}{' '}
        <span style={{ color: '#888', fontSize: 12 }}>{r.availability === 'stock' ? '— حسب الكتالوج' : '— RX / تصنيع'}</span>
      </Descriptions.Item>
      <Descriptions.Item label="السوق">{r.market_scope || '—'}</Descriptions.Item>
      <Descriptions.Item label="الدرجة">{r.match_score?.toFixed(1)}</Descriptions.Item>
      <Descriptions.Item label="السبب" span={2}>{r.reason}</Descriptions.Item>
    </Descriptions>
  );

  const sd = searchData;
  const best = sd?.best_match;
  const bestIsActionable = isActionableBestMatch(best);

  return (
    <div>
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>📝 الوصفات الطبية</h1>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateVisible(true)}>وصفة جديدة</Button>
      </Row>
      <Table dataSource={prescriptions} columns={columns} rowKey="id" loading={loading} />

      {/* تفاصيل الوصفة */}
      <Modal title="تفاصيل الوصفة" open={modalVisible} onCancel={() => setModalVisible(false)} footer={null} width={600}>
        {selected && (
          <Descriptions bordered column={2}>
            <Descriptions.Item label="العميل">{selected.customer_name || '—'}</Descriptions.Item>
            <Descriptions.Item label="الهاتف">{selected.customer_phone || '—'}</Descriptions.Item>
            <Descriptions.Item label="OD SPH">{selected.od_sph}</Descriptions.Item>
            <Descriptions.Item label="OS SPH">{selected.os_sph}</Descriptions.Item>
            <Descriptions.Item label="OD CYL">{selected.od_cyl}</Descriptions.Item>
            <Descriptions.Item label="OS CYL">{selected.os_cyl}</Descriptions.Item>
            <Descriptions.Item label="OD Axis">{selected.od_axis}°</Descriptions.Item>
            <Descriptions.Item label="OS Axis">{selected.os_axis}°</Descriptions.Item>
            <Descriptions.Item label="OD ADD">{selected.od_add}</Descriptions.Item>
            <Descriptions.Item label="OS ADD">{selected.os_add}</Descriptions.Item>
            <Descriptions.Item label="PD">{selected.pd || '—'}</Descriptions.Item>
            <Descriptions.Item label="تحويل السالب↔الموجب">{selected.transposition_applied ? 'نعم' : 'لا'}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>

      {/* إنشاء وصفة - الوصفة أولاً، بيانات العميل اختيارية */}
      <Modal title="وصفة جديدة" open={createVisible} onCancel={() => setCreateVisible(false)} footer={null} width={720}>
        <Form form={createForm} layout="vertical" onFinish={handleCreate}>
          <Card size="small" title="العين اليمنى (OD)" style={{ marginBottom: 12 }}>
            <Row gutter={12}>
              <Col span={6}><Form.Item name="od_sph" label="SPH" rules={[{ required: true }]}><InputNumber step={0.25} style={{ width: '100%' }} /></Form.Item></Col>
              <Col span={6}><Form.Item name="od_cyl" label="CYL"><InputNumber step={0.25} style={{ width: '100%' }} /></Form.Item></Col>
              <Col span={6}><Form.Item name="od_axis" label="AXIS"><InputNumber step={1} min={0} max={180} style={{ width: '100%' }} /></Form.Item></Col>
              <Col span={6}><Form.Item name="od_add" label="ADD"><InputNumber step={0.25} min={0} max={5} style={{ width: '100%' }} /></Form.Item></Col>
            </Row>
          </Card>
          <Card size="small" title="العين اليسرى (OS)" style={{ marginBottom: 12 }}>
            <Row gutter={12}>
              <Col span={6}><Form.Item name="os_sph" label="SPH" rules={[{ required: true }]}><InputNumber step={0.25} style={{ width: '100%' }} /></Form.Item></Col>
              <Col span={6}><Form.Item name="os_cyl" label="CYL"><InputNumber step={0.25} style={{ width: '100%' }} /></Form.Item></Col>
              <Col span={6}><Form.Item name="os_axis" label="AXIS"><InputNumber step={1} min={0} max={180} style={{ width: '100%' }} /></Form.Item></Col>
              <Col span={6}><Form.Item name="os_add" label="ADD"><InputNumber step={0.25} min={0} max={5} style={{ width: '100%' }} /></Form.Item></Col>
            </Row>
          </Card>
          <Row gutter={12}>
            <Col span={6}><Form.Item name="pd" label="PD (اختياري)"><InputNumber step={0.5} min={40} max={80} style={{ width: '100%' }} /></Form.Item></Col>
          </Row>
          <Collapse ghost>
            <Panel header="بيانات العميل (اختياري)" key="cust">
              <Row gutter={16}>
                <Col span={12}><Form.Item name="customer_name" label="اسم العميل"><Input /></Form.Item></Col>
                <Col span={12}><Form.Item name="customer_phone" label="الهاتف"><Input /></Form.Item></Col>
              </Row>
              <Form.Item name="notes" label="ملاحظات"><Input.TextArea rows={2} /></Form.Item>
            </Panel>
          </Collapse>
          <Button type="primary" htmlType="submit" block loading={creating} style={{ marginTop: 8 }}>حفظ وبحث</Button>
        </Form>
      </Modal>

      {/* لوحة البحث السريع */}
      <Modal
        title={`بحث سريع${searchFor ? ` — وصفة #${searchFor.id}` : ''}`}
        open={searchVisible}
        onCancel={() => setSearchVisible(false)}
        footer={null}
        width={1180}
      >
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 'bold', marginBottom: 4 }}>نوع الاستخدام</div>
          <Radio.Group
            optionType="button"
            value={usageMode}
            disabled={searching}
            onChange={(e) => { setUsageMode(e.target.value); setSearchData(null); }}
            options={USE_MODE_OPTIONS}
          />
        </div>

        <div style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 'bold', marginBottom: 4 }}>احتياج العميل</div>
          <Select aria-label="احتياج العميل" style={{ width: '100%', maxWidth: 450 }}
            value={customerNeed} options={CUSTOMER_NEED_OPTIONS} disabled={searching}
            onChange={(value) => { setCustomerNeed(value); setSearchData(null); }} />
          <div style={{ color: '#666', marginTop: 6 }}>نوصي فقط بما يثبته الكتالوج. عند غياب دليل كافٍ لا نعرض اختياراً تخمينياً.</div>
        </div>

        <Collapse ghost style={{ marginBottom: 12 }}>
          <Panel header="خيارات متقدمة: تقنية إضافية" key="technology">
          <div style={{ fontWeight: 'bold', marginBottom: 4 }}>التكنولوجيا المطلوبة</div>
          <Radio.Group
            optionType="button"
            value={technologyIntent}
            disabled={searching}
            onChange={(e) => { setTechnologyIntent(e.target.value); setSearchData(null); }}
            options={TECHNOLOGY_OPTIONS}
          />
          </Panel>
        </Collapse>

        <Radio.Group value={mode} onChange={(e) => setMode(e.target.value)} style={{ marginBottom: 12 }}>
          <Radio value="automatic">بحث تلقائي</Radio>
          <Radio value="targeted">مرشحات متقدمة</Radio>
        </Radio.Group>

        {mode === 'targeted' && (
          <Card size="small" style={{ marginBottom: 12 }}>
            <Row gutter={[12, 8]}>
              <Col span={6}>
                <div>الشركة</div>
                <Select allowClear style={{ width: '100%' }} placeholder="الكل" value={filters.company_id}
                  onChange={onCompanyChange} options={companies.map((c) => ({ value: c.id, label: c.name }))} />
              </Col>
              <Col span={6}>
                <div>المنتج / الموديل</div>
                <Select allowClear showSearch optionFilterProp="label" style={{ width: '100%' }} placeholder="الكل"
                  value={filters.lens_model_id}
                  onChange={onModelChange}
                  options={withSelected(
                    facets.lens_models.map((m) => ({ value: m.id, label: m.name })),
                    filters.lens_model_id,
                    modelNameById[filters.lens_model_id] || `#${filters.lens_model_id}`,
                  )} />
              </Col>
              <Col span={3}>
                <div>Index</div>
                <Select allowClear showSearch style={{ width: '100%' }} placeholder="الكل"
                  value={filters.index_value}
                  onChange={onFilterFieldChange('index_value')}
                  options={withSelected(facets.index_value.map((v) => ({ value: v, label: String(v) })), filters.index_value, String(filters.index_value))} />
              </Col>
              <Col span={5}>
                <div>الفئة</div>
                <Select allowClear style={{ width: '100%' }} placeholder="الكل" value={filters.category}
                  onChange={onFilterFieldChange('category')}
                  options={withSelected(
                    facets.category.map((v) => ({ value: v, label: CATEGORY_LABELS[v] || v })),
                    filters.category, CATEGORY_LABELS[filters.category] || filters.category,
                  )} />
              </Col>
              <Col span={4}>
                <div>السعر الأقصى</div>
                <InputNumber style={{ width: '100%' }} placeholder="الكل"
                  value={filters.max_price} onChange={(v) => setFilters((f) => ({ ...f, max_price: v }))} />
              </Col>
              <Col span={6}>
                <div>التصميم / design_variant</div>
                <Select allowClear showSearch optionFilterProp="label" style={{ width: '100%' }} placeholder="الكل"
                  value={filters.design_variant}
                  onChange={onFilterFieldChange('design_variant')}
                  options={withSelected(facets.design_variant.map((v) => ({ value: v, label: v })), filters.design_variant, filters.design_variant)} />
              </Col>
              <Col span={6}>
                <div>الطلاء</div>
                <Select allowClear showSearch optionFilterProp="label" style={{ width: '100%' }} placeholder="الكل"
                  value={filters.coating}
                  onChange={onFilterFieldChange('coating')}
                  options={withSelected(facets.coating.map((c) => ({ value: c.code, label: c.name_ar || c.name })), filters.coating, filters.coating)} />
              </Col>
              <Col span={6}>
                <div>اللون / color_variant</div>
                <Select allowClear showSearch optionFilterProp="label" style={{ width: '100%' }} placeholder="الكل"
                  value={filters.color_variant}
                  onChange={onFilterFieldChange('color_variant')}
                  options={withSelected(facets.color_variant.map((v) => ({ value: v, label: v })), filters.color_variant, filters.color_variant)} />
              </Col>
              <Col span={6}>
                <div>التقنية / treatment_band</div>
                <Select allowClear showSearch optionFilterProp="label" style={{ width: '100%' }} placeholder="الكل"
                  value={filters.treatment_band}
                  onChange={onFilterFieldChange('treatment_band')}
                  options={withSelected(facets.treatment_band.map((v) => ({ value: v, label: v })), filters.treatment_band, filters.treatment_band)} />
              </Col>
              <Col span={3}>
                <div>التوفر</div>
                <Select style={{ width: '100%' }} value={filters.availability || 'both'}
                  onChange={onFilterFieldChange('availability')}
                  options={[{ value: 'both', label: 'الكل' }, { value: 'stock', label: 'STOCK' }, { value: 'rx', label: 'RX' }]} />
              </Col>
              <Col span={3}>
                <div>السوق</div>
                <Select style={{ width: '100%' }} value={filters.market_scope || 'all'}
                  onChange={onFilterFieldChange('market_scope')}
                  options={[{ value: 'all', label: 'الكل' }, { value: 'Egypt', label: 'Egypt' }, { value: 'Out Of Egypt', label: 'Out Of Egypt' }]} />
              </Col>
            </Row>
            <div style={{ marginTop: 8, color: '#888', fontSize: 12 }}>
              كل المرشحات تُطبَّق معاً (AND) ولا يتم تجاوز أي منها تلقائياً. كل حقل اختياري ومستقل — لا يلزم اختيار المنتج أولاً. اختيار أي حقل يُحدّث خيارات باقي الحقول فقط، ولا يحذف أي اختيار سابق تلقائياً؛ حتى لو أصبح المزيج غير متاح، يبقى اختيارك ظاهراً (⚠️) والبحث سيُظهر بدقة أنه غير متاح بهذه المواصفات. لا يُحذف اختيار تلقائياً إلا عند تغيير الشركة أو المنتج نفسه إن كانت القيمة السابقة لا تنتمي إطلاقاً للكيان الجديد.
            </div>
          </Card>
        )}

        <Button type="primary" onClick={() => runSearch(searchFor, mode, mode === 'targeted' ? buildFilterPayload() : undefined)} loading={searching}>
          بحث
        </Button>

        {searching && <div style={{ padding: 32, textAlign: 'center' }}>جاري البحث...</div>}

        {!searching && sd && (
          <div style={{ marginTop: 16 }}>
            <Alert
              type={ANSWER_TYPE[sd.availability_answer.code] || 'info'}
              showIcon
              message={sd.availability_answer.title}
              description={sd.availability_answer.detail}
              style={{ marginBottom: 12 }}
            />
            {sd.derived_search_rx && (
              <Card size="small" title="قوة القراءة المستخدمة في البحث" style={{ marginBottom: 12, borderColor: '#1677ff' }}>
                <div style={{ display: 'flex', gap: 24 }}>
                  <div>OD: {sd.derived_search_rx.od_sph} / {sd.derived_search_rx.od_cyl} x {sd.derived_search_rx.od_axis}</div>
                  <div>OS: {sd.derived_search_rx.os_sph} / {sd.derived_search_rx.os_cyl} x {sd.derived_search_rx.os_axis}</div>
                </div>
                <div style={{ color: '#888', fontSize: 12, marginTop: 4 }}>
                  محسوبة تلقائياً من وصفة الأبعد + ADD — الوصفة الأصلية المحفوظة لم تتغيّر.
                </div>
              </Card>
            )}
            {sd.use_mode === 'bifocal' || sd.use_mode === 'progressive' ? (
              <div style={{ color: '#888', fontSize: 12, marginBottom: 12 }}>
                البحث يستخدم وصفة الأبعد (Distance) + ADD كما هي، بدون تحويل لقوة قراءة.
              </div>
            ) : null}
            <Descriptions size="small" column={5} bordered style={{ marginBottom: 12 }}>
              <Descriptions.Item label="خيارات الزوج"><span style={{ whiteSpace: 'nowrap' }}>{sd.exact_total}</span></Descriptions.Item>
              <Descriptions.Item label="زوج STOCK مصر"><span style={{ whiteSpace: 'nowrap' }}>{sd.stock_egypt_count}</span></Descriptions.Item>
              <Descriptions.Item label="زوج STOCK خارج مصر"><span style={{ whiteSpace: 'nowrap' }}>{sd.stock_out_of_egypt_count}</span></Descriptions.Item>
              <Descriptions.Item label="زوج STOCK — سوق غير محدد"><span style={{ whiteSpace: 'nowrap' }}>{sd.stock_market_unknown_count}</span></Descriptions.Item>
              <Descriptions.Item label="زوج RX"><span style={{ whiteSpace: 'nowrap' }}>{sd.rx_count}</span></Descriptions.Item>
              <Descriptions.Item label="مقسّم / غير متوفر"><span style={{ whiteSpace: 'nowrap' }}>{sd.split_count}</span></Descriptions.Item>
              <Descriptions.Item label="توصية Index" span={3}>{sd.index_recommendation}</Descriptions.Item>
              <Descriptions.Item label="توصية Aspherical" span={2}>{sd.aspherical_recommendation}</Descriptions.Item>
            </Descriptions>

            {bestIsActionable && (
              <Card size="small" title="⭐ أفضل خيار للزوج" style={{ marginBottom: 12, borderColor: '#52c41a', borderWidth: 2 }}>
                {renderResultCard(best)}
              </Card>
            )}

            {!bestIsActionable && sd.exact_total > 0 && (
              <Alert type="warning" showIcon style={{ marginBottom: 12 }}
                message="لا توجد توصية تستوفي التوفر المثبت والسعر النهائي؛ راجع التفاصيل أدناه." />
            )}
            {(sd.seller_alternatives || []).filter(isActionableBestMatch).map((r, i) => (
              <Card key={`seller-${rowKey(r)}`} size="small" title={`بديل ${i + 1} — يحقق نفس الاحتياج`}
                style={{ marginBottom: 12, borderColor: '#1677ff' }}>
                {renderResultCard(r)}
              </Card>
            ))}
            {bestIsActionable && (sd.seller_alternatives || []).length < 2 && (
              <div style={{ color: '#666', marginBottom: 12 }}>لا يوجد بديلان إضافيان يستوفيان جميع الشروط في الكتالوج الحالي.</div>
            )}
            {sd.exact_total === 0 && <Empty description="لا توجد نتيجة مطابقة تماماً" />}

            <Collapse activeKey={activePanelKeys} onChange={setActivePanelKeys}>
              {sd.groups.map((grp) => (
                <Panel
                  key={grp.key}
                  header={
                    <span>
                      {grp.label} <Tag>{grp.count}</Tag>
                      <span style={{ color: '#888', fontSize: 12, marginRight: 8 }}>{grp.catalog_note}</span>
                    </span>
                  }
                >
                  {grp.count === 0 ? (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="لا شيء في هذه المجموعة" />
                  ) : (
                    <>
                      <Table
                        dataSource={grp.results}
                        columns={resultColumns}
                        rowKey={rowKey}
                        size="small"
                        pagination={grp.count > 15 ? { pageSize: 15 } : false}
                        scroll={{ x: 1280 }}
                        expandable={{
                          expandedRowRender: (r) => (
                            <Row gutter={16} style={{ padding: 8 }}>
                              <Col><PairMatrix od={r.od} os={r.os} /></Col>
                              <Col flex="auto"><PairAnswer pf={r.pair_fulfillment} /></Col>
                            </Row>
                          ),
                        }}
                      />
                    </>
                  )}
                </Panel>
              ))}
            </Collapse>

            {sd.availability_intelligence && sd.availability_intelligence.length > 0 && (
              <>
                <Divider />
                <h3>توفر نفس المنتج (خارج المطلوب)</h3>
                <Alert type="warning" showIcon style={{ marginBottom: 12 }}
                  message={sd.availability_intelligence_note
                    || 'نفس المنتج المطلوب متاح خارج التوفر/السوق/السعر المطلوب — ليس نتيجة مطابقة.'} />
                {sd.availability_intelligence.map((r) => (
                  <Card key={`intel-${rowKey(r)}`} size="small" style={{ marginBottom: 8, borderColor: '#faad14' }}>
                    {renderResultCard(r)}
                  </Card>
                ))}
              </>
            )}

            {sd.alternatives && sd.alternatives.length > 0 && (
              <>
                <Divider />
                <h3>أفضل البدائل</h3>
                <Alert type="info" showIcon style={{ marginBottom: 12 }}
                  message={sd.alternatives_note || 'بدائل مقترحة — ليست مطابقات تامة.'} />
                {sd.alternatives.map((a) => (
                  <Card key={a.result.source_pricing_id} size="small" style={{ marginBottom: 8 }}>
                    <Space wrap style={{ marginBottom: 6 }}>
                      <Tag color="blue">سبب الاقتراح: {a.proximity_reason}</Tag>
                      {a.relaxed_filters.map((rf) => <Tag color="volcano" key={rf}>مختلف: {rf}</Tag>)}
                    </Space>
                    {renderLensMatchCard(a.result)}
                  </Card>
                ))}
              </>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};

export default Prescriptions;
