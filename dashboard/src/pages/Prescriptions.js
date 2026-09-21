import React, { useEffect, useState, useRef } from 'react';
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

// F4: alternatives (frozen-matcher LensMatchResult) carry raw `availability`
// ("stock"/"rx") + `market_scope` instead of the already-routed
// PairFulfillment.status primary results use. This mirrors
// backend product_search.market_is_egypt/_row_route EXACTLY on those SAME
// two fields - never derived from company/product name, never collapsing an
// unspecified/Out-Of-Egypt market into Egypt or into a generic "STOCK".
const marketIsEgypt = (marketScope) => {
  const s = (marketScope || '').toString().trim().toLowerCase();
  if (!s) return null;
  if (s.includes('out') && s.includes('egypt')) return false;
  if (['egypt', 'eg', 'مصر'].includes(s)) return true;
  if (s.includes('egypt')) return true;
  return false;
};
const alternativeRoute = (r) => {
  if (r.availability === 'stock') {
    const eg = marketIsEgypt(r.market_scope);
    if (eg === true) return 'stock_egypt';
    if (eg === false) return 'stock_outside';
    return 'stock_market_unknown';
  }
  return 'rx';
};

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

export const priceNeedsConfirmation = (pf) => Boolean(
  pf.price_confirmation_note || pf.needs_review
  || pf.technology_addon?.unit_status === 'UNIT_UNRESOLVED'
  || !['stock_egypt', 'stock_outside', 'stock_market_unknown', 'rx'].includes(pf.status)
  || pf.provenance !== 'single_route' || pf.price_pair == null || !Number.isFinite(Number(pf.price_pair)) || Number(pf.price_pair) <= 0
);

// Confirmed-price badge: restrained gold, amount is the strongest element -
// visually on par with the existing availability Tags, never neon/bright.
// Distinct from the pale price_confirmation_note warning box below (#fffbe6/
// #ffe58f) so a confirmed price can never be mistaken for a pending one.
const PAIR_PRICE_BADGE_STYLE = {
  display: 'inline-flex', alignItems: 'baseline', gap: 4,
  background: '#FFEB3B', border: '1px solid #E6C900', borderRadius: 6,
  padding: '1px 10px', color: '#3D3300',
};

export const PairPrice = ({ pf }) => {
  const pending = priceNeedsConfirmation(pf);
  const base = pf.technology_addon?.base_price ?? pf.price_pair;
  return pending ? <div>
    <b style={{ color: '#ad6800' }}>بانتظار تأكيد السعر</b>
    {base != null && <div style={{ fontSize: 12 }}>السعر الأساسي: {base} {pf.currency} / Pair — السعر النهائي غير مؤكد</div>}
    <div style={{ fontSize: 12 }}>{pf.price_confirmation_note || (pf.needs_review ? 'بحاجة لمراجعة قبل اعتماد السعر' : 'لا يوجد سعر نهائي مؤكد')}</div>
  </div> : <div>
    <span style={{ color: '#595959' }}>سعر الزوج النهائي: </span>
    <span className="pair-price-confirmed" style={PAIR_PRICE_BADGE_STYLE}>
      <b style={{ fontSize: 16 }}>{pf.price_pair}</b> {pf.currency} / Pair
    </span>
  </div>;
};

export const sellerNeedPayload = (needs) => ({ customer_needs: needs });

export const ManufacturerCoverage = ({ groups = [] }) => {
  const coverage = new Map();
  groups.forEach((group) => group.results.forEach((result) => {
    const name = result.company_name;
    const entry = coverage.get(name) || { count: 0, actionable: 0 };
    entry.count += 1;
    if (isActionableBestMatch(result)) entry.actionable += 1;
    coverage.set(name, entry);
  }));
  if (!coverage.size) return null;
  return <div style={{ marginBottom: 12 }} aria-label="نتائج مطابقة أخرى">
    <b>نتائج مطابقة أخرى</b>
    <div style={{ marginTop: 6 }}>{Array.from(coverage, ([name, entry]) => (
      <Tag key={name} color={entry.actionable ? 'blue' : 'orange'}>
        {name} {entry.count}{!entry.actionable ? ' — يحتاج تأكيد' : ''}
      </Tag>
    ))}</div>
  </div>;
};

