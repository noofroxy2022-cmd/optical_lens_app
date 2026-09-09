import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, InputNumber, Select, Tag, message, Card, Row, Col, Upload, Alert, Statistic, Descriptions, List } from 'antd';
import { UploadOutlined, CheckOutlined, CloseOutlined, FilePdfOutlined, EditOutlined, SaveOutlined } from '@ant-design/icons';
import { companyAPI, pdfImportAPI } from '../services/api';

const { Option } = Select;

// Generic price-interpretation policy sent to POST /pdf-import/extract as
// dual_price_semantics. NOT manufacturer-specific: the operator asserts how a
// two-value price cell should be read. '' -> no special dual-price policy.
const PRICE_POLICIES = [
  { value: '', label: 'لا توجد سياسة سعر مزدوج خاصة' },
  { value: 'left_wholesale_right_retail', label: 'السعر النهائي (التجزئة) في العمود الأيمن' },
];

// Pull a human-readable message out of an axios error without leaking a stack trace.
const errMsg = (error, fallback) => {
  const d = error?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (d && typeof d === 'object') return d.message || JSON.stringify(d);
  return error?.response?.data?.message || fallback;
};

const fmt = (v) => (v === null || v === undefined || v === '' ? '·' : v);

// Compact power-range summary from the extracted range fields.
const powerSummary = (r) => {
  const parts = [];
  if (r.sph_min != null || r.sph_max != null) parts.push(`SPH ${fmt(r.sph_min)}…${fmt(r.sph_max)}`);
  if (r.cyl_min != null || r.cyl_max != null) parts.push(`CYL ${fmt(r.cyl_min)}…${fmt(r.cyl_max)}`);
  if (r.add_min != null || r.add_max != null) parts.push(`ADD ${fmt(r.add_min)}…${fmt(r.add_max)}`);
  if (r.extracted_total_power_min != null || r.extracted_total_power_max != null) {
    const cap = r.extracted_max_cyl_abs != null ? ` |CYL|≤${r.extracted_max_cyl_abs}` : '';
    parts.push(`Σ ${fmt(r.extracted_total_power_min)}…${fmt(r.extracted_total_power_max)}${cap}`);
  }
  return parts.length ? parts.join('   ') : '—';
};

const statusTag = (v) => {
  if (v === 'pending') return <Tag>قيد المراجعة</Tag>;
  if (v === 'confirmed') return <Tag color="green">مؤكد</Tag>;
  if (v === 'rejected') return <Tag color="red">مرفوض</Tag>;
  if (v === 'needs_review') return <Tag color="volcano">يحتاج مراجعة</Tag>;
  return <Tag>{v}</Tag>;
};

const availTag = (v) => (
  v === 'stock' ? <Tag color="green">STOCK</Tag> :
  v === 'rx' ? <Tag color="orange">RX</Tag> :
  v === 'both' ? <Tag color="blue">STOCK+RX</Tag> : <Tag>—</Tag>
);

