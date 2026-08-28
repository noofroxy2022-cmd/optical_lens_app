import 'package:hive/hive.dart';

part 'prescription.g.dart';

@HiveType(typeId: 0)
class EyePrescription extends HiveObject {
  @HiveField(0)
  double sph;
  @HiveField(1)
  double cyl;
  @HiveField(2)
  int axis;
  @HiveField(3)
  double add;

  EyePrescription({
    required this.sph,
    this.cyl = 0.0,
    this.axis = 0,
    this.add = 0.0,
  });

  Map<String, dynamic> toJson() => {
    'sph': sph,
    'cyl': cyl,
    'axis': axis,
    'add': add,
  };

  factory EyePrescription.fromJson(Map<String, dynamic> json) => EyePrescription(
    sph: (json['sph'] as num).toDouble(),
    cyl: (json['cyl'] as num?)?.toDouble() ?? 0.0,
    axis: json['axis'] as int? ?? 0,
    add: (json['add'] as num?)?.toDouble() ?? 0.0,
  );
}

@HiveType(typeId: 1)
class Prescription extends HiveObject {
  @HiveField(0)
  int? id;
  @HiveField(1)
  String? customerName;
  @HiveField(2)
  EyePrescription od;
  @HiveField(3)
  EyePrescription os;
  @HiveField(4)
  double? pd;
  @HiveField(5)
  String? notes;
  @HiveField(6)
  DateTime createdAt;
  @HiveField(7)
  bool isSynced;

  Prescription({
    this.id,
    this.customerName,
    required this.od,
    required this.os,
    this.pd,
    this.notes,
    DateTime? createdAt,
    this.isSynced = false,
  }) : createdAt = createdAt ?? DateTime.now();

  Map<String, dynamic> toJson() => {
    'customer_name': customerName,
    'od': od.toJson(),
    'os': os.toJson(),
    'pd': pd,
    'notes': notes,
  };
}

@HiveType(typeId: 2)
class LensModel extends HiveObject {
  @HiveField(0)
  int id;
  @HiveField(1)
  String name;
  @HiveField(2)
  String companyName;
  @HiveField(3)
  String lensType;
  @HiveField(4)
  String material;
  @HiveField(5)
  double sphMin;
  @HiveField(6)
  double sphMax;
  @HiveField(7)
  double cylMin;
  @HiveField(8)
  double cylMax;
  @HiveField(9)
  double? addMin;
  @HiveField(10)
  double? addMax;
  @HiveField(11)
  double index;
  @HiveField(12)
  bool antiReflective;
  @HiveField(13)
  bool photochromic;
  @HiveField(14)
  bool blueLightFilter;
  @HiveField(15)
  bool uvProtection;
  @HiveField(16)
  double price;
  @HiveField(17)
  String? description;
  @HiveField(18)
  DateTime cachedAt;

  LensModel({
    required this.id,
    required this.name,
    required this.companyName,
    required this.lensType,
    required this.material,
    required this.sphMin,
    required this.sphMax,
    required this.cylMin,
    required this.cylMax,
    this.addMin,
    this.addMax,
    required this.index,
    this.antiReflective = false,
    this.photochromic = false,
    this.blueLightFilter = false,
    this.uvProtection = false,
    required this.price,
    this.description,
    DateTime? cachedAt,
  }) : cachedAt = cachedAt ?? DateTime.now();

  factory LensModel.fromApi(Map<String, dynamic> json) => LensModel(
    id: json['id'],
    name: json['name'],
    companyName: json['company']?['name'] ?? 'Unknown',
    lensType: json['lens_type'],
    material: json['material'],
    sphMin: (json['sph_min'] as num).toDouble(),
    sphMax: (json['sph_max'] as num).toDouble(),
    cylMin: (json['cyl_min'] as num).toDouble(),
    cylMax: (json['cyl_max'] as num).toDouble(),
    addMin: json['add_min'] != null ? (json['add_min'] as num).toDouble() : null,
    addMax: json['add_max'] != null ? (json['add_max'] as num).toDouble() : null,
    index: (json['index'] as num).toDouble(),
    antiReflective: json['anti_reflective'] ?? false,
    photochromic: json['photochromic'] ?? false,
    blueLightFilter: json['blue_light_filter'] ?? false,
    uvProtection: json['uv_protection'] ?? false,
    price: (json['price'] as num).toDouble(),
    description: json['description'],
  );
}
