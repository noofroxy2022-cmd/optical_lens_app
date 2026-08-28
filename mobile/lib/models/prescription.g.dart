// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'prescription.dart';

// **************************************************************************
// TypeAdapterGenerator
// **************************************************************************

class EyePrescriptionAdapter extends TypeAdapter<EyePrescription> {
  @override
  final int typeId = 0;

  @override
  EyePrescription read(BinaryReader reader) {
    final numOfFields = reader.readByte();
    final fields = <int, dynamic>{
      for (int i = 0; i < numOfFields; i++) reader.readByte(): reader.read(),
    };
    return EyePrescription(
      sph: fields[0] as double,
      cyl: fields[1] as double,
      axis: fields[2] as int,
      add: fields[3] as double,
    );
  }

  @override
  void write(BinaryWriter writer, EyePrescription obj) {
    writer
      ..writeByte(4)
      ..writeByte(0)
      ..write(obj.sph)
      ..writeByte(1)
      ..write(obj.cyl)
      ..writeByte(2)
      ..write(obj.axis)
      ..writeByte(3)
      ..write(obj.add);
  }

  @override
  int get hashCode => typeId.hashCode;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is EyePrescriptionAdapter &&
          runtimeType == other.runtimeType &&
          typeId == other.typeId;
}

class PrescriptionAdapter extends TypeAdapter<Prescription> {
  @override
  final int typeId = 1;

  @override
  Prescription read(BinaryReader reader) {
    final numOfFields = reader.readByte();
    final fields = <int, dynamic>{
      for (int i = 0; i < numOfFields; i++) reader.readByte(): reader.read(),
    };
    return Prescription(
      id: fields[0] as int?,
      customerName: fields[1] as String?,
      od: fields[2] as EyePrescription,
      os: fields[3] as EyePrescription,
      pd: fields[4] as double?,
      notes: fields[5] as String?,
      createdAt: fields[6] as DateTime?,
      isSynced: fields[7] as bool,
    );
  }

  @override
  void write(BinaryWriter writer, Prescription obj) {
    writer
      ..writeByte(8)
      ..writeByte(0)
      ..write(obj.id)
      ..writeByte(1)
      ..write(obj.customerName)
      ..writeByte(2)
      ..write(obj.od)
      ..writeByte(3)
      ..write(obj.os)
      ..writeByte(4)
      ..write(obj.pd)
      ..writeByte(5)
      ..write(obj.notes)
      ..writeByte(6)
      ..write(obj.createdAt)
      ..writeByte(7)
      ..write(obj.isSynced);
  }

  @override
  int get hashCode => typeId.hashCode;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is PrescriptionAdapter &&
          runtimeType == other.runtimeType &&
          typeId == other.typeId;
}

class LensModelAdapter extends TypeAdapter<LensModel> {
  @override
  final int typeId = 2;

  @override
  LensModel read(BinaryReader reader) {
    final numOfFields = reader.readByte();
    final fields = <int, dynamic>{
      for (int i = 0; i < numOfFields; i++) reader.readByte(): reader.read(),
    };
    return LensModel(
      id: fields[0] as int,
      name: fields[1] as String,
      companyName: fields[2] as String,
      lensType: fields[3] as String,
      material: fields[4] as String,
      sphMin: fields[5] as double,
      sphMax: fields[6] as double,
      cylMin: fields[7] as double,
      cylMax: fields[8] as double,
      addMin: fields[9] as double?,
      addMax: fields[10] as double?,
      index: fields[11] as double,
      antiReflective: fields[12] as bool,
      photochromic: fields[13] as bool,
      blueLightFilter: fields[14] as bool,
      uvProtection: fields[15] as bool,
      price: fields[16] as double,
      description: fields[17] as String?,
      cachedAt: fields[18] as DateTime?,
    );
  }

  @override
  void write(BinaryWriter writer, LensModel obj) {
    writer
      ..writeByte(19)
      ..writeByte(0)
      ..write(obj.id)
      ..writeByte(1)
      ..write(obj.name)
      ..writeByte(2)
      ..write(obj.companyName)
      ..writeByte(3)
      ..write(obj.lensType)
      ..writeByte(4)
      ..write(obj.material)
      ..writeByte(5)
      ..write(obj.sphMin)
      ..writeByte(6)
      ..write(obj.sphMax)
      ..writeByte(7)
      ..write(obj.cylMin)
      ..writeByte(8)
      ..write(obj.cylMax)
      ..writeByte(9)
      ..write(obj.addMin)
      ..writeByte(10)
      ..write(obj.addMax)
      ..writeByte(11)
      ..write(obj.index)
      ..writeByte(12)
      ..write(obj.antiReflective)
      ..writeByte(13)
      ..write(obj.photochromic)
      ..writeByte(14)
      ..write(obj.blueLightFilter)
      ..writeByte(15)
      ..write(obj.uvProtection)
      ..writeByte(16)
      ..write(obj.price)
      ..writeByte(17)
      ..write(obj.description)
      ..writeByte(18)
      ..write(obj.cachedAt);
  }

  @override
  int get hashCode => typeId.hashCode;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is LensModelAdapter &&
          runtimeType == other.runtimeType &&
          typeId == other.typeId;
}
