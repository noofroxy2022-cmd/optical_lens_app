# 🔬 Optical Lens Matcher

تطبيق متكامل لمطابقة العدسات البصرية مع الوصفات الطبية، يدعم OCR ووضع Offline ولوحة تحكم سحابية.

## 📁 هيكل المشروع

```
optical_lens_app/
├── backend/          # FastAPI + PostgreSQL + Google Vision OCR
├── mobile/           # Flutter (Android + iOS)
├── dashboard/        # React + Ant Design
└── docker-compose.yml
```

## ✨ المميزات

| الميزة | الوصف |
|--------|-------|
| 📸 OCR | استخراج الوصفة من الصورة (Google Vision API) |
| 🔍 مطابقة ذكية | محرك scoring متقدم للعدسات |
| 📴 Offline | عمل بدون إنترنت مع تخزين محلي |
| 🌐 Dashboard | إدارة الشركات والكتالوجات |
| 🐳 Docker | نشر بنقرة واحدة |

## 🚀 Quick Start

```bash
# 1. استنساخ
# 2. Docker
sudo docker-compose up -d

# 3. Dashboard متاح على: http://localhost:3000
# 4. API متاح على: http://localhost:8000/docs
```

## 📱 بناء APK

راجع [BUILD_GUIDE.md](BUILD_GUIDE.md)

## 🔧 API Endpoints

- `POST /prescriptions/` - إنشاء وصفة
- `POST /prescriptions/upload` - OCR من صورة
- `POST /prescriptions/{id}/match` - مطابقة العدسات
- `GET /lenses/` - قائمة العدسات
- `GET /companies/` - قائمة الشركات

## 📄 الترخيص
MIT License
