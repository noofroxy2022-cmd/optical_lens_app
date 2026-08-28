import React from 'react';
import ReactDOM from 'react-dom/client';
import { ConfigProvider } from 'antd';
import arEG from 'antd/locale/ar_EG';
import App from './App';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <ConfigProvider locale={arEG} direction="rtl">
    <App />
  </ConfigProvider>
);
