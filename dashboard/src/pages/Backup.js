import React, { useEffect, useState } from 'react';
import { Table, Button, message, Card, Tag, Alert, Space, Modal, List } from 'antd';
import { CloudUploadOutlined, ReloadOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { backupAPI } from '../services/api';

const errMsg = (error, fallback) => {
  const d = error?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (d && typeof d === 'object') return d.message || JSON.stringify(d);
  return fallback;
};

const fmtSize = (n) => (n == null ? '—' : n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`);

const Backup = () => {
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [restoreInfo, setRestoreInfo] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await backupAPI.list();
      setInfo(r.data);
    } catch (e) {
      message.error(errMsg(e, 'فشل تحميل النسخ الاحتياطية'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const backupNow = async () => {
    setBusy(true);
    try {
      const r = await backupAPI.now();
      message.success(`تم إنشاء نسخة: ${r.data.backup?.name}`);
      await load();
    } catch (e) {
      message.error(errMsg(e, 'فشل إنشاء النسخة'));
    } finally {
      setBusy(false);
    }
  };

  // Restore is OFFLINE ONLY - this just fetches and shows the manual steps.
  // The server never replaces the live DB while running.
  const showRestoreSteps = async (name) => {
    setBusy(true);
    try {
      const r = await backupAPI.restore(name);
      setRestoreInfo(r.data);
    } catch (e) {
      message.error(errMsg(e, 'تعذّر جلب تعليمات الاسترجاع'));
    } finally {
      setBusy(false);
    }
  };

  const columns = [
    { title: 'الاسم', dataIndex: 'name', key: 'name' },
    { title: 'الحجم', dataIndex: 'size_bytes', key: 'size', render: fmtSize },
    { title: 'التاريخ', dataIndex: 'created_at', key: 'created_at' },
    {
      title: 'استرجاع (دون اتصال)',
      key: 'restore',
      render: (_, r) => (
        <Button size="small" icon={<InfoCircleOutlined />} onClick={() => showRestoreSteps(r.name)}>
          خطوات الاسترجاع
        </Button>
      ),
    },
  ];

  return (
    <div>
      <h1 style={{ marginBottom: 16 }}>💾 النسخ الاحتياطي</h1>

      {info && !info.is_sqlite && (
        <Alert type="warning" showIcon style={{ marginBottom: 16 }}
          message="قاعدة البيانات الحالية ليست SQLite — النسخ الاحتياطي التلقائي غير مُفعّل." />
      )}

      <Card size="small" style={{ marginBottom: 16 }}>
        <Space direction="vertical" size={4}>
          <div>مجلد النسخ: <Tag>{info?.backup_dir || '—'}</Tag></div>
          <div>سياسة الاحتفاظ: آخر <b>{info?.keep ?? 7}</b> نسخ — نسخة يومية تلقائية.</div>
          <div style={{ color: '#888', fontSize: 12 }}>
            النسخ تُؤخذ عبر واجهة SQLite الآمنة ولا توقف أو تُفسد قاعدة البيانات أثناء العمل.
          </div>
        </Space>
        <div style={{ marginTop: 12 }}>
          <Button type="primary" icon={<CloudUploadOutlined />} loading={busy} onClick={backupNow} style={{ marginLeft: 8 }}>
            نسخ احتياطي الآن
          </Button>
          <Button icon={<ReloadOutlined />} onClick={load}>تحديث</Button>
        </div>
      </Card>

      <Alert type="warning" showIcon style={{ marginBottom: 12 }}
        message="الاسترجاع يتم دون اتصال فقط"
        description="لا يستبدل الخادم قاعدة البيانات الحيّة أثناء عمله. أوقف الخادم، استبدل الملف يدوياً، ثم أعد التشغيل — اضغط «خطوات الاسترجاع» لعرض الخطوات." />

      <Table
        dataSource={info?.backups || []}
        columns={columns}
        rowKey="name"
        loading={loading}
        size="small"
        pagination={false}
      />

      <Modal
        title="خطوات الاسترجاع (دون اتصال)"
        open={!!restoreInfo}
        onCancel={() => setRestoreInfo(null)}
        footer={<Button onClick={() => setRestoreInfo(null)}>إغلاق</Button>}
        width={680}
      >
        {restoreInfo && (
          <>
            <Alert
              type={restoreInfo.chosen_backup_ok ? 'info' : 'error'}
              showIcon
              style={{ marginBottom: 12 }}
              message={restoreInfo.message}
              description={restoreInfo.chosen_backup_ok
                ? `النسخة المختارة سليمة: ${restoreInfo.chosen_backup}`
                : `تحذير: النسخة المختارة (${restoreInfo.chosen_backup}) لم تجتز فحص السلامة.`}
            />
            <List
              size="small"
              header={<b>الخطوات</b>}
              bordered
              dataSource={restoreInfo.steps || []}
              renderItem={(s, i) => <List.Item>{i + 1}. {s}</List.Item>}
            />
            <div style={{ marginTop: 12, fontSize: 12, color: '#888' }}>
              <div>ملف النسخة: <Tag>{restoreInfo.backup_path}</Tag></div>
              <div>قاعدة البيانات الحيّة: <Tag>{restoreInfo.live_db_path}</Tag></div>
            </div>
          </>
        )}
      </Modal>
    </div>
  );
};

export default Backup;
