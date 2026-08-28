import React, { useEffect, useState } from 'react';
import { Table, Button, Modal, Form, Input, Switch, message, Popconfirm, Tag, Upload, Card, Row, Col, Statistic } from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined, EyeOutlined, UploadOutlined, PoweroffOutlined } from '@ant-design/icons';
import { companyAPI, lensModelAPI } from '../services/api';

const Companies = () => {
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [form] = Form.useForm();
  const [editForm] = Form.useForm();

  useEffect(() => {
    loadCompanies();
  }, []);

  const loadCompanies = async () => {
    setLoading(true);
    try {
      const res = await companyAPI.getAll({ include_inactive: true });
      setCompanies(res.data);
    } catch (error) {
      message.error('فشل تحميل الشركات');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (values) => {
    try {
      await companyAPI.create(values);
      message.success('تم إضافة الشركة بنجاح');
      setModalVisible(false);
      form.resetFields();
      loadCompanies();
    } catch (error) {
      message.error('فشل الإضافة');
    }
  };

  const handleUpdate = async (values) => {
    try {
      await companyAPI.update(selectedCompany.id, values);
      message.success('تم التحديث بنجاح');
      setEditModalVisible(false);
      loadCompanies();
    } catch (error) {
      message.error('فشل التحديث');
    }
  };

  const handleToggleActive = async (id) => {
    try {
      const res = await companyAPI.toggleActive(id);
      const status = res.data.is_active ? 'مفعلة' : 'معطلة';
      message.success(`الشركة الآن ${status}`);
      loadCompanies();
    } catch (error) {
      message.error('فشل التغيير');
    }
  };

  const handleDelete = async (id, hard = false) => {
    try {
      await companyAPI.delete(id, hard);
      message.success(hard ? 'تم الحذف النهائي' : 'تم الحذف');
      loadCompanies();
    } catch (error) {
      message.error('فشل الحذف');
    }
  };

  const showEdit = (company) => {
    setSelectedCompany(company);
    editForm.setFieldsValue(company);
    setEditModalVisible(true);
  };

  const showDetail = (company) => {
    setSelectedCompany(company);
    setDetailModalVisible(true);
  };

  const activeCount = companies.filter(c => c.is_active && !c.is_deleted).length;
  const inactiveCount = companies.filter(c => !c.is_active && !c.is_deleted).length;

  const columns = [
    { title: 'الشعار', dataIndex: 'logo_url', key: 'logo', render: (v) => v ? <img src={v} alt="logo" style={{ width: 40, height: 40, objectFit: 'contain' }} /> : '—' },
    { title: 'الاسم', dataIndex: 'name', key: 'name', render: (v, record) => (
      <span>
        {v}
        {record.name_ar && <span style={{ color: '#888', fontSize: 12, marginRight: 8 }}>({record.name_ar})</span>}
      </span>
    )},
    { title: 'الدولة', dataIndex: 'country', key: 'country', render: (v) => v || '—' },
    { title: 'الحالة', dataIndex: 'is_active', key: 'status', render: (v) => (
      v ? <Tag color="green">نشطة</Tag> : <Tag color="red">معطلة</Tag>
    )},
    { title: 'العدسات', dataIndex: 'lens_models_count', key: 'lenses' },
    { title: 'الكتالوجات', dataIndex: 'catalogs_count', key: 'catalogs' },
    {
      title: 'الإجراءات',
      key: 'actions',
      width: 280,
      render: (_, record) => (
        <>
          <Button icon={<EyeOutlined />} size="small" onClick={() => showDetail(record)} style={{ marginRight: 4 }} />
          <Button icon={<EditOutlined />} size="small" onClick={() => showEdit(record)} style={{ marginRight: 4 }} />
          <Button 
            icon={<PoweroffOutlined />} 
            size="small" 
            onClick={() => handleToggleActive(record.id)}
            style={{ marginRight: 4 }}
            type={record.is_active ? "default" : "primary"}
          >
            {record.is_active ? 'تعطيل' : 'تفعيل'}
          </Button>
          <Popconfirm title="حذف نهائي؟" onConfirm={() => handleDelete(record.id, true)}>
            <Button danger icon={<DeleteOutlined />} size="small">حذف</Button>
          </Popconfirm>
        </>
      ),
    },
  ];

  return (
    <div>
      <h1 style={{ marginBottom: '16px' }}>🏢 إدارة الشركات</h1>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={8}>
          <Card><Statistic title="الشركات النشطة" value={activeCount} valueStyle={{ color: '#52c41a' }} /></Card>
        </Col>
        <Col span={8}>
          <Card><Statistic title="الشركات المعطلة" value={inactiveCount} valueStyle={{ color: '#ff4d4f' }} /></Card>
        </Col>
        <Col span={8}>
          <Card><Statistic title="الإجمالي" value={companies.length} /></Card>
        </Col>
      </Row>

      <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalVisible(true)} style={{ marginBottom: 16 }}>
        شركة جديدة
      </Button>

      <Table dataSource={companies} columns={columns} rowKey="id" loading={loading} />

      {/* Modal إضافة */}
      <Modal title="إضافة شركة" open={modalVisible} onCancel={() => setModalVisible(false)} footer={null} width={600}>
        <Form form={form} onFinish={handleCreate} layout="vertical">
          <Row gutter={16}>
            <Col span={12}><Form.Item name="name" label="الاسم (إنجليزي)" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="name_ar" label="الاسم (عربي)"><Input /></Form.Item></Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="country" label="الدولة"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="website" label="الموقع"><Input /></Form.Item></Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="contact_email" label="البريد"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="contact_phone" label="الهاتف"><Input /></Form.Item></Col>
          </Row>
          <Form.Item name="description" label="الوصف"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="notes" label="ملاحظات"><Input.TextArea rows={2} /></Form.Item>
          <Button type="primary" htmlType="submit" block>حفظ</Button>
        </Form>
      </Modal>

      {/* Modal تعديل */}
      <Modal title="تعديل شركة" open={editModalVisible} onCancel={() => setEditModalVisible(false)} footer={null} width={600}>
        <Form form={editForm} onFinish={handleUpdate} layout="vertical">
          <Row gutter={16}>
            <Col span={12}><Form.Item name="name" label="الاسم (إنجليزي)" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="name_ar" label="الاسم (عربي)"><Input /></Form.Item></Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="country" label="الدولة"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="website" label="الموقع"><Input /></Form.Item></Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="contact_email" label="البريد"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="contact_phone" label="الهاتف"><Input /></Form.Item></Col>
          </Row>
          <Form.Item name="description" label="الوصف"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="is_active" valuePropName="checked" label="نشطة"><Switch /></Form.Item>
          <Button type="primary" htmlType="submit" block>تحديث</Button>
        </Form>
      </Modal>

      {/* Modal تفاصيل */}
      <Modal title="تفاصيل الشركة" open={detailModalVisible} onCancel={() => setDetailModalVisible(false)} footer={null}>
        {selectedCompany && (
          <div>
            <p><strong>الاسم:</strong> {selectedCompany.name}</p>
            <p><strong>الدولة:</strong> {selectedCompany.country || '—'}</p>
            <p><strong>الموقع:</strong> {selectedCompany.website || '—'}</p>
            <p><strong>البريد:</strong> {selectedCompany.contact_email || '—'}</p>
            <p><strong>الهاتف:</strong> {selectedCompany.contact_phone || '—'}</p>
            <p><strong>الوصف:</strong> {selectedCompany.description || '—'}</p>
            <p><strong>الحالة:</strong> {selectedCompany.is_active ? 'نشطة ✅' : 'معطلة ❌'}</p>
            <p><strong>تاريخ الإنشاء:</strong> {new Date(selectedCompany.created_at).toLocaleString('ar-SA')}</p>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default Companies;
