import React, { useEffect, useState } from 'react';
import { Table, Button, Modal, Descriptions, Tag, message, Popconfirm, Form, Input, InputNumber, Row, Col, Card, Empty, Alert } from 'antd';
import { EyeOutlined, DeleteOutlined, PlusOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { prescriptionAPI } from '../services/api';

const errMsg = (error, fallback) => {
  const d = error?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d.length) return d.map((x) => x.msg || JSON.stringify(x)).join(' | ');
  if (d && typeof d === 'object') return d.message || JSON.stringify(d);
  return error?.response?.data?.message || fallback;
};

const availLabel = (v) => (v === 'stock' ? <Tag color="green">STOCK</Tag> : <Tag color="orange">RX</Tag>);

const Prescriptions = () => {
  const [prescriptions, setPrescriptions] = useState([]);
  const [selected, setSelected] = useState(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [loading, setLoading] = useState(false);

  const [createVisible, setCreateVisible] = useState(false);
  const [createForm] = Form.useForm();
  const [creating, setCreating] = useState(false);

  const [matchVisible, setMatchVisible] = useState(false);
  const [matching, setMatching] = useState(false);
  const [matchData, setMatchData] = useState(null);
  const [matchFor, setMatchFor] = useState(null);

  useEffect(() => {
    loadPrescriptions();
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
        od: {
          sph: values.od_sph, cyl: values.od_cyl ?? 0,
          axis: values.od_axis ?? 0, add: values.od_add ?? 0,
        },
        os: {
          sph: values.os_sph, cyl: values.os_cyl ?? 0,
          axis: values.os_axis ?? 0, add: values.os_add ?? 0,
        },
      };
      const res = await prescriptionAPI.create(payload);
      message.success('تم إنشاء الوصفة');
      setCreateVisible(false);
      createForm.resetFields();
      await loadPrescriptions();
      runMatch(res.data);
    } catch (error) {
      message.error(errMsg(error, 'فشل إنشاء الوصفة'));
    } finally {
      setCreating(false);
    }
  };

  const runMatch = async (record) => {
    setMatchFor(record);
    setMatchData(null);
    setMatchVisible(true);
    setMatching(true);
    try {
      const res = await prescriptionAPI.match(record.id);
      setMatchData(res.data);
    } catch (error) {
      message.error(errMsg(error, 'فشل مطابقة العدسات'));
      setMatchVisible(false);
    } finally {
      setMatching(false);
    }
  };

  const columns = [
    { title: 'العميل', dataIndex: 'customer_name', key: 'customer_name', render: (v) => v || '—' },
    { title: 'OD SPH', dataIndex: 'od_sph', key: 'od_sph' },
    { title: 'OS SPH', dataIndex: 'os_sph', key: 'os_sph' },
    { title: 'PD', dataIndex: 'pd', key: 'pd', render: (v) => v || '—' },
    {
      title: 'التاريخ',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (v) => new Date(v).toLocaleString('ar-SA'),
    },
    {
      title: 'الإجراءات',
      key: 'actions',
      render: (_, record) => (
        <>
          <Button icon={<ThunderboltOutlined />} size="small" type="primary" onClick={() => runMatch(record)} style={{ marginRight: 8 }}>
            مطابقة العدسات
          </Button>
          <Button icon={<EyeOutlined />} size="small" onClick={() => viewDetails(record)} style={{ marginRight: 8 }}>
            عرض
          </Button>
          <Popconfirm title="هل أنت متأكد؟" onConfirm={() => handleDelete(record.id)}>
            <Button danger icon={<DeleteOutlined />} size="small">حذف</Button>
          </Popconfirm>
        </>
      ),
    },
  ];

  const resultColumns = [
    { title: 'الموديل', key: 'model', render: (_, r) => r.lens_model?.name || '—' },
    { title: 'الفئة', key: 'category', render: (_, r) => r.lens_model?.category || '—' },
    { title: 'المادة / Index', key: 'material', render: (_, r) => `${r.variant?.material || '—'} / ${r.variant?.index_value ?? '—'}` },
    { title: 'التصميم', key: 'design', render: (_, r) => r.design_variant || r.variant?.design_variant || (r.variant?.is_aspherical ? 'Aspherical' : r.variant?.design_type) || '—' },
    { title: 'اللون / التقنية', key: 'color', render: (_, r) => r.color_variant || r.variant?.color_variant || '—' },
    { title: 'الطلاء', key: 'coating', render: (_, r) => r.coating_name || r.coating_code || '—' },
    { title: 'السعر (زوج)', key: 'price', render: (_, r) => `${r.price_pair} ${r.currency}` },
    { title: 'التوفر', key: 'availability', render: (_, r) => availLabel(r.availability) },
    { title: 'السوق', key: 'market', render: (_, r) => r.market_scope || '—' },
    { title: 'الدرجة', key: 'score', render: (_, r) => r.match_score?.toFixed(1) },
    { title: 'السبب', key: 'reason', render: (_, r) => <span style={{ fontSize: 12 }}>{r.reason}</span> },
  ];

  const results = matchData?.results || [];
  const best = results[0];
  const alternatives = results.slice(1);

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

      {/* إنشاء وصفة */}
      <Modal title="وصفة جديدة" open={createVisible} onCancel={() => setCreateVisible(false)} footer={null} width={720}>
        <Form form={createForm} layout="vertical" onFinish={handleCreate}>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="customer_name" label="اسم العميل"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="customer_phone" label="الهاتف"><Input /></Form.Item></Col>
            <Col span={4}><Form.Item name="pd" label="PD"><InputNumber step={0.5} min={40} max={80} style={{ width: '100%' }} /></Form.Item></Col>
          </Row>

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

          <Form.Item name="notes" label="ملاحظات"><Input.TextArea rows={2} /></Form.Item>
          <Button type="primary" htmlType="submit" block loading={creating}>حفظ ومطابقة العدسات</Button>
        </Form>
      </Modal>

      {/* نتائج المطابقة */}
      <Modal
        title={`نتائج مطابقة العدسات${matchFor ? ` - وصفة #${matchFor.id}` : ''}`}
        open={matchVisible}
        onCancel={() => setMatchVisible(false)}
        footer={null}
        width={1100}
      >
        {matching && <div style={{ padding: 40, textAlign: 'center' }}>جاري المطابقة...</div>}
        {!matching && matchData && (
          <>
            <Descriptions size="small" column={4} bordered style={{ marginBottom: 16 }}>
              <Descriptions.Item label="إجمالي النتائج">{matchData.total_matches}</Descriptions.Item>
              <Descriptions.Item label="STOCK">{matchData.stock_count}</Descriptions.Item>
              <Descriptions.Item label="RX">{matchData.rx_count}</Descriptions.Item>
              <Descriptions.Item label="تحويل CYL">{matchData.transposition_applied ? 'مُطبّق' : 'لا'}</Descriptions.Item>
              <Descriptions.Item label="توصية Index" span={2}>{matchData.index_recommendation}</Descriptions.Item>
              <Descriptions.Item label="توصية Aspherical" span={2}>{matchData.aspherical_recommendation}</Descriptions.Item>
            </Descriptions>

            {results.length === 0 && <Empty description="لا توجد عدسات مطابقة" />}

            {best && (
              <Card
                size="small"
                title="⭐ أفضل تطابق"
                style={{ marginBottom: 16, borderColor: '#52c41a', borderWidth: 2 }}
              >
                <Descriptions size="small" column={3}>
                  <Descriptions.Item label="الموديل">{best.lens_model?.name}</Descriptions.Item>
                  <Descriptions.Item label="الفئة">{best.lens_model?.category}</Descriptions.Item>
                  <Descriptions.Item label="المادة / Index">{best.variant?.material} / {best.variant?.index_value}</Descriptions.Item>
                  <Descriptions.Item label="التصميم">{best.design_variant || best.variant?.design_variant || (best.variant?.is_aspherical ? 'Aspherical' : best.variant?.design_type) || '—'}</Descriptions.Item>
                  <Descriptions.Item label="اللون / التقنية">{best.color_variant || best.variant?.color_variant || '—'}</Descriptions.Item>
                  <Descriptions.Item label="الطلاء">{best.coating_name || best.coating_code || '—'}</Descriptions.Item>
                  <Descriptions.Item label="السعر (زوج)">{`${best.price_pair} ${best.currency}`}</Descriptions.Item>
                  <Descriptions.Item label="التوفر">{availLabel(best.availability)}</Descriptions.Item>
                  <Descriptions.Item label="السوق">{best.market_scope || '—'}</Descriptions.Item>
                  <Descriptions.Item label="الدرجة">{best.match_score?.toFixed(1)}</Descriptions.Item>
                  <Descriptions.Item label="السبب" span={2}>{best.reason}</Descriptions.Item>
                </Descriptions>
              </Card>
            )}

            {alternatives.length > 0 && (
              <>
                <h4>بدائل ({alternatives.length})</h4>
                <Table
                  dataSource={alternatives}
                  columns={resultColumns}
                  rowKey="source_pricing_id"
                  size="small"
                  pagination={false}
                  scroll={{ x: 1100 }}
                />
                <Alert
                  style={{ marginTop: 12 }}
                  type="info"
                  showIcon
                  message="النتائج مرتبة ومصفّاة من الخادم. الترتيب أعلاه هو ترتيب المطابقة النهائي."
                />
              </>
            )}
          </>
        )}
      </Modal>
    </div>
  );
};

export default Prescriptions;
