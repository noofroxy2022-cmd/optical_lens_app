import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:connectivity_plus/connectivity_plus.dart';
import '../models/prescription.dart';
import 'offline_service.dart';

class ApiService {
  static const String baseUrl = 'http://10.0.2.2:8000';
  static final OfflineService _offline = OfflineService();

  static Future<bool> _isOnline() async {
    final result = await Connectivity().checkConnectivity();
    return result != ConnectivityResult.none;
  }

  // ===== الوصفات =====
  static Future<Map<String, dynamic>> createPrescription(Prescription p) async {
    if (await _isOnline()) {
      try {
        final response = await http.post(
          Uri.parse('$baseUrl/prescriptions/'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(p.toJson()),
        );
        final result = jsonDecode(response.body);
        p.id = result['id'];
        p.isSynced = true;
        await _offline.savePrescription(p);
        return result;
      } catch (e) {
        // fallback للـ offline
        await _offline.savePrescription(p);
        return {'offline': true, 'message': 'حُفظت محلياً - ستُرفع عند الاتصال'};
      }
    } else {
      await _offline.savePrescription(p);
      return {'offline': true, 'message': 'لا يوجد اتصال - حُفظت محلياً'};
    }
  }

  static Future<Map<String, dynamic>> uploadPrescriptionImage(File image) async {
    if (!await _isOnline()) {
      return {'success': false, 'message': 'لا يوجد اتصال بالإنترنت'};
    }
    var request = http.MultipartRequest('POST', Uri.parse('$baseUrl/prescriptions/upload'));
    request.files.add(await http.MultipartFile.fromPath('file', image.path));
    var response = await request.send();
    var responseData = await response.stream.bytesToString();
    return jsonDecode(responseData);
  }

  static Future<Map<String, dynamic>> matchLenses(int prescriptionId, Map<String, dynamic>? filters) async {
    // إذا كان offline، استخدم المطابقة المحلية
    if (!await _isOnline()) {
      return _matchOffline(prescriptionId, filters);
    }

    final response = await http.post(
      Uri.parse('$baseUrl/prescriptions/$prescriptionId/match'),
      headers: {'Content-Type': 'application/json'},
      body: filters != null ? jsonEncode({'filters': filters}) : '{}',
    );
    return jsonDecode(response.body);
  }

  static Future<Map<String, dynamic>> _matchOffline(int prescriptionId, Map<String, dynamic>? filters) async {
    final prescription = _offline.getAllPrescriptions().firstWhere((p) => p.id == prescriptionId);
    final lenses = _offline.getCachedLenses();

    // فلترة محلية بسيطة
    var filtered = lenses.where((l) {
      if (filters == null) return true;
      if (filters['lens_type'] != null && l.lensType != filters['lens_type']) return false;
      if (filters['material'] != null && l.material != filters['material']) return false;
      if (filters['anti_reflective'] == true && !l.antiReflective) return false;
      if (filters['photochromic'] == true && !l.photochromic) return false;
      if (filters['blue_light_filter'] == true && !l.blueLightFilter) return false;
      if (filters['max_price'] != null && l.price > filters['max_price']) return false;
      return true;
    }).toList();

    // مطابقة نطاق القوة
    filtered = filtered.where((l) {
      final odValid = l.sphMin - 0.25 <= prescription.od.sph && prescription.od.sph <= l.sphMax + 0.25;
      final osValid = l.sphMin - 0.25 <= prescription.os.sph && prescription.os.sph <= l.sphMax + 0.25;
      return odValid && osValid;
    }).toList();

    return {
      'prescription': prescription,
      'results': filtered.map((l) => {
        'lens': {
          'id': l.id,
          'name': l.name,
          'company': {'name': l.companyName},
          'index': l.index,
          'price': l.price,
          'anti_reflective': l.antiReflective,
          'photochromic': l.photochromic,
          'blue_light_filter': l.blueLightFilter,
          'uv_protection': l.uvProtection,
        },
        'match_score': 80.0,
        'reason': 'مطابقة offline',
      }).toList(),
      'total_matches': filtered.length,
      'offline': true,
    };
  }

  // ===== الشركات =====
  static Future<List<dynamic>> getCompanies() async {
    if (!await _isOnline()) return [];
    final response = await http.get(Uri.parse('$baseUrl/companies/'));
    return jsonDecode(response.body);
  }

  // ===== العدسات =====
  static Future<void> syncLenses() async {
    if (!await _isOnline()) return;
    try {
      final response = await http.get(Uri.parse('$baseUrl/lenses/'));
      final lenses = jsonDecode(response.body) as List;
      final models = lenses.map((l) => LensModel.fromApi(l)).toList();
      await _offline.cacheLenses(models);
    } catch (e) {
      print('Sync error: $e');
    }
  }

  // ===== رفع الوصفات المعلقة =====
  static Future<void> syncPendingPrescriptions() async {
    if (!await _isOnline()) return;
    final pending = _offline.getUnsyncedPrescriptions();
    for (var p in pending) {
      try {
        final response = await http.post(
          Uri.parse('$baseUrl/prescriptions/'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(p.toJson()),
        );
        if (response.statusCode == 200 || response.statusCode == 201) {
          p.isSynced = true;
          await p.save();
        }
      } catch (e) {
        print('Sync prescription error: $e');
      }
    }
  }
}
