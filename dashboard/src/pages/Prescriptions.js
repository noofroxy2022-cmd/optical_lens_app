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
const materialLabel = (variant) => {
  const m = (variant?.material || '').toString().trim();
  if (ORDINARY_MATERIAL.has(m.toLowerCase())) return null;
  return m;
};
const indexMaterialText = (variant) => {
  const idx = variant?.index_value;
  const idxTxt = idx != null ? `Index ${Number(idx).toFixed(2)}` : 'Index —';
  const mat = materialLabel(variant);
  return mat ? `${mat} · ${idxTxt}` : idxTxt;
};

const designText = (r) =>
  r.design_variant || r.variant?.design_variant ||
  (r.variant?.is_aspherical ? 'Aspherical' : r.variant?.design_type) || '—';

const CATEGORIES = [
  { value: 'single_vision', label: 'Single Vision' },
  { value: 'progressive', label: 'Progressive' },
  { value: 'bifocal', label: 'Bifocal' },
  { value: 'office', label: 'Office' },
  { value: 'digital', label: 'Digital' },
];

const ANSWER_TYPE = { stock_egypt: 'success', stock_out_of_egypt: 'warning', rx_only: 'warning', none: 'error' };

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
  const [mode, setMode] = useState('automatic');
  const [companies, setCompanies] = useState([]);
  const [models, setModels] = useState([]);
  const [filters, setFilters] = useState({});

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
    setFilters({});
    setModels([]);
    setSearchVisible(true);
    runSearch(record, 'automatic', {});
  };

  const onCompanyChange = async (companyId) => {
    setFilters((f) => ({ ...f, company_id: companyId, lens_model_id: undefined }));
    setModels([]);
    if (companyId) {
      try {
        // fetch all active models and narrow client-side (avoids the query-param
        // path on GET /lens-models/); backend is not touched.
        const r = await lensModelAPI.getAll();
        setModels((r.data || []).filter((m) => m.company_id === companyId));
      } catch (e) { /* non-fatal - product filter stays optional */ }
    }
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
    if (f.availability && f.availability !== 'both') out.availability = f.availability;
    if (f.market_scope && f.market_scope !== 'all') out.market_scope = f.market_scope;
    if (f.max_price != null && f.max_price !== '') out.max_price = Number(f.max_price);
    return out;
  };

  const runSearch = async (record, useMode, rawFilters) => {
    const m = useMode ?? mode;
    setSearching(true);
    setSearchData(null);
    try {
      const payload = { mode: m };
      if (m === 'targeted') payload.filters = rawFilters ?? buildFilterPayload();
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

  const resultColumns = [
    { title: 'الشركة', key: 'company', width: 110, render: (_, r) => r.lens_model?.company?.name || '—' },
    { title: 'الموديل', key: 'model', width: 150, render: (_, r) => r.lens_model?.name || '—' },
    { title: 'المادة / Index', key: 'idx', width: 150, render: (_, r) => indexMaterialText(r.variant) },
    { title: 'الفئة', key: 'category', width: 110, render: (_, r) => r.lens_model?.category || '—' },
    { title: 'التصميم', key: 'design', width: 130, render: (_, r) => designText(r) },
    { title: 'الطلاء', key: 'coating', width: 130, render: (_, r) => r.coating_name || r.coating_code || '—' },
    { title: 'التقنية / اللون', key: 'tech', width: 130, render: (_, r) => r.color_variant || r.variant?.color_variant || '—' },
    { title: 'سعر التجزئة (زوج)', key: 'price', width: 130, render: (_, r) => `${r.price_pair} ${r.currency}` },
    { title: 'التوفر', key: 'availability', width: 90, render: (_, r) => availLabel(r.availability) },
    { title: 'السوق', key: 'market', width: 120, render: (_, r) => r.market_scope || '—' },
    { title: 'الدرجة', key: 'score', width: 70, render: (_, r) => r.match_score?.toFixed(1) },
    { title: 'السبب', key: 'reason', render: (_, r) => <span style={{ fontSize: 12 }}>{r.reason}</span> },
  ];

  const renderResultCard = (r, extra) => (
    <Descriptions size="small" column={3} bordered style={{ marginBottom: 8 }}>
      <Descriptions.Item label="الشركة">{r.lens_model?.company?.name || '—'}</Descriptions.Item>
      <Descriptions.Item label="الموديل">{r.lens_model?.name}</Descriptions.Item>
      <Descriptions.Item label="المادة / Index">{indexMaterialText(r.variant)}</Descriptions.Item>
      <Descriptions.Item label="الفئة">{r.lens_model?.category}</Descriptions.Item>
      <Descriptions.Item label="التصميم">{designText(r)}</Descriptions.Item>
      <Descriptions.Item label="الطلاء">{r.coating_name || r.coating_code || '—'}</Descriptions.Item>
      <Descriptions.Item label="التقنية / اللون">{r.color_variant || r.variant?.color_variant || '—'}</Descriptions.Item>
      <Descriptions.Item label="سعر التجزئة (زوج)">{`${r.price_pair} ${r.currency}`}</Descriptions.Item>
      <Descriptions.Item label="التوفر">
        {availLabel(r.availability)}{' '}
        <span style={{ color: '#888', fontSize: 12 }}>
          {r.availability === 'stock' ? '— حسب الكتالوج' : '— RX / تصنيع'}
        </span>
      </Descriptions.Item>
      <Descriptions.Item label="السوق">{r.market_scope || '—'}</Descriptions.Item>
      <Descriptions.Item label="الدرجة">{r.match_score?.toFixed(1)}</Descriptions.Item>
      <Descriptions.Item label="السبب" span={2}>{r.reason}</Descriptions.Item>
      {extra}
    </Descriptions>
  );

  const sd = searchData;
  const best = sd?.best_match;

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
        <Radio.Group value={mode} onChange={(e) => setMode(e.target.value)} style={{ marginBottom: 12 }}>
          <Radio value="automatic">بحث تلقائي</Radio>
          <Radio value="targeted">بحث بمواصفات محددة</Radio>
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
                  value={filters.lens_model_id} disabled={!filters.company_id}
                  onChange={(v) => setFilters((f) => ({ ...f, lens_model_id: v }))}
                  options={models.map((m) => ({ value: m.id, label: m.name }))} />
              </Col>
              <Col span={3}>
                <div>Index</div>
                <InputNumber style={{ width: '100%' }} step={0.01} placeholder="الكل"
                  value={filters.index_value} onChange={(v) => setFilters((f) => ({ ...f, index_value: v }))} />
              </Col>
              <Col span={5}>
                <div>الفئة</div>
                <Select allowClear style={{ width: '100%' }} placeholder="الكل" value={filters.category}
                  onChange={(v) => setFilters((f) => ({ ...f, category: v }))} options={CATEGORIES} />
              </Col>
              <Col span={4}>
                <div>السعر الأقصى</div>
                <InputNumber style={{ width: '100%' }} placeholder="الكل"
                  value={filters.max_price} onChange={(v) => setFilters((f) => ({ ...f, max_price: v }))} />
              </Col>
              <Col span={6}>
                <div>التصميم / design_variant</div>
                <Input allowClear placeholder="مثال: Flat Top S28" value={filters.design_variant}
                  onChange={(e) => setFilters((f) => ({ ...f, design_variant: e.target.value }))} />
              </Col>
              <Col span={6}>
                <div>الطلاء</div>
                <Input allowClear placeholder="مثال: Hi Vision Aqua" value={filters.coating}
                  onChange={(e) => setFilters((f) => ({ ...f, coating: e.target.value }))} />
              </Col>
              <Col span={6}>
                <div>التقنية / اللون (color_variant)</div>
                <Input allowClear placeholder="مثال: Sensity 2" value={filters.color_variant}
                  onChange={(e) => setFilters((f) => ({ ...f, color_variant: e.target.value }))} />
              </Col>
              <Col span={3}>
                <div>التوفر</div>
                <Select style={{ width: '100%' }} value={filters.availability || 'both'}
                  onChange={(v) => setFilters((f) => ({ ...f, availability: v }))}
                  options={[{ value: 'both', label: 'الكل' }, { value: 'stock', label: 'STOCK' }, { value: 'rx', label: 'RX' }]} />
              </Col>
              <Col span={3}>
                <div>السوق</div>
                <Select style={{ width: '100%' }} value={filters.market_scope || 'all'}
                  onChange={(v) => setFilters((f) => ({ ...f, market_scope: v }))}
                  options={[{ value: 'all', label: 'الكل' }, { value: 'Egypt', label: 'Egypt' }, { value: 'Out Of Egypt', label: 'Out Of Egypt' }]} />
              </Col>
            </Row>
            <div style={{ marginTop: 8, color: '#888', fontSize: 12 }}>
              كل المرشحات تُطبَّق معاً (AND) ولا يتم تجاوز أي منها تلقائياً.
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
            <Descriptions size="small" column={4} bordered style={{ marginBottom: 12 }}>
              <Descriptions.Item label="نتائج مطابقة">{sd.exact_total}</Descriptions.Item>
              <Descriptions.Item label="STOCK مصر">{sd.stock_egypt_count}</Descriptions.Item>
              <Descriptions.Item label="STOCK خارج مصر">{sd.stock_out_of_egypt_count}</Descriptions.Item>
              <Descriptions.Item label="RX">{sd.rx_count}</Descriptions.Item>
              <Descriptions.Item label="توصية Index" span={2}>{sd.index_recommendation}</Descriptions.Item>
              <Descriptions.Item label="توصية Aspherical" span={2}>{sd.aspherical_recommendation}</Descriptions.Item>
            </Descriptions>

            {best && (
              <Card size="small" title="⭐ أفضل خيار" style={{ marginBottom: 12, borderColor: '#52c41a', borderWidth: 2 }}>
                {renderResultCard(best)}
              </Card>
            )}

            {sd.exact_total === 0 && <Empty description="لا توجد نتيجة مطابقة تماماً" />}

            <Collapse defaultActiveKey={['stock_egypt', 'stock_out_of_egypt', 'rx']}>
              {sd.groups.map((grp) => (
                <Panel
                  key={grp.key}
                  header={
                    <span>
                      {grp.label} <Tag>{grp.count}</Tag>
                      <span style={{ color: '#888', fontSize: 12, marginRight: 8 }}>
                        {grp.availability === 'stock' ? 'حسب الكتالوج' : 'تصنيع حسب الطلب'}
                      </span>
                    </span>
                  }
                >
                  {grp.count === 0 ? (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="لا شيء في هذه المجموعة" />
                  ) : (
                    <Table
                      dataSource={grp.results}
                      columns={resultColumns}
                      rowKey="source_pricing_id"
                      size="small"
                      pagination={grp.count > 20 ? { pageSize: 20 } : false}
                      scroll={{ x: 1200 }}
                    />
                  )}
                </Panel>
              ))}
            </Collapse>

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
                    {renderResultCard(a.result)}
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
