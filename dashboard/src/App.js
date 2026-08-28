import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout, Menu } from 'antd';
import {
  DashboardOutlined,
  EyeOutlined,
  BuildOutlined,
  FileTextOutlined,
  FilePdfOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import Dashboard from './pages/Dashboard';
import Companies from './pages/Companies';
import LensModels from './pages/LensModels';
import Prescriptions from './pages/Prescriptions';
import PDFPreview from './pages/PDFPreview';

const { Sider, Content } = Layout;

function App() {
  const menuItems = [
    { key: '/', icon: <DashboardOutlined />, label: 'الرئيسية' },
    { key: '/companies', icon: <BuildOutlined />, label: 'الشركات' },
    { key: '/lens-models', icon: <EyeOutlined />, label: 'نماذج العدسات' },
    { key: '/prescriptions', icon: <FileTextOutlined />, label: 'الوصفات' },
    { key: '/pdf-preview', icon: <FilePdfOutlined />, label: 'استيراد PDF' },
  ];

  return (
    <BrowserRouter>
      <Layout style={{ minHeight: '100vh' }}>
        <Sider theme="dark" width={220}>
          <div style={{ padding: '16px', color: '#fff', fontSize: '18px', fontWeight: 'bold', textAlign: 'center' }}>
            ⚡ Optical Lens
          </div>
          <Menu
            theme="dark"
            mode="inline"
            defaultSelectedKeys={['/']}
            items={menuItems.map(item => ({
              key: item.key,
              icon: item.icon,
              label: <a href={item.key} style={{ color: 'inherit' }}>{item.label}</a>,
            }))}
          />
        </Sider>
        <Layout>
          <Content style={{ margin: '24px', padding: '24px', background: '#fff', borderRadius: '8px' }}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/companies" element={<Companies />} />
              <Route path="/lens-models" element={<LensModels />} />
              <Route path="/prescriptions" element={<Prescriptions />} />
              <Route path="/pdf-preview" element={<PDFPreview />} />
            </Routes>
          </Content>
        </Layout>
      </Layout>
    </BrowserRouter>
  );
}

export default App;