const PDFPreview = () => {
  const [companies, setCompanies] = useState([]);
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [pricePolicy, setPricePolicy] = useState('');
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [extractions, setExtractions] = useState([]);
  const [catalogId, setCatalogId] = useState(null);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [selectedExtraction, setSelectedExtraction] = useState(null);
  const [editForm] = Form.useForm();
  const [loadingExtractions, setLoadingExtractions] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);
  const [bulkConfirming, setBulkConfirming] = useState(false);
  const [approving, setApproving] = useState(false);

  useEffect(() => {
    loadCompanies();
  }, []);

  const loadCompanies = async () => {
    try {
      const res = await companyAPI.getAll();
      setCompanies(res.data);
    } catch (error) {
      message.error(errMsg(error, 'فشل تحميل الشركات'));
    }
  };

  const handleUpload = async () => {
    if (!file || !selectedCompany) {
      message.warning('اختر شركة وملف PDF');
      return;
    }
    setBulkResult(null);
    setExtractions([]);
    setUploading(true);
    let newCatalogId = null;
    try {
      const res = await pdfImportAPI.upload(selectedCompany, file);
      newCatalogId = res.data.catalog_id;
      setCatalogId(newCatalogId);
      message.success('تم رفع الكتالوج');
    } catch (error) {
      message.error(errMsg(error, 'فشل رفع الكتالوج'));
      setUploading(false);
      return;
    }
    setUploading(false);

    setExtracting(true);
    try {
      const extractRes = await pdfImportAPI.extract(newCatalogId, {
        dualPriceSemantics: pricePolicy || null,
      });
      message.success(extractRes.data.message || 'تم الاستخراج');
      await loadExtractions(newCatalogId);
    } catch (error) {
      message.error(errMsg(error, 'فشل الاستخراج'));
    } finally {
      setExtracting(false);
    }
  };

  const loadExtractions = async (catId) => {
    setLoadingExtractions(true);
    try {
      const res = await pdfImportAPI.getExtractions(catId);
      setExtractions(res.data);
    } catch (error) {
      message.error(errMsg(error, 'فشل تحميل البيانات المستخرجة'));
    } finally {
      setLoadingExtractions(false);
    }
  };

  const handleConfirm = async (extractionId) => {
    try {
      await pdfImportAPI.confirm(extractionId);
      message.success('تمت الموافقة على الصف');
      loadExtractions(catalogId);
    } catch (error) {
      message.error(errMsg(error, 'فشل تأكيد الصف'));
    }
  };

  const handleReject = async (extractionId) => {
    try {
      await pdfImportAPI.reject(extractionId, 'مرفوض يدوياً من المراجعة');
      message.success('تم رفض الصف');
      loadExtractions(catalogId);
    } catch (error) {
      message.error(errMsg(error, 'فشل رفض الصف'));
    }
  };

  // Commercial confirmation only writes rows that have passed row-level review
  // approval first. Approve every clean pending row in one action so the operator
  // is not clicking "موافقة" hundreds of times; rows the backend rejects (e.g.
  // unresolved coating) stay pending and are reported, not forced.
  const handleApproveAllPending = async () => {
    const pend = extractions.filter((e) => e.status === 'pending');
    if (pend.length === 0) return;
    setApproving(true);
    let ok = 0;
    let failed = 0;
    try {
      for (let i = 0; i < pend.length; i += 10) {
        const chunk = pend.slice(i, i + 10);
        const outcomes = await Promise.allSettled(chunk.map((e) => pdfImportAPI.confirm(e.id)));
        outcomes.forEach((o) => (o.status === 'fulfilled' ? (ok += 1) : (failed += 1)));
      }
      if (failed === 0) {
        message.success(`تم اعتماد ${ok} صف للمراجعة`);
      } else {
        message.warning(`تم اعتماد ${ok} صف؛ تعذّر اعتماد ${failed} (طلاء أو بيانات غير محسومة - عدّلها ثم أعد المحاولة)`);
      }
      await loadExtractions(catalogId);
    } catch (error) {
      message.error(errMsg(error, 'فشل اعتماد الصفوف'));
    } finally {
      setApproving(false);
    }
  };

  const handleBulkConfirm = async () => {
    setBulkConfirming(true);
    try {
      const res = await pdfImportAPI.bulkConfirm(catalogId);
      setBulkResult(res.data);
      if (res.data.confirmed > 0) {
        message.success(`تم تأكيد ${res.data.confirmed} صف في قاعدة البيانات التجارية`);
      } else {
        message.warning('لم يتم تأكيد أي صف - راجع الأسباب أدناه');
      }
      await loadExtractions(catalogId);
    } catch (error) {
      setBulkResult(null);
      message.error(errMsg(error, 'فشل تأكيد الكتالوج'));
    } finally {
      setBulkConfirming(false);
    }
  };

  const showEdit = (record) => {
    setSelectedExtraction(record);
    editForm.setFieldsValue({
      extracted_name: record.extracted_name,
      extracted_category: record.extracted_category,
      extracted_material: record.extracted_material,
      extracted_index: record.extracted_index,
      extracted_availability: record.extracted_availability,
      extracted_design: record.extracted_design,
      extracted_color_variant: record.extracted_color_variant,
      extracted_market_scope: record.extracted_market_scope,
      extracted_coating: record.extracted_coating,
      sph_min: record.sph_min,
      sph_max: record.sph_max,
      cyl_min: record.cyl_min,
      cyl_max: record.cyl_max,
      add_min: record.add_min,
      add_max: record.add_max,
      extracted_price: record.extracted_price,
    });
    setEditModalVisible(true);
  };

  const handleEditSave = async (values) => {
    try {
      await pdfImportAPI.updateExtraction(selectedExtraction.id, values);
      message.success('تم حفظ التعديلات');
      setEditModalVisible(false);
      loadExtractions(catalogId);
    } catch (error) {
      message.error(errMsg(error, 'فشل حفظ التعديلات'));
    }
  };

  const columns = [
    { title: 'الحالة', dataIndex: 'status', key: 'status', fixed: 'left', width: 110, render: statusTag },
    { title: 'الموديل', dataIndex: 'extracted_name', key: 'name', fixed: 'left', width: 190, render: (v, r) => (
      <span>
        {v}
        {r.modified_data && <Tag color="orange" style={{ marginRight: 6 }}>معدل</Tag>}
      </span>
    )},
    { title: 'الفئة', dataIndex: 'extracted_category', key: 'category', width: 120, render: (v) => v || '—' },
    { title: 'المادة / Index', key: 'material', width: 150, render: (_, r) => `${r.extracted_material || '—'} / ${r.extracted_index ?? '—'}` },
    { title: 'التصميم', dataIndex: 'extracted_design', key: 'design', width: 140, render: (v) => v || '—' },
    { title: 'اللون / التقنية', dataIndex: 'extracted_color_variant', key: 'color', width: 140, render: (v) => v || '—' },
    { title: 'الطلاء', dataIndex: 'extracted_coating', key: 'coating', width: 120, render: (v) => v || '—' },
    { title: 'سعر التجزئة', dataIndex: 'extracted_price', key: 'price', width: 110, render: (v) => (v != null ? v : '—') },
    { title: 'التوفر', dataIndex: 'extracted_availability', key: 'availability', width: 110, render: availTag },
    { title: 'السوق', dataIndex: 'extracted_market_scope', key: 'market', width: 130, render: (v) => v || '—' },
    { title: 'نطاق القوة', key: 'power', width: 300, render: (_, r) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{powerSummary(r)}</span> },
    { title: 'ملاحظات المراجعة', key: 'notes', width: 260, render: (_, r) => {
      const notes = [r.review_notes, r.coating_review_notes].filter(Boolean).join(' | ');
      return notes ? <span style={{ color: '#cf1322' }}>{notes}</span> : '—';
    }},
    {
      title: 'الإجراءات',
      key: 'actions',
      fixed: 'right',
      width: 230,
      render: (_, record) => (
        <>
          <Button icon={<EditOutlined />} size="small" onClick={() => showEdit(record)} style={{ marginRight: 4 }}>تعديل</Button>
          {(record.status === 'pending' || record.status === 'needs_review') && (
            <>
              <Button icon={<CheckOutlined />} size="small" type="primary" onClick={() => handleConfirm(record.id)} style={{ marginRight: 4 }}>موافقة</Button>
              <Button icon={<CloseOutlined />} size="small" danger onClick={() => handleReject(record.id)}>رفض</Button>
            </>
          )}
        </>
      ),
    },
  ];

  const pendingCount = extractions.filter((e) => e.status === 'pending').length;
  const needsReviewCount = extractions.filter((e) => e.status === 'needs_review').length;
  const confirmedCount = extractions.filter((e) => e.status === 'confirmed').length;

  return (
    <div>
      <h1>📄 استيراد الكتالوجات (PDF)</h1>

      <Card style={{ marginBottom: 24 }}>
        <Row gutter={16} align="middle">
          <Col span={5}>
            <Select
              placeholder="اختر الشركة"
              style={{ width: '100%' }}
              value={selectedCompany}
              onChange={setSelectedCompany}
            >
              {companies.map((c) => <Option key={c.id} value={c.id}>{c.name}</Option>)}
            </Select>
          </Col>
          <Col span={7}>
            <Select
              style={{ width: '100%' }}
              value={pricePolicy}
              onChange={setPricePolicy}
              options={PRICE_POLICIES}
            />
          </Col>
          <Col span={6}>
            <Upload
              beforeUpload={(f) => { setFile(f); return false; }}
              accept=".pdf"
              maxCount={1}
            >
              <Button icon={<UploadOutlined />}>اختر ملف PDF</Button>
            </Upload>
          </Col>
          <Col span={6}>
            <Button
              type="primary"
              icon={<FilePdfOutlined />}
              onClick={handleUpload}
              loading={uploading || extracting}
              disabled={!file || !selectedCompany}
              block
            >
              {uploading ? 'جاري الرفع...' : extracting ? 'جاري الاستخراج...' : 'رفع واستخراج'}
            </Button>
          </Col>
        </Row>
        <div style={{ marginTop: 8, color: '#888', fontSize: 12 }}>
          تفسير أعمدة السعر: يحدد كيف يقرأ المحلّل خلية السعر متعددة القيم قبل الاستخراج.
        </div>
        {file && (
          <Alert message={`الملف المختار: ${file.name}`} type="info" style={{ marginTop: 12 }} />
        )}
      </Card>

      {catalogId && (
        <>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={5}><Card size="small"><Statistic title="قيد المراجعة" value={pendingCount} valueStyle={{ color: '#faad14' }} /></Card></Col>
            <Col span={5}><Card size="small"><Statistic title="يحتاج مراجعة" value={needsReviewCount} valueStyle={{ color: '#d4380d' }} /></Card></Col>
            <Col span={5}><Card size="small"><Statistic title="مؤكد" value={confirmedCount} valueStyle={{ color: '#52c41a' }} /></Card></Col>
            <Col span={9}>
              <Card size="small">
                <Button
                  block
                  icon={<CheckOutlined />}
                  loading={approving}
                  onClick={handleApproveAllPending}
                  disabled={pendingCount === 0}
                  style={{ marginBottom: 8 }}
                >
                  اعتماد كل الصفوف المعلّقة ({pendingCount})
                </Button>
                <Button
                  type="primary"
                  block
                  icon={<CheckOutlined />}
                  loading={bulkConfirming}
                  onClick={handleBulkConfirm}
                  disabled={extractions.length === 0}
                >
                  تأكيد الكتالوج
                </Button>
                <div style={{ marginTop: 6, color: '#888', fontSize: 12 }}>
                  اعتمد الصفوف المعلّقة أولاً، ثم أكّد الكتالوج لكتابة الأسعار التجارية.
                </div>
              </Card>
            </Col>
          </Row>

          {bulkResult && (
            <Card
              title="نتيجة تأكيد الكتالوج"
              size="small"
              style={{ marginBottom: 16, borderColor: bulkResult.confirmed > 0 ? '#52c41a' : '#faad14' }}
            >
              <Descriptions size="small" column={3} bordered>
                <Descriptions.Item label="مؤكد تجارياً">{bulkResult.confirmed}</Descriptions.Item>
                <Descriptions.Item label="متخطى (غير محسوم)">{bulkResult.skipped_unresolved}</Descriptions.Item>
                <Descriptions.Item label="تكرارات مطابقة مدمجة">{bulkResult.true_duplicates_collapsed}</Descriptions.Item>
                <Descriptions.Item label="تعارضات سعر">{bulkResult.conflicts}</Descriptions.Item>
                <Descriptions.Item label="إصدارات سابقة أُغلقت">{bulkResult.closed_previous_current}</Descriptions.Item>
                <Descriptions.Item label="حالة الكتالوج">{bulkResult.status}</Descriptions.Item>
              </Descriptions>
              {bulkResult.confirmed > 0 && (
                <Alert
                  style={{ marginTop: 12 }}
                  type="success"
                  showIcon
                  message="نجاح جزئي = نجاح: تمت كتابة الصفوف السليمة. الصفوف المتبقية أُعيدت إلى المراجعة بسبب مذكور."
                />
              )}
              {bulkResult.parked && bulkResult.parked.length > 0 && (
                <List
                  size="small"
                  header={<strong>صفوف أُعيدت للمراجعة ({bulkResult.parked.length})</strong>}
                  style={{ marginTop: 12 }}
                  dataSource={bulkResult.parked}
                  renderItem={(p) => (
                    <List.Item>
                      <Tag color="volcano">صف #{p.extraction_id}</Tag> {p.reason}
                    </List.Item>
                  )}
                />
              )}
              <div style={{ marginTop: 8, color: '#888', fontSize: 12 }}>
                استخدم جدول المراجعة أدناه لتعديل أو رفض الصفوف المُعادة ثم أعد "تأكيد الكتالوج".
              </div>
            </Card>
          )}

          <h3>البيانات المستخرجة - مراجعة وتأكيد</h3>
          <Table
            dataSource={extractions}
            columns={columns}
            rowKey="id"
            loading={loadingExtractions}
            scroll={{ x: 2200 }}
            size="small"
            pagination={{ pageSize: 25, showSizeChanger: true }}
            rowClassName={(r) => (r.status === 'needs_review' ? 'row-needs-review' : '')}
          />
          <style>{`.row-needs-review > td { background: #fff7e6 !important; }`}</style>
        </>
      )}

      {/* Modal تعديل */}
      <Modal title="تعديل البيانات المستخرجة" open={editModalVisible} onCancel={() => setEditModalVisible(false)} footer={null} width={760}>
        <Form form={editForm} onFinish={handleEditSave} layout="vertical">
          <Row gutter={16}>
            <Col span={12}><Form.Item name="extracted_name" label="الموديل" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="extracted_category" label="الفئة">
              <Select allowClear>
                <Option value="single_vision">أحادية البؤرة</Option>
                <Option value="bifocal">ثنائية البؤرة</Option>
                <Option value="progressive">متعددة البؤرة</Option>
                <Option value="office">مكتبية</Option>
              </Select>
            </Form.Item></Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}><Form.Item name="extracted_material" label="المادة"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="extracted_index" label="Index"><InputNumber step={0.01} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="extracted_availability" label="التوفر">
              <Select allowClear>
                <Option value="stock">STOCK</Option>
                <Option value="rx">RX</Option>
                <Option value="both">STOCK+RX</Option>
              </Select>
            </Form.Item></Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}><Form.Item name="extracted_design" label="التصميم / نسخة التصميم"><Input placeholder="مثال: Flat Top S28" /></Form.Item></Col>
            <Col span={8}><Form.Item name="extracted_color_variant" label="اللون / التقنية"><Input placeholder="مثال: Sensity 2" /></Form.Item></Col>
            <Col span={8}><Form.Item name="extracted_market_scope" label="السوق"><Input placeholder="مثال: Egypt / Out Of Egypt" /></Form.Item></Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="extracted_coating" label="الطلاء"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="extracted_price" label="سعر التجزئة"><InputNumber style={{ width: '100%' }} /></Form.Item></Col>
          </Row>
          <Row gutter={16}>
            <Col span={6}><Form.Item name="sph_min" label="SPH Min"><InputNumber step={0.25} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={6}><Form.Item name="sph_max" label="SPH Max"><InputNumber step={0.25} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={6}><Form.Item name="cyl_min" label="CYL Min"><InputNumber step={0.25} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={6}><Form.Item name="cyl_max" label="CYL Max"><InputNumber step={0.25} style={{ width: '100%' }} /></Form.Item></Col>
          </Row>
          <Row gutter={16}>
            <Col span={6}><Form.Item name="add_min" label="ADD Min"><InputNumber step={0.25} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={6}><Form.Item name="add_max" label="ADD Max"><InputNumber step={0.25} style={{ width: '100%' }} /></Form.Item></Col>
          </Row>
          <Button type="primary" htmlType="submit" icon={<SaveOutlined />} block>حفظ التعديلات</Button>
        </Form>
      </Modal>
    </div>
  );
};

export default PDFPreview;
