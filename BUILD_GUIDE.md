# 🚀 دليل بناء APK وتشغيل التطبيق

## المتطلبات
- Flutter SDK 3.0+
- Android Studio + SDK
- JDK 17
- Git

## 1. تثبيت Flutter
```bash
git clone https://github.com/flutter/flutter.git -b stable
export PATH="$PATH:`pwd`/flutter/bin"
flutter doctor
```

## 2. إعداد المشروع
```bash
cd optical_lens_app/mobile
flutter pub get
```

## 3. تعديل عنوان الـ API
افتح `lib/services/api_service.dart` وعدل `baseUrl`:
- للمحاكي: `http://10.0.2.2:8000`
- للجهاز الحقيقي: `http://YOUR_SERVER_IP:8000`

## 4. بناء APK
```bash
# APK عادي (debug)
flutter build apk

# APK مقسم (لأحجام أصغر)
flutter build apk --split-per-abi

# AAB للـ Play Store
flutter build appbundle
```

## 5. تثبيت APK على الجهاز
```bash
# توصيل الجهاز عبر USB (تفعيل USB Debugging)
flutter install

# أو نقل الملف يدوياً
# الملف موجود في: build/app/outputs/flutter-apk/app-release.apk
```

## 6. تشغيل Backend
```bash
cd ../backend

# الخيار أ: Docker (موصى به)
docker-compose up -d

# الخيار ب: محلي
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python seed_data.py
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 7. تشغيل Dashboard
```bash
cd ../dashboard
npm install
npm start
# أو Docker:
docker-compose up -d dashboard
```

## ⚙️ إعداد Google Vision API
1. أنشئ مشروع في Google Cloud Console
2. فعّل Vision API
3. أنشئ Service Account + JSON Key
4. ضع الملف في `backend/credentials/google-credentials.json`
5. عيّن متغير البيئة: `export GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/google-credentials.json`

## 📱 Offline Mode
- العدسات تُحفظ تلقائياً في الجهاز عند أول تشغيل
- الوصفات تُحفظ محلياً إذا لم يكن هناك اتصال
- اضغط زر "مزامنة" في الإعدادات لرفع الوصفات المعلقة
