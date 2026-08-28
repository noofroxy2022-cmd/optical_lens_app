import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../services/offline_service.dart';
import '../models/prescription.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final OfflineService _offlineService = OfflineService();
  
  bool _isLoading = false;
  bool _isOnline = false;
  List<dynamic> _matchResults = [];

  // متحكمات إدخال قراءات العين اليمنى (OD)
  final TextEditingController _odSphController = TextEditingController(text: '0.00');
  final TextEditingController _odCylController = TextEditingController(text: '0.00');
  final TextEditingController _odAxisController = TextEditingController(text: '0');

  // متحكمات إدخال قراءات العين اليسرى (OS)
  final TextEditingController _osSphController = TextEditingController(text: '0.00');
  final TextEditingController _osCylController = TextEditingController(text: '0.00');
  final TextEditingController _osAxisController = TextEditingController(text: '0');

  @override
  void initState() {
    super.initState();
    _checkStatusAndSync();
  }

  Future<void> _checkStatusAndSync() async {
    setState(() => _isLoading = true);
    
    final online = await _offlineService.isOnline();
    if (online) {
      await ApiService.syncLenses();
      await ApiService.syncPendingPrescriptions();
    }
    
    setState(() {
      _isOnline = online;
      _isLoading = false;
    });
  }

  Future<void> _processMatching() async {
    setState(() => _isLoading = true);

    try {
      final od = EyePrescription(
        sph: double.tryParse(_odSphController.text) ?? 0.0,
        cyl: double.tryParse(_odCylController.text) ?? 0.0,
        axis: int.tryParse(_odAxisController.text) ?? 0,
      );

      final os = EyePrescription(
        sph: double.tryParse(_osSphController.text) ?? 0.0,
        cyl: double.tryParse(_osCylController.text) ?? 0.0,
        axis: int.tryParse(_osAxisController.text) ?? 0,
      );

      final prescription = Prescription(
        od: od,
        os: os,
        createdAt: DateTime.now(),
      );

      final result = await ApiService.createPrescription(prescription);
      
      if (prescription.id != null) {
        final matchResponse = await ApiService.matchLenses(prescription.id!, null);
        setState(() {
          _matchResults = matchResponse['results'] ?? [];
        });
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('حدث خطأ أثناء المطابقة: $e')),
      );
    } finally {
      setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('نظام مطابقة العدسات البصرية'),
        centerTitle: true,
        actions: [
          IconButton(
            icon: const Icon(Icons.sync),
            onPressed: _checkStatusAndSync,
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : SingleChildScrollView(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // شريط حالة الاتصال
                  Container(
                    padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
                    decoration: BoxDecoration(
                      color: _isOnline ? Colors.green.shade100 : Colors.amber.shade100,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Row(
                      children: [
                        Icon(
                          _isOnline ? Icons.wifi : Icons.wifi_off,
                          color: _isOnline ? Colors.green.shade800 : Colors.amber.shade900,
                        ),
                        const SizedBox(width: 10),
                        Text(
                          _isOnline ? 'متصل بالشبكة (Online)' : 'يعمل بدون اتصال (Offline Mode)',
                          style: TextStyle(
                            color: _isOnline ? Colors.green.shade900 : Colors.amber.shade900,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 20),

                  // إدخال المقاسات
                  const Text('بيانات الوصفة الطبية (Prescription)', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 10),
                  
                  // العين اليمنى OD
                  _buildEyeInputSection('العين اليمنى (OD)', _odSphController, _odCylController, _odAxisController),
                  const SizedBox(height: 15),

                  // العين اليسرى OS
                  _buildEyeInputSection('العين اليسرى (OS)', _osSphController, _osCylController, _osAxisController),
                  const SizedBox(height: 20),

                  ElevatedButton.icon(
                    onPressed: _processMatching,
                    icon: const Icon(Icons.search),
                    label: const Text('بدء مطابقة العدسات', style: TextStyle(fontSize: 16)),
                    style: ElevatedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 14),
                    ),
                  ),
                  const SizedBox(height: 25),

                  // نتائج المطابقة
                  if (_matchResults.isNotEmpty) ...[
                    const Text('العدسات المطابقة:', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 10),
                    ListView.builder(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      itemCount: _matchResults.length,
                      itemBuilder: (context, index) {
                        final item = _matchResults[index];
                        final lens = item['lens'];
                        return Card(
                          margin: const EdgeInsets.only(bottom: 10),
                          child: ListTile(
                            leading: CircleAvatar(child: Text('${lens['index'] ?? ''}')),
                            title: Text(lens['name'] ?? 'عدسة'),
                            subtitle: Text('الشركة: ${lens['company']?['name'] ?? '-'} | السعر: ${lens['price']}'),
                            trailing: Text('%${item['match_score'] ?? 0}', style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.blue)),
                          ),
                        );
                      },
                    ),
                  ]
                ],
              ),
            ),
    );
  }

  Widget _buildEyeInputSection(String title, TextEditingController sph, TextEditingController cyl, TextEditingController axis) {
    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(12.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(child: TextField(controller: sph, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'SPH'))),
                const SizedBox(width: 8),
                Expanded(child: TextField(controller: cyl, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'CYL'))),
                const SizedBox(width: 8),
                Expanded(child: TextField(controller: axis, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'AXIS'))),
              ],
            ),
          ],
        ),
      ),
    );
  }
}