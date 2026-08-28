import 'package:hive_flutter/hive_flutter.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import '../models/prescription.dart';

class OfflineService {
  static final OfflineService _instance = OfflineService._internal();
  factory OfflineService() => _instance;
  OfflineService._internal();

  late Box<LensModel> _lensesBox;
  late Box<Prescription> _prescriptionsBox;
  late Box _settingsBox;

  Future<void> init() async {
    await Hive.initFlutter();
    Hive.registerAdapter(EyePrescriptionAdapter());
    Hive.registerAdapter(PrescriptionAdapter());
    Hive.registerAdapter(LensModelAdapter());

    _lensesBox = await Hive.openBox<LensModel>('lenses');
    _prescriptionsBox = await Hive.openBox<Prescription>('prescriptions');
    _settingsBox = await Hive.openBox('settings');
  }

  // ===== الاتصال =====
  Future<bool> isOnline() async {
    final result = await Connectivity().checkConnectivity();
    return result != ConnectivityResult.none;
  }

  // ===== العدسات =====
  Future<void> cacheLenses(List<LensModel> lenses) async {
    await _lensesBox.clear();
    for (var lens in lenses) {
      await _lensesBox.put(lens.id, lens);
    }
    await _settingsBox.put('lenses_cached_at', DateTime.now().toIso8601String());
  }

  List<LensModel> getCachedLenses() {
    return _lensesBox.values.toList();
  }

  DateTime? getLensesCacheTime() {
    final cached = _settingsBox.get('lenses_cached_at');
    return cached != null ? DateTime.parse(cached) : null;
  }

  bool isCacheValid({Duration maxAge = const Duration(hours: 24)}) {
    final cacheTime = getLensesCacheTime();
    if (cacheTime == null) return false;
    return DateTime.now().difference(cacheTime) < maxAge;
  }

  // ===== الوصفات =====
  Future<void> savePrescription(Prescription prescription) async {
    await _prescriptionsBox.add(prescription);
  }

  List<Prescription> getUnsyncedPrescriptions() {
    return _prescriptionsBox.values.where((p) => !p.isSynced).toList();
  }

  Future<void> markAsSynced(int key) async {
    final prescription = _prescriptionsBox.get(key);
    if (prescription != null) {
      prescription.isSynced = true;
      await prescription.save();
    }
  }

  List<Prescription> getAllPrescriptions() {
    return _prescriptionsBox.values.toList().reversed.toList();
  }

  Future<void> clearCache() async {
    await _lensesBox.clear();
    await _prescriptionsBox.clear();
    await _settingsBox.clear();
  }
}
