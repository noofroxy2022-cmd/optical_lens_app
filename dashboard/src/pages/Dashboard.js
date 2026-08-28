import React, { useEffect, useState } from 'react';
import { Card, Row, Col, Statistic, Table, Tag } from 'antd';
import {
  EyeOutlined,
  BuildOutlined,
  FileTextOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import { companyAPI, lensAPI, prescriptionAPI } from '../services/api';

const Dashboard = () => {
  const [stats, setStats] = useState({ companies: 0, lenses: 0, prescriptions: 0 });
  const [recentPrescriptions, setRecentPrescriptions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [companies, lenses, prescriptions] = await Promise.all([
        companyAPI.getAll(),
        lensAPI.getAll(),
        prescriptionAPI.getAll(),
      ]);

      setStats({
        companies: companies.data.length,
        lenses: lenses.data.length,
        prescriptions: prescriptions.data.length,
      });

      setRecentPrescriptions(prescriptions.data.slice(0, 5));
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
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
      render: (v) => new Date(v).toLocaleDateString('ar-SA'),
    },
  ];

  return (
    <div>
      <h1 style={{ marginBottom: '24px' }}>📊 لوحة التحكم</h1>

      <Row gutter={16}>
        <Col span={8}>
          <Card>
            <Statistic
              title="الشركات"
              value={stats.companies}
              prefix={<BuildOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="العدسات"
              value={stats.lenses}
              prefix={<EyeOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="الوصفات"
              value={stats.prescriptions}
              prefix={<FileTextOutlined />}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
      </Row>

      <Card title="آخر الوصفات" style={{ marginTop: '24px' }} loading={loading}>
        <Table
          dataSource={recentPrescriptions}
          columns={columns}
          rowKey="id"
          pagination={false}
          size="small"
        />
      </Card>
    </div>
  );
};

export default Dashboard;
