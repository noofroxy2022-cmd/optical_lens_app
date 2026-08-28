import React, { useEffect, useState } from 'react';
import { Table, Button, Modal, Form, Input, InputNumber, Select, Switch, message, Popconfirm, Row, Col } from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import { lensAPI, companyAPI } from '../services/api';

const { Option } = Select;

const Lenses = () => {
  const [lenses, setLenses] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [form] = Form.useForm();

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [lensesRes, companiesRes] = await Promise.all([
        lensAPI.getAll(),
        companyAPI.getAll(),
      ]);
      setLenses(lensesRes.data);
      setCompanies(companiesRes.data);
    } catch (error) {
      message.error('فشل التحميل');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (values) => {
    try {
      await lensAPI.create(values);
      message.success('تم إضافة العدسة بنجاح');
      setModalVisible(false);
      form.resetFields();
      loadData();
    } catch (error) {
      message.error('فشل الإضافة');
    }
  };

  const handleDelete = async (id) => {
    try {
      await lensAPI.delete(id);
      message.success('تم الحذف');
      loadData();
    } catch (error) {
      message.error('فشل الحذف');
    }
  };

  const columns = [
    { title: 'الاسم', dataIndex: 'name', key: 'name' },
    { title: 'الشركة', dataIndex: ['company', 'name'], key: 'company' },
    { title: 'النوع', dataIndex: 'lens_type', key: 'lens_type' },
    { title: 'المادة', dataIndex: 'material', key: 'material' },
    { title: 'Index', dataIndex: 'index', key: 'index' },
    { title: 'السعر', dataIndex: 'price', key: 'price', render: (v) => `$${v}` },
    {
      title: 'الإجراءات',
      key: 'actions',
      render: (_, record) => (
        <Popconfirm title="هل أنت متأكد؟" onConfirm={() => handleDelete(record.id)}>
          <Button danger icon={<DeleteOutlined />} size="small">حذف</Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px' }}>
        <h1>👁️ إدارة العدسات</h1>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalVisible(true)}>
          عدسة جديدة
        </Button>
      </div>

      <Table dataSource={lenses} columns={columns} rowKey="id" loading={loading} scroll={{ x: true }} />

      <Modal
        title="إضافة عدسة جديدة"
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        footer={null}
        width={700}
      >
        <Form form={form} onFinish={handleCreate} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="company_id" label="الشركة" rules={[{ required: true }]}>
                <Select placeholder="اختر الشركة">
                  {companies.map(c => <Option key={c.id} value={c.id}>{c.name}</Option>)}
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="name" label="اسم العدسة" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="lens_type" label="نوع العدسة" rules={[{ required: true }]}>
                <Select>
                  <Option value="single_vision">أحادية البؤرة</Option>
                  <Option value="bifocal">ثنائية البؤرة</Option>
                  <Option value="progressive">متعددة البؤرة</Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="material" label="المادة" rules={[{ required: true }]}>
                <Select>
                  <Option value="CR39">CR-39</Option>
                  <Option value="polycarbonate">بولي كربونيت</Option>
                  <Option value="high_index_1.60">High Index 1.60</Option>
                  <Option value="high_index_1.67">High Index 1.67</Option>
                  <Option value="high_index_1.74">High Index 1.74</Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="sph_min" label="SPH Min" rules={[{ required: true }]}>
                <InputNumber step={0.25} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="sph_max" label="SPH Max" rules={[{ required: true }]}>
                <InputNumber step={0.25} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="cyl_min" label="CYL Min" rules={[{ required: true }]}>
                <InputNumber step={0.25} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="cyl_max" label="CYL Max" rules={[{ required: true }]}>
                <InputNumber step={0.25} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="index" label="Index" rules={[{ required: true }]}>
                <InputNumber step={0.01} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="price" label="السعر" rules={[{ required: true }]}>
                <InputNumber style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="diameter" label="القطر (mm)">
                <InputNumber style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={6}><Form.Item name="anti_reflective" valuePropName="checked"><Switch /> Anti-Reflective</Form.Item></Col>
            <Col span={6}><Form.Item name="photochromic" valuePropName="checked"><Switch /> Photochromic</Form.Item></Col>
            <Col span={6}><Form.Item name="blue_light_filter" valuePropName="checked"><Switch /> Blue Light</Form.Item></Col>
            <Col span={6}><Form.Item name="uv_protection" valuePropName="checked"><Switch /> UV</Form.Item></Col>
          </Row>

          <Form.Item name="description" label="الوصف">
            <Input.TextArea rows={2} />
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" block>حفظ العدسة</Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default Lenses;
