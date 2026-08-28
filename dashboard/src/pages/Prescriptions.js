import React, { useEffect, useState } from 'react';
import { Table, Button, Modal, Descriptions, Tag, message, Popconfirm } from 'antd';
import { EyeOutlined, DeleteOutlined } from '@ant-design/icons';
import { prescriptionAPI } from '../services/api';

const Prescriptions = () => {
  const [prescriptions, setPrescriptions] = useState([]);
  const [selected, setSelected] = useState(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadPrescriptions();
  }, []);

  const loadPrescriptions = async () => {
    setLoading(true);
    try {
      const res = await prescriptionAPI.getAll();
      setPrescriptions(res.data);
    } catch (error) {
      message.error('فشل التحميل');
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
      message.error('فشل الحذف');
    }
  };

  const viewDetails = (record) => {
    setSelected(record);
    setModalVisible(true);
  };

  const columns = [
    { title: 'العميل', dataIndex: 'customer_name', key: 'customer_name', render: (v) => v || '—' },
    { title: 'OD SPH', dataIndex: 'od_sph', key: 'od_sph' },
    { title: 'OS SPH', dataIndex: 'os_sph', key: 'os_sph' },
    { title: 'PD', dataIndex: 'pd', key: 'pd', render: (v) => v || '—' },
    {
      title: 'OCR',
      dataIndex: 'ocr_confidence',
      key: 'ocr',
      render: (v) => v ? <Tag color="green">{v.toFixed(1)}%</Tag> : <Tag>يدوي</Tag>,
    },
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

  return (
    <div>
      <h1 style={{ marginBottom: '16px' }}>📝 الوصفات الطبية</h1>
      <Table dataSource={prescriptions} columns={columns} rowKey="id" loading={loading} />

      <Modal
        title="تفاصيل الوصفة"
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        footer={null}
        width={600}
      >
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
            <Descriptions.Item label="OCR Confidence">{selected.ocr_confidence?.toFixed(1) || '—'}%</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  );
};

export default Prescriptions;