export const sellerHeadline = (data) => {
  if (isActionableBestMatch(data.best_match)) {
    const status = data.best_match.pair_fulfillment.status;
    return { code: status === 'stock_outside' ? 'stock_out_of_egypt' : status === 'rx' ? 'rx_only' : status,
      title: `الخيار الموصى به: ${data.best_match.manufacturing_location === 'egypt' && status === 'rx' ? 'تصنيع داخل مصر' : PAIR_STATUS_AR[status]}`, detail: 'سعر الزوج النهائي مؤكد؛ التوفر حسب الكتالوج.' };
  }
  if (data.exact_total > 0 || data.availability_intelligence?.length) {
    return { code: 'pending', title: 'يوجد خيار يحتاج تأكيد — لا توجد توصية جاهزة بسعر نهائي',
      detail: data.availability_answer.title };
  }
  return data.availability_answer;
};

// "أفضل حل موحد للزوج" + a pair price only when provenance is proven (§4/§8/§2).
export const PairAnswer = ({ pf, manufacturingLocation }) => {
  return (
    <div>
      <div>
        <b>أفضل حل موحد للزوج: </b>
        <Tag color={PAIR_STATUS_COLOR[pf.status]}>{manufacturingLocation === 'egypt' && pf.status === 'rx' ? 'تصنيع داخل مصر' : PAIR_STATUS_AR[pf.status] || pf.status}</Tag>
        {(pf.status === 'stock_egypt' || pf.status === 'stock_outside' || pf.status === 'stock_market_unknown') &&
          <span style={{ color: '#888', fontSize: 12 }}>— حسب الكتالوج</span>}
        {pf.needs_review && <Tag color="volcano" style={{ marginRight: 6 }}>بحاجة لمراجعة</Tag>}
      </div>
      <PairPrice pf={pf} />
      {/* An unresolved surcharge unit must never display a computed total. */}
      {pf.technology_addon && (
        <div style={{ marginTop: 4, color: '#0958d9', fontSize: 12, background: '#e6f4ff',
                     border: '1px solid #91caff', borderRadius: 4, padding: '4px 8px' }}>
          ℹ️ إضافة لتوفير التكنولوجيا المطلوبة —
          الأساس {pf.technology_addon.base_price} {pf.currency}؛ {pf.technology_addon.label} {pf.technology_addon.addon_price} {pf.currency}
          {priceNeedsConfirmation(pf)
            ? (pf.technology_addon.unit_status === 'UNIT_UNRESOLVED'
              ? ' — وحدة الإضافة بانتظار التأكيد؛ السعر النهائي غير مؤكد' : ' — السعر النهائي غير مؤكد')
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
<details style={{ marginTop: 4, fontSize: 12 }}><summary>تفاصيل التوفر</summary>{pf.reason}</details>
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
  anti_fatigue: 'Anti-Fatigue',
  myopia_control: 'Myopia Control',
};

const ANSWER_TYPE = {
  stock_egypt: 'success', stock_out_of_egypt: 'warning', stock_market_unknown: 'warning',
  rx_only: 'warning', split: 'warning', none: 'error', validation_error: 'error',
};

// V1.2 core-workflow: customer-facing use-mode / technology-intent labels.
// Values sent to the backend are the canonical English tokens (see
// backend/app/technology_evidence.py); labels are Arabic display text only.
//
// Special Lenses (owner-confirmed, 2026-09-19): the seller-facing top level
// is exactly Single Vision / Bifocal / Progressive / Special Lenses - no
// subtype (Occupational/Office, Young/Anti-Fatigue, Myopia Control, ...) is
// ever an independent top-level peer; each is an entry in
// SPECIAL_SUBTYPE_OPTIONS below. 'special' is a pure UI grouping value - it
// is NEVER sent to the backend; selecting a subtype always sends that
// subtype's own already-working use_mode. A future catalog-proven subtype is
// one more entry in SPECIAL_SUBTYPE_OPTIONS, never a form redesign.
const TOP_LEVEL_USE_MODE_OPTIONS = [
  { value: 'distance', label: 'مسافات' },
  { value: 'reading', label: 'قراءة — عدسة أحادية' },
  { value: 'bifocal', label: 'Bifocal' },
  { value: 'progressive', label: 'Progressive' },
  { value: 'special', label: 'Special Lenses' },
];
const SPECIAL_SUBTYPE_OPTIONS = [
  { value: 'office', label: 'Occupational / Office' },
  { value: 'anti_fatigue', label: 'Young / Anti-Fatigue' },
  { value: 'myopia_control', label: 'Myopia Control' },
];
const SPECIAL_SUBTYPE_VALUES = SPECIAL_SUBTYPE_OPTIONS.map((o) => o.value);
const CUSTOMER_NEED_OPTIONS = [
  { value: 'blue_light', label: 'حماية من الضوء الأزرق' },
  { value: 'photo_gray', label: 'Photo Gray' },
  { value: 'photo_brown', label: 'Photo Brown' },
  { value: 'impact_resistant', label: 'مقاومة للكسر' },
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
  && !priceNeedsConfirmation(best.pair_fulfillment)
);

const EMPTY_FACETS = { lens_models: [], index_value: [], category: [], design_variant: [], coating: [], color_variant: [], treatment_band: [] };

// Maps PairFulfillment.status to a tier rank for sellerRowOrder below -
// mirrors backend product_search._STATUS_ORDER/_order_key exactly, so the
// frontend never re-derives its own notion of availability priority.
const _STATUS_TIER = { stock_egypt: 0, stock_outside: 1, stock_market_unknown: 2, rx: 3,
  split: 4, eligibility_unknown: 5, unavailable: 5 };

// Single central presentation-order rule for every seller results section:
// availability tier, then refractive index ascending (HAT-01, owner-approved
// 2026-09-21 - groups same-index options together so the seller scans one
// index band at a time instead of prices jumping between indices), then the
// confirmed final pair price ascending within that index (a pending/
// unconfirmed price never outranks a proven one), then match_score as the
// tiebreak - independent of selected needs. This supersedes the earlier
// price-only rule (which existed to fix a DIFFERENT bug: index being used as
// the ONLY/primary key and fragmenting one tier into disconnected per-index
// price runs) - index is now the intentional, approved primary grouping, with
// price still strictly ascending inside each index group. A missing/
// unparseable index is never allowed to jump ahead of a known one - it always
// sorts after every row with a real index.
export const sellerRowOrder = (a, b) => {
  const tier = (_STATUS_TIER[a.pair_fulfillment.status] ?? 3) - (_STATUS_TIER[b.pair_fulfillment.status] ?? 3);
  if (tier) return tier;
  const aIndex = Number(a.index_value);
  const bIndex = Number(b.index_value);
  const aIndexValid = Number.isFinite(aIndex);
  const bIndexValid = Number.isFinite(bIndex);
  if (aIndexValid !== bIndexValid) return aIndexValid ? -1 : 1;
  if (aIndexValid && aIndex !== bIndex) return aIndex - bIndex;
  const pendingA = priceNeedsConfirmation(a.pair_fulfillment);
  const pendingB = priceNeedsConfirmation(b.pair_fulfillment);
  if (pendingA !== pendingB) return pendingA ? 1 : -1;
  if (!pendingA) {
    const price = Number(a.pair_fulfillment.price_pair) - Number(b.pair_fulfillment.price_pair);
    if (price) return price;
  }
  const score = Number(b.match_score) - Number(a.match_score);
  if (score) return score;
  const identity = (r) => `${r.company_name}|${r.lens_model_id}|${r.variant_id}|${r.coating_id}|${r.pair_fulfillment.source_pricing_ids?.join(',')}`;
  return identity(a).localeCompare(identity(b));
};

export const sellerSections = (data) => {
  // Special Lenses subtypes (office/anti_fatigue/myopia_control, 2026-09-19)
  // are each proven RX-only just like bifocal/progressive - see
  // app/catalog_corrections.py OCCUPATIONAL_OFFICE_MODELS/
  // ANTI_FATIGUE_MODELS/MYOPIA_CONTROL_MODELS.
  const multi = ['progressive', 'bifocal', 'office', 'anti_fatigue', 'myopia_control'].includes(data.use_mode);
  const groups = data.groups || [];
  const labels = { stock_egypt: 'STOCK داخل مصر', stock_out_of_egypt: 'STOCK خارج مصر',
    rx: 'RX / تصنيع', stock_market_unknown: 'STOCK — مكان التوفر غير محدد' };
  const order = multi ? ['rx', 'stock_egypt', 'stock_out_of_egypt', 'stock_market_unknown']
    : ['stock_egypt', 'stock_out_of_egypt', 'rx', 'stock_market_unknown'];
  const keys = [...order, ...groups.map((g) => g.key).filter((key) => !order.includes(key))];
  return keys.map((key) => {
    const group = groups.find((g) => g.key === key);
    const results = [...(group?.results || [])].sort(sellerRowOrder);
    const section = { key, label: labels[key] || group?.label, results };
    if (multi && key === 'rx') {
      section.tiers = [
        { key: 'local', label: 'تصنيع داخل مصر', results: results.filter((r) => r.manufacturing_location === 'egypt') },
        { key: 'other', label: 'باقي خيارات RX / التصنيع', results: results.filter((r) => r.manufacturing_location !== 'egypt') },
      ];
    }
    return section;
  }).filter((section) => section.results.length || (multi ? section.key === 'rx'
    : ['stock_egypt', 'stock_out_of_egypt'].includes(section.key)));
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
  // V1.2 core-workflow: what the customer wants made (distance/reading/
  // bifocal/progressive) and a manufacturer-agnostic technology need. Both
  // are independent of `mode` (automatic vs targeted) below - the employee
  // still enters the doctor's prescription only once and never computes a
  // Reading power or a manufacturer's own technology naming by hand.
  const [usageMode, setUsageMode] = useState('distance');
  const [customerNeeds, setCustomerNeeds] = useState([]);
  const searchVersion = useRef(0);
  const [editing, setEditing] = useState(null);
  // F5: explicit "criteria changed - search again" notice. Only ever shown
  // after a search has genuinely completed at least once for the CURRENT
  // prescription/session (hasSearchedRef) - never on the initial, not-yet-
  // searched state, so it is never inferred from searchData===null alone.
  const [resultsStale, setResultsStale] = useState(false);
  const hasSearchedRef = useRef(false);
  const invalidateSearch = () => {
    searchVersion.current += 1;
    if (hasSearchedRef.current) setResultsStale(true);
    setSearchData(null);
    setSearching(false);
  };
  const changeCriteria = (setter, value) => { invalidateSearch(); setter(value); };
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
        od: { sph: values.od_sph, cyl: values.od_cyl ?? 0, axis: values.od_axis ?? null, add: values.od_add ?? null },
        os: { sph: values.os_sph, cyl: values.os_cyl ?? 0, axis: values.os_axis ?? null, add: values.os_add ?? null },
      };
      const res = editing ? await prescriptionAPI.update(editing.id, payload) : await prescriptionAPI.create(payload);
      message.success(editing ? 'تم حفظ الوصفة الأصلية — اضغط بحث لتحديث النتائج' : 'تم إنشاء الوصفة');
      setCreateVisible(false);
      createForm.resetFields();
      await loadPrescriptions();
      if (editing) {
        invalidateSearch();
        setSearchFor(res.data);
        setSearchVisible(true);
        setEditing(null);
      } else openSearch(res.data);
    } catch (error) {
      message.error(errMsg(error, 'فشل إنشاء الوصفة'));
    } finally {
      setCreating(false);
    }
  };

  const openEdit = (record) => {
    invalidateSearch();
    setEditing(record);
    const fields = { customer_name: record.customer_name, customer_phone: record.customer_phone,
      pd: record.pd, notes: record.notes };
    ['od', 'os'].forEach((eye) => {
      ['sph', 'cyl', 'axis'].forEach((field) => {
        fields[`${eye}_${field}`] = record[`${eye}_${field}_original`];
      });
      fields[`${eye}_add`] = record[`${eye}_add`];
    });
    createForm.setFieldsValue(fields);
    setCreateVisible(true);
  };

  const openSearch = (record) => {
    setSearchFor(record);
    setSearchData(null);
    setResultsStale(false);
    hasSearchedRef.current = false;
    setMode('automatic');
    setUsageMode('distance');
    setCustomerNeeds([]);
    setFilters({});
    setFacets(EMPTY_FACETS);
    setModelNameById({});
    setSearchVisible(true);
    // Explicit defaults avoid stale use/need from a previous prescription.
    // (same lesson as the P1 Collapse fix: this Modal instance persists across
    // openSearch calls, so a closure-read of current state here could be stale).
    runSearch(record, 'automatic', {}, 'distance', []);
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
    invalidateSearch();
    const version = searchVersion.current;
    let next = { ...filters, company_id: companyId };
    setFilters(next);
    if (companyId) {
      next = await clearIdentityInvalidChildren({ company_id: companyId }, next, { checkProduct: true });
    }
    if (version !== searchVersion.current) return;
    setFilters(next);
    refreshFacetOptions(next);
  };

  const onModelChange = async (modelId) => {
    invalidateSearch();
    const version = searchVersion.current;
    let next = { ...filters, lens_model_id: modelId };
    setFilters(next);
    if (modelId) {
      next = await clearIdentityInvalidChildren({ company_id: filters.company_id, lens_model_id: modelId }, next, { checkProduct: false });
    }
    if (version !== searchVersion.current) return;
    setFilters(next);
    refreshFacetOptions(next);
  };

  // Every other catalog-driven field: set the value and refresh what the OTHER
  // dropdowns offer next - never clear any sibling filter. No fixed order.
  const onFilterFieldChange = (key) => (value) => {
    invalidateSearch();
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

  const runSearch = async (record, useMode, rawFilters, usageModeOverride, needOverride) => {
    const m = useMode ?? mode;
    const um = usageModeOverride !== undefined ? usageModeOverride : usageMode;
    const version = ++searchVersion.current;
    setSearching(true);
    setSearchData(null);
    try {
      const payload = { mode: m, ...sellerNeedPayload(needOverride !== undefined ? needOverride : customerNeeds) };
      if (m === 'targeted') payload.filters = rawFilters ?? buildFilterPayload();
      if (um) payload.use_mode = um;
      const res = await prescriptionAPI.search(record.id, payload);
      if (version === searchVersion.current) {
        setSearchData(res.data);
        hasSearchedRef.current = true;
        setResultsStale(false);
      }
    } catch (error) {
      if (version === searchVersion.current) message.error(errMsg(error, 'فشل البحث'));
    } finally {
      if (version === searchVersion.current) setSearching(false);
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
    { title: 'الشركة', key: 'company', width: 115, render: (_, r) => r.company_name || '—' },
    { title: 'المنتج / الموديل', key: 'model', width: 185, render: (_, r) => <div>
      {isPrimaryRow(r) && <Tag color="blue" style={{ marginBottom: 2 }}>الخيار المقترح</Tag>}
      <div>{r.model_name || '—'}</div>
      <div style={{ fontSize: 12, color: '#666' }}>{r.design_variant}</div>
    </div> },
    { title: 'المادة / Index', key: 'idx', width: 145, render: (_, r) => indexMaterialText(r.material, r.index_value) },
    { title: 'التقنية / الطلاء', key: 'tech', width: 200, render: (_, r) => [r.coating_name || r.coating_code, r.treatment_band, r.color_variant].filter(Boolean).join(' / ') || '—' },
    { title: 'التوفر / التصنيع', key: 'pair', width: 160, render: (_, r) => <Tag color={PAIR_STATUS_COLOR[r.pair_fulfillment.status]}>{r.manufacturing_location === 'egypt' && r.pair_fulfillment.status === 'rx' ? 'تصنيع داخل مصر' : PAIR_STATUS_AR[r.pair_fulfillment.status]}</Tag> },
    { title: 'سعر الزوج', key: 'price', width: 240, render: (_, r) => <PairPrice pf={r.pair_fulfillment} /> },
  ];

  const renderSellerTable = (section) => <div>
    <ManufacturerCoverage groups={[section]} />
    <Table dataSource={section.results} columns={resultColumns} rowKey={rowKey} size="small"
      pagination={section.results.length > 15 ? { pageSize: 15, showSizeChanger: false } : false}
      scroll={{ x: 1080 }}
      expandable={{ expandedRowRender: (r) => <div>
        <div>الفئة: {r.category} — الدرجة: {r.match_score?.toFixed(1)}</div>
        <PairMatrix od={r.od} os={r.os} />
        <PairAnswer pf={r.pair_fulfillment} manufacturingLocation={r.manufacturing_location} />
        <details><summary>تفاصيل الكتالوج والتوافق</summary>{r.reason}</details>
      </div> }} />
  </div>;

  const rowKey = (r) => `${r.lens_model_id}-${r.variant_id}-${r.coating_id}`;

  const renderResultCard = (r) => (
    <>
      <b>{r.company_name} — {r.model_name}</b>
      {r.seller_recommendation_reason && <div>متوافق مع وصفة العينين والاحتياج المحدد</div>}
      <PairAnswer pf={r.pair_fulfillment} manufacturingLocation={r.manufacturing_location} />
      <Collapse ghost><Panel header="تفاصيل العدسة والتوافق" key="details">
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
      </Row>
      </Panel></Collapse>
    </>
  );

  // ---- alternatives still carry a frozen-matcher LensMatchResult ----
  // F4/F7: primary line (identity + pair price + full 4-tier availability,
  // same PAIR_STATUS_AR/PAIR_STATUS_COLOR language as primary results) stays
  // immediately visible; secondary technical fields move into the same
  // Collapse/Panel pattern already used by renderResultCard above. No field
  // is removed - every value below still renders, only its visual priority
  // changed. The alternative's own proposal reason/relaxed-filter tags are
  // unchanged (rendered by the caller, outside this function).
  const renderLensMatchCard = (r) => {
    const route = alternativeRoute(r);
    return (
      <div>
        <div>
          <b>{r.lens_model?.company?.name || '—'} — {r.lens_model?.name}</b>{' '}
          <Tag color={PAIR_STATUS_COLOR[route]}>{PAIR_STATUS_AR[route]}</Tag>
        </div>
        <div><b>سعر الزوج: </b>{r.price_pair} {r.currency} / Pair</div>
        <Collapse ghost><Panel header="تفاصيل العدسة والتوافق" key="details">
          <Descriptions size="small" column={3} bordered>
            <Descriptions.Item label="المادة / Index">{indexMaterialText(r.variant?.material, r.variant?.index_value)}</Descriptions.Item>
            <Descriptions.Item label="الفئة">{r.lens_model?.category}</Descriptions.Item>
            <Descriptions.Item label="التصميم">{r.design_variant || r.variant?.design_variant || '—'}</Descriptions.Item>
            <Descriptions.Item label="الطلاء">{r.coating_name || r.coating_code || '—'}</Descriptions.Item>
            <Descriptions.Item label="التقنية / اللون">{r.color_variant || r.variant?.color_variant || '—'}</Descriptions.Item>
            <Descriptions.Item label="السوق">{r.market_scope || '—'}</Descriptions.Item>
            <Descriptions.Item label="الدرجة">{r.match_score?.toFixed(1)}</Descriptions.Item>
            <Descriptions.Item label="السبب" span={2}>{r.reason}</Descriptions.Item>
          </Descriptions>
        </Panel></Collapse>
      </div>
    );
  };

  const sd = searchData;
  const headline = sd ? sellerHeadline(sd) : null;
  // F3: identifies the SAME row the backend already proved as `best_match`
  // (ACTIONABLE_PAIR_STATUSES + proven single-route price - isActionableBestMatch),
  // by its exact pricing-row identity, so at most one row across every
  // rendered table ever receives the visual cue - never a new ranking, never
  // applied to alternatives/availability-intelligence/unverified tables.
  const isPrimaryRow = (r) => {
    if (!sd || !isActionableBestMatch(sd.best_match)) return false;
    const ids = sd.best_match.pair_fulfillment.source_pricing_ids;
    const rowIds = r?.pair_fulfillment?.source_pricing_ids;
    return !!ids?.length && !!rowIds?.length && ids.join(',') === rowIds.join(',');
  };

  return (
    <div>
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>📝 الوصفات الطبية</h1>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); createForm.resetFields(); setCreateVisible(true); }}>وصفة جديدة</Button>
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
            <Descriptions.Item label="OD ADD">{selected.od_add ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="OS ADD">{selected.os_add ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="PD">{selected.pd || '—'}</Descriptions.Item>
            <Descriptions.Item label="تحويل السالب↔الموجب">{selected.transposition_applied ? 'نعم' : 'لا'}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>

      {/* إنشاء وصفة - الوصفة أولاً، بيانات العميل اختيارية */}
      <Modal title={editing ? "تعديل الوصفة الأصلية" : "وصفة جديدة"} open={createVisible} onCancel={() => setCreateVisible(false)} footer={null} width={720}>
        <Form form={createForm} layout="vertical" onFinish={handleCreate}>
          <Card size="small" title="العين اليمنى (OD)" style={{ marginBottom: 12 }}>
            <Row gutter={12}>
              <Col span={6}><Form.Item name="od_sph" label="SPH" rules={[{ required: true }]}><InputNumber step={0.25} style={{ width: '100%' }} /></Form.Item></Col>
              <Col span={6}><Form.Item name="od_cyl" label="CYL"><InputNumber step={0.25} style={{ width: '100%' }} /></Form.Item></Col>
              <Col span={6}><Form.Item name="od_axis" label="AXIS" dependencies={['od_cyl']} rules={[({ getFieldValue }) => ({ validator(_, value) {
                return Number(getFieldValue('od_cyl') || 0) !== 0 && (value == null || value === '')
                  ? Promise.reject(new Error('أدخل AXIS لهذه العين عند وجود CYL غير صفر')) : Promise.resolve();
              } })]}><InputNumber step={1} min={0} max={180} style={{ width: '100%' }} /></Form.Item></Col>
              <Col span={6}><Form.Item name="od_add" label="ADD"><InputNumber step={0.25} min={0} max={5} style={{ width: '100%' }} /></Form.Item></Col>
            </Row>
          </Card>
          <Card size="small" title="العين اليسرى (OS)" style={{ marginBottom: 12 }}>
            <Row gutter={12}>
              <Col span={6}><Form.Item name="os_sph" label="SPH" rules={[{ required: true }]}><InputNumber step={0.25} style={{ width: '100%' }} /></Form.Item></Col>
              <Col span={6}><Form.Item name="os_cyl" label="CYL"><InputNumber step={0.25} style={{ width: '100%' }} /></Form.Item></Col>
              <Col span={6}><Form.Item name="os_axis" label="AXIS" dependencies={['os_cyl']} rules={[({ getFieldValue }) => ({ validator(_, value) {
                return Number(getFieldValue('os_cyl') || 0) !== 0 && (value == null || value === '')
                  ? Promise.reject(new Error('أدخل AXIS لهذه العين عند وجود CYL غير صفر')) : Promise.resolve();
              } })]}><InputNumber step={1} min={0} max={180} style={{ width: '100%' }} /></Form.Item></Col>
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
          <Button type="primary" htmlType="submit" block loading={creating} style={{ marginTop: 8 }}>{editing ? "حفظ التعديل" : "حفظ وبحث"}</Button>
        </Form>
      </Modal>

      {/* لوحة البحث السريع */}
      <Modal
        title={`بحث سريع${searchFor ? ` — وصفة #${searchFor.id}` : ''}`}
        open={searchVisible}
        onCancel={() => { invalidateSearch(); setSearchVisible(false); }}
        footer={null}
        width={1180}
      >
        {searchFor && <Card size="small" title="الوصفة الأصلية — قبل تحويل القراءة" style={{ marginBottom: 12 }}>
          {['od', 'os'].map((eye) => <div key={eye}>{eye.toUpperCase()}: SPH {searchFor[`${eye}_sph_original`]} / CYL {searchFor[`${eye}_cyl_original`]} × {searchFor[`${eye}_axis_original`]} — ADD {searchFor[`${eye}_add`] ?? '—'}</div>)}
          <Button onClick={() => openEdit(searchFor)}>تعديل الوصفة الأصلية</Button>
        </Card>}
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 'bold', marginBottom: 4 }}>نوع الاستخدام</div>
          <Radio.Group
            optionType="button"
            value={SPECIAL_SUBTYPE_VALUES.includes(usageMode) ? 'special' : usageMode}
            disabled={searching}
            onChange={(e) => changeCriteria(setUsageMode,
              e.target.value === 'special' ? SPECIAL_SUBTYPE_OPTIONS[0].value : e.target.value)}
            options={TOP_LEVEL_USE_MODE_OPTIONS}
          />
          {SPECIAL_SUBTYPE_VALUES.includes(usageMode) && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontWeight: 'bold', marginBottom: 4 }}>نوع العدسة الخاصة</div>
              <Radio.Group
                optionType="button"
                value={usageMode}
                disabled={searching}
                onChange={(e) => changeCriteria(setUsageMode, e.target.value)}
                options={SPECIAL_SUBTYPE_OPTIONS}
              />
            </div>
          )}
        </div>

        <div style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 'bold', marginBottom: 4 }}>احتياج العميل</div>
          <Space wrap role="group" aria-label="احتياج العميل">
            {CUSTOMER_NEED_OPTIONS.map(({ value, label }) => (
              <Button key={value} aria-pressed={customerNeeds.includes(value)}
                type={customerNeeds.includes(value) ? 'primary' : 'default'}
                onClick={() => changeCriteria(setCustomerNeeds, customerNeeds.includes(value)
                  ? customerNeeds.filter((need) => need !== value) : [...customerNeeds, value])}>
                {label}
              </Button>
            ))}
          </Space>
          <div style={{ color: '#666', marginTop: 6 }}>
            {customerNeeds.length ? 'يجب أن تحقق العدسة جميع الاحتياجات المحددة حسب الكتالوج.'
              : 'بدون احتياج إضافي — بدون شرط تكنولوجي، وليس شرط العدسة الشفافة فقط.'}
          </div>
        </div>

        <Radio.Group value={mode} onChange={(e) => changeCriteria(setMode, e.target.value)} style={{ marginBottom: 12 }}>
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
                  value={filters.max_price} onChange={onFilterFieldChange('max_price')} />
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

        {!searching && resultsStale && (
          <Alert type="info" showIcon style={{ marginTop: 12 }}
            message="تم تغيير معايير البحث. اضغط بحث لعرض النتائج المحدثة." />
        )}

        {searching && <div style={{ padding: 32, textAlign: 'center' }}>جاري البحث...</div>}

        {!searching && sd && (
          <div style={{ marginTop: 16 }}>
            {sd.exact_total === 0 && <Alert
              type={ANSWER_TYPE[headline.code] || 'warning'}
              showIcon
              message={headline.title}
              description={headline.detail}
              style={{ marginBottom: 12 }}
            />}
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
            <Collapse ghost><Panel header="إحصاءات البحث والتوصيات الفنية" key="stats">
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
            </Panel></Collapse>

            <div aria-label="نتائج العدسات المطابقة">
              <h3>نتائج العدسات المطابقة — {sd.exact_total} نتيجة</h3>
              {sellerSections(sd).map((section) => (
                <Card key={section.key} size="small" data-seller-section={section.key}
                  title={`${section.label} — ${section.results.length} نتيجة`} style={{ marginBottom: 16 }}>
                  {section.tiers ? <>
                    <ManufacturerCoverage groups={[section]} />
                    {section.tiers.map((tier) => <div key={tier.key} data-manufacturing-tier={tier.key}>
                      <h4>{tier.label} — {tier.results.length} نتيجة</h4>
                      {renderSellerTable(tier)}
                    </div>)}
                  </> : renderSellerTable(section)}
                </Card>
              ))}
            </div>

            {sd.stock_egypt_unverified && sd.stock_egypt_unverified.length > 0 && (
              <>
                <Divider />
                <h3>⚠️ STOCK داخل مصر — نطاق القوة غير مثبت — {sd.stock_egypt_unverified.length} نتيجة</h3>
                <Alert type="warning" showIcon style={{ marginBottom: 12 }}
                  message="متوفر Stock داخل مصر، لكن توافقه مع هذه الوصفة يحتاج تأكيد PowerRange"
                  description="هذه المنتجات ليست مطابقة للوصفة، وليست توصية قابلة للتنفيذ، وسعرها المعروض هو سعر الكتالوج فقط — وليس عرض سعر مؤكد لهذه الوصفة." />
                <ManufacturerCoverage groups={[{ results: sd.stock_egypt_unverified }]} />
                <Table
                  dataSource={sd.stock_egypt_unverified}
                  rowKey={rowKey}
                  size="small"
                  pagination={sd.stock_egypt_unverified.length > 15 ? { pageSize: 15, showSizeChanger: false } : false}
                  columns={[
                    { title: 'الشركة', key: 'company', width: 115, render: (_, r) => r.company_name || '—' },
                    { title: 'المنتج / الموديل', key: 'model', width: 185, render: (_, r) => r.model_name || '—' },
                    { title: 'المادة / Index', key: 'idx', width: 145, render: (_, r) => indexMaterialText(r.material, r.index_value) },
                    { title: 'التقنية / الطلاء', key: 'tech', width: 200, render: (_, r) => [r.coating_name || r.coating_code, r.treatment_band, r.color_variant].filter(Boolean).join(' / ') || '—' },
                    { title: 'سعر الكتالوج (معلوماتي فقط)', key: 'price', width: 200, render: (_, r) => (r.catalog_price_pair != null ? `${r.catalog_price_pair} ${r.currency} / Pair` : '—') },
                  ]}
                />
              </>
            )}

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
