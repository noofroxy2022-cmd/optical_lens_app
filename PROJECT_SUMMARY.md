# ✅ Optical Lens Matcher - النسخة النهائية V3.0

## 📋 ما تم إنجازه بالكامل

### 1. 🔧 Backend (FastAPI)

#### قاعدة البيانات (Database Schema)
| الجدول | الوظيفة |
|--------|---------|
| **Company** | الشركات (is_active, is_deleted, Toggle) |
| **Catalog** | ملفات PDF المرفوعة |
| **CatalogExtraction** | **Preview & Confirm** - البيانات المستخرجة بانتظار المراجعة |
| **LensModel** | نماذج العدسات (category, features) |
| **LensVariant** | متغيرات العدسة (material, index, availability, **design_type, is_aspherical**) |
| **PowerRange** | نطاقات القوة (sph, cyl, add, max_cyl_for_high_sph) |
| **Prescription** | الوصفات (**od_sph_original, od_sph (transposed), transposition_applied**) |
| **MatchResult** | نتائج المطابقة |

#### المنطق البصري (Optics Matching Logic)
| الميزة | التفاصيل |
|--------|----------|
| **Transposition** | تحويل CYL الموجب تلقائياً إلى السلبي + Axis ± 90 |
| **Index Recommendation** | 1.50→1.56→1.60→1.61→1.67→1.74 بناءً على SPH |
| **Aspherical Preference** | تفضيل Aspherical عند SPH>3 أو CYL>2 أو المجموع>4 |
| **Stock vs RX** | تصنيف واضح مع تفضيل Stock |
| **ADD Support** | توجيه Progressive/Bifocal تلقائياً |

#### PDF Hybrid Parser
| الميزة | التفاصيل |
|--------|----------|
| **pdfplumber** | استخراج الجداول المنظمة |
| **Google Vision** | استخراج الجداول الملونة/المعقدة |
| **Color Detection** | اكتشاف Stock (أخضر) vs RX (أحمر) |
| **Preview & Confirm** | حفظ في CatalogExtraction → مراجعة → تأكيد/رفض |
| **Bulk Confirm** | تأكيد جميع البيانات بنقرة واحدة |

### 2. 🖥️ Dashboard (React + Ant Design)

| الصفحة | الوظيفة |
|--------|---------|
| **Dashboard** | إحصائيات + آخر الوصفات |
| **Companies** | CRUD + Toggle Active/Inactive + Soft/Hard Delete + Logo Upload |
| **LensModels** | إدارة نماذج العدسات + Variants + PowerRanges |
| **Prescriptions** | عرض تفاصيل الوصفات + OCR confidence |
| **PDFPreview** | **رفع PDF → استخراج → معاينة → تعديل → تأكيد/رفض → Bulk Confirm** |

### 3. 📱 Flutter Mobile

| الملف | الوظيفة |
|-------|---------|
| `models/prescription.dart` | Hive models للـ Offline Mode |
| `services/offline_service.dart` | تخزين محلي + مزامنة |
| `services/api_service.dart` | API مع fallback offline |
| `screens/` | 5 شاشات كاملة |

---

## 🚀 API Endpoints

### Companies
- `POST /companies/` - إضافة شركة
- `GET /companies/?include_inactive=true` - قائمة الشركات
- `PUT /companies/{id}` - تحديث
- `POST /companies/{id}/toggle-active` - تفعيل/تعطيل
- `DELETE /companies/{id}?hard_delete=true` - حذف

### Lens Models
- `POST /lens-models/` - إضافة نموذج
- `GET /lens-models/` - قائمة النماذج
- `POST /lens-models/{id}/variants` - إضافة variant
- `POST /lens-models/{id}/power-ranges` - إضافة نطاق قوة

### Prescriptions
- `POST /prescriptions/` - إنشاء وصفة (مع Transposition تلقائي)
- `POST /prescriptions/upload` - OCR + Transposition
- `POST /prescriptions/{id}/match` - مطابقة مع Index + Aspherical recommendations
- `GET /prescriptions/{id}/recommendations` - التوصيات البصرية فقط

### PDF Import
- `POST /pdf-import/upload` - رفع PDF
- `POST /pdf-import/preview/{catalog_id}` - معاينة
- `POST /pdf-import/extract/{catalog_id}` - استخراج وحفظ في Preview
- `GET /pdf-import/extractions/{catalog_id}` - جلب البيانات المستخرجة
- `PUT /pdf-import/extractions/{id}` - تعديل
- `POST /pdf-import/extractions/{id}/confirm` - تأكيد ونقل إلى DB
- `POST /pdf-import/extractions/{id}/reject` - رفض
- `POST /pdf-import/bulk-confirm/{catalog_id}` - تأكيد الكل

---

## 🐳 Docker Compose

```bash
cd optical_lens_app
docker-compose up -d

# Backend: http://localhost:8000/docs
# Dashboard: http://localhost:3000
# Database: PostgreSQL on port 5432
```

---

## 📱 بناء APK

```bash
cd optical_lens_app/mobile
flutter pub get
flutter build apk --split-per-abi
```

---

## 🔑 إعداد Google Vision API

1. Google Cloud Console → مشروع جديد
2. فعّل Vision API
3. Service Account + JSON Key
4. `export GOOGLE_APPLICATION_CREDENTIALS=backend/credentials/google-credentials.json`

---

## ⚡ الميزات المتقدمة المُفعّلة

| الميزة | الحالة |
|--------|--------|
| ✅ Transposition (CYL ±) | تلقائي في Prescription + Matcher |
| ✅ Index Recommendation | 1.50→1.74 بناءً على SPH |
| ✅ Aspherical Preference | تفضيل تلقائي للقوة العالية |
| ✅ Stock vs RX vs BOTH | تصنيف واضح + تفضيل Stock |
| ✅ ADD Support | Progressive/Bifocal تلقائي |
| ✅ PDF Hybrid Parser | pdfplumber + Vision + Color Detection |
| ✅ Preview & Confirm | مراجعة 100% قبل الاعتماد |
| ✅ Bulk Confirm | تأكيد الكل بنقرة واحدة |
| ✅ Dynamic CRUD | إدارة كاملة من Dashboard |
| ✅ Toggle Active/Inactive | فوري في النتائج |
| ✅ Soft/Hard Delete | مرن |
| ✅ Offline Mode | Hive في Flutter |

---

## 📂 تحميل المشروع

[optical_lens_app](sandbox:///mnt/agents/output/optical_lens_app)
