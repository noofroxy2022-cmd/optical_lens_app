import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, InputNumber, Select, Tag, message, Tabs, Card, Row, Col, Upload, Spin, Alert, Checkbox } from 'antd';
import { UploadOutlined, EyeOutlined, CheckOutlined, CloseOutlined, FilePdfOutlined, EditOutlined, SaveOutlined } from '@ant-design/icons';
import { companyAPI, pdfImportAPI } from '../services/api';

const { TabPane } = Tabs;
const { Option } = Select;

const PDFPreview = () => {
  const [companies, setCompanies] = useState([]);
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [previewData, setPreviewData] = useState(null);
  const [extractions, setExtractions] = useState([]);
  const [catalogId, setCatalogId] = useState(null);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [selectedExtraction, setSelectedExtraction] = useState(null);
  const [editForm] = Form.useForm();
  const [loadingExtractions, setLoadingExtractions] = useState(false);

  useEffect(() => {
    loadCompanies();
  }, []);

  const loadCompanies = async () => {
    try {
      const res = await companyAPI.getAll();
      setCompanies(res.data);
    } catch (error) {
      message.error('فشل تحميل الشركات');
    }
  };

  const handleUpload = async () => {
    if (!file || !selectedCompany) {
      message.warning('اختر شركة وملف PDF');
      return;
    }

    setUploading(true);
    try {
      const res = await pdfImportAPI.upload(selectedCompany, file);
      setCatalogId(res.data.catalog_id);
      message.success('تم رفع الكتالوج');

      // استخراج تلقائي
      setExtracting(true);
      const extractRes = await pdfImportAPI.extract(res.data.catalog_id);
      message.success(extractRes.data.message);

      // جلب البيانات المستخرجة
      await loadExtractions(res.data.catalog_id);

    } catch (error) {
      message.error('فشل العملية');
    } finally {
      setUploading(false);
      setExtracting(false);
    }
  };

  const loadExtractions = async (catId) => {
    setLoadingExtractions(true);
    try {
      const res = await pdfImportAPI.getExtractions(catId);
      setExtractions(res.data);
    } catch (error) {
      message.error('فشل تحميل البيانات');
    } finally {
      setLoadingExtractions(false);
    }
  };

  const handlePreview = async () => {
    if (!catalogId) {
      message.warning('ارفع كتالوج أولاً');
      return;
    }
    try {
      const res = await pdfImportAPI.preview(catalogId);
      setPreviewData(res.data);
    } catch (error) {
      message.error('فشل المعاينة');
    }
  };

  const handleConfirm = async (extractionId) => {
    try {
      await pdfImportAPI.confirm(extractionId);
      message.success('تم التأكيد');
      loadExtractions(catalogId);
    } catch (error) {
      message.error('فشل التأكيد');
    }
  };

  const handleReject = async (extractionId) => {
    try {
      await pdfImportAPI.reject(extractionId, 'مرفوض يدوياً');
      message.success('تم الرفض');
      loadExtractions(catalogId);
    } catch (error) {
      message.error('فشل الرفض');
    }
  };

  const handleBulkConfirm = async () => {
    try {
      const res = await pdfImportAPI.bulkConfirm(catalogId);
      message.success(res.data.message);
      loadExtractions(catalogId);
    } catch (error) {
      message.error('فشل التأكيد المجمع');
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
      message.success('تم التحديث');
      setEditModalVisible(false);
      loadExtractions(catalogId);
    } catch (error) {
      message.error('فشل التحديث');
    }
  };

  const columns = [
    { title: 'الاسم', dataIndex: 'extracted_name', key: 'name', render: (v, r) => (
      <span>
        {v}
        {r.modified_data && <Tag color="orange" style={{ marginRight: 8 }}>معدل</Tag>}
      </span>
    )},
    { title: 'النوع', dataIndex: 'extracted_category', key: 'category', render: v => v || '—' },
    { title: 'المادة', dataIndex: 'extracted_material', key: 'material', render: v => v || '—' },
    { title: 'Index', dataIndex: 'extracted_index', key: 'index', render: v => v || '—' },
    { title: 'SPH', key: 'sph', render: (_, r) => `[${r.sph_min}, ${r.sph_max}]` },
    { title: 'CYL', key: 'cyl', render: (_, r) => `[${r.cyl_min}, ${r.cyl_max}]` },
    { title: 'ADD', key: 'add', render: (_, r) => r.add_min ? `[${r.add_min}, ${r.add_max}]` : '—' },
    { title: 'السعر', dataIndex: 'extracted_price', key: 'price', render: v => v ? `$${v}` : '—' },
    { title: 'التوفر', dataIndex: 'extracted_availability', key: 'availability', render: v => (
      v === 'stock' ? <Tag color="green">Stock</Tag> :
      v === 'rx' ? <Tag color="orange">RX</Tag> :
      v === 'both' ? <Tag color="blue">Both</Tag> : <Tag>—</Tag>
    )},
    { title: 'الحالة', dataIndex: 'status', key: 'status', render: v => (
      v === 'pending' ? <Tag>قيد المراجعة</Tag> :
      v === 'confirmed' ? <Tag color="green">مؤكد</Tag> :
      v === 'rejected' ? <Tag color="red">مرفوض</Tag> : <Tag>{v}</Tag>
    )},
    {
      title: 'الإجراءات',
      key: 'actions',
      width: 250,
      render: (_, record) => (
        <>
          <Button icon={<EditOutlined />} size="small" onClick={() => showEdit(record)} style={{ marginRight: 4 }}>تعديل</Button>
          {record.status === 'pending' && (
            <>
              <Button icon={<CheckOutlined />} size="small" type="primary" onClick={() => handleConfirm(record.id)} style={{ marginRight: 4 }}>تأكيد</Button>
              <Button icon={<CloseOutlined />} size="small" danger onClick={() => handleReject(record.id)}>رفض</Button>
            </>
          )}
        </>
      ),
    },
  ];

  const pendingCount = extractions.filter(e => e.status === 'pending').length;
  const confirmedCount = extractions.filter(e => e.status === 'confirmed').length;

  return (
    <div>
      <h1>📄 استيراد الكتالوجات (PDF)</h1>

      <Card style={{ marginBottom: 24 }}>
        <Row gutter={16} align="middle">
          <Col span={6}>
            <Select
              placeholder="اختر الشركة"
              style={{ width: '100%' }}
              onChange={setSelectedCompany}
            >
              {companies.map(c => <Option key={c.id} value={c.id}>{c.name}</Option>)}
            </Select>
          </Col>
          <Col span={8}>
            <Upload
              beforeUpload={(file) => { setFile(file); return false; }}
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
            >
              {uploading ? 'جاري الرفع...' : extracting ? 'جاري الاستخراج...' : 'رفع واستخراج'}
            </Button>
          </Col>
        </Row>

        {file && (
          <Alert message={`الملف المختار: ${file.name}`} type="info" style={{ marginTop: 12 }} />
        )}
      </Card>

      {catalogId && (
        <>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={8}>
              <Card><Statistic title="قيد المراجعة" value={pendingCount} valueStyle={{ color: '#faad14' }} /></Card>
            </Col>
            <Col span={8}>
              <Card><Statistic title="مؤكد" value={confirmedCount} valueStyle={{ color: '#52c41a' }} /></Card>
            </Col>
            <Col span={8}>
              <Card>
                <Button type="primary" block icon={<CheckOutlined />} onClick={handleBulkConfirm} disabled={pendingCount === 0}>
                  تأكيد الكل ({pendingCount})
                </Button>
              </Card>
            </Col>
          </Row>

          <h3>البيانات المستخرجة - مراجعة وتأكيد</h3>
          <Table 
            dataSource={extractions} 
            columns={columns} 
            rowKey="id" 
            loading={loadingExtractions}
            scroll={{ x: true }}
            size="small"
          />
        </>
      )}

      {/* Modal تعديل */}
      <Modal title="تعديل البيانات المستخرجة" open={editModalVisible} onCancel={() => setEditModalVisible(false)} footer={null} width={700}>
        <Form form={editForm} onFinish={handleEditSave} layout="vertical">
          <Row gutter={16}>
            <Col span={12}><Form.Item name="extracted_name" label="الاسم" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="extracted_category" label="النوع">
              <Select>
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
              <Select>
                <Option value="stock">Stock</Option>
                <Option value="rx">RX</Option>
                <Option value="both">Both</Option>
              </Select>
            </Form.Item></Col>
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
            <Col span={6}><Form.Item name="extracted_price" label="السعر"><InputNumber style={{ width: '100%' }} /></Form.Item></Col>
          </Row>
          <Button type="primary" htmlType="submit" icon={<SaveOutlined />} block>حفظ التعديلات</Button>
        </Form>
      </Modal>
    </div>
  );
};

export default PDFPreview;
