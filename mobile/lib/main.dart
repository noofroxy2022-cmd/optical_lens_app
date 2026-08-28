import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:google_fonts/google_fonts.dart'; // مكتبة الخطوط لضمان دعم العربية على الويب
import 'services/offline_service.dart';
import 'services/api_service.dart';
import 'screens/home_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  // تهيئة الخدمات المحلية والشبكية بشكل آمن لتفادي تعليق التطبيق
  try {
    await OfflineService().init();
    await ApiService.syncLenses();
  } catch (e) {
    debugPrint('تنبيه أثناء تهيئة الخدمات: $e');
  }

  runApp(const OpticalLensApp());
}

class OpticalLensApp extends StatelessWidget {
  const OpticalLensApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'مطابقة العدسات',
      debugShowCheckedModeBanner: false,

      // ضبط إعدادات اللغة العربية والاتجاه من اليمين إلى اليسار (RTL)
      locale: const Locale('ar', 'EG'),
      supportedLocales: const [
        Locale('ar', 'EG'),
        Locale('en', 'US'),
      ],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],

      // ثيم التطبيق وضبط الخط ليدعم اللغة العربية على الويب حديثاً
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF1976D2),
          brightness: Brightness.light,
        ),
        textTheme: GoogleFonts.cairoTextTheme(
          Theme.of(context).textTheme,
        ),
        useMaterial3: true,
      ),

      home: const HomeScreen(),
    );
  }
}