import "dart:async";
import "dart:convert";
import "dart:typed_data";

import "package:flet/flet.dart";
import "package:flutter/foundation.dart";
import "package:flutter_blue_plus/flutter_blue_plus.dart";

class FletBleBridgeService extends FletService {
  FletBleBridgeService({required super.control}) {
    control.addInvokeMethodListener(_invokeMethod);
  }

  StreamSubscription<List<int>>? _notifySub;
  BluetoothDevice? _device;
  int _notifyHexLogsLeft = 0;

  /// Console: always (Android: `adb logcat | grep flet_ble`). Python: only if `bridge_debug`.
  void _log(String msg) {
    debugPrint("[flet_ble_bridge] $msg");
    final verbose = control.getBool("bridge_debug", false) ?? false;
    if (verbose) {
      control.triggerEventWithoutSubscribers("bridge_log", {"message": msg});
    }
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    _log("invoke $name args=$args");
    switch (name) {
      case "connect":
        final mac = args["mac"] as String?;
        if (mac == null || mac.isEmpty) {
          _emitStatus("connect: falta MAC");
          return false;
        }
        final ok = await _connect(mac);
        return ok;
      case "disconnect":
        await _disconnect();
        return true;
      case "scan":
        final target = (args["target_name"] as String?) ?? "";
        final ms = (args["timeout_ms"] as num?)?.toInt() ?? 10000;
        return await _scan(target, ms);
      default:
        return null;
    }
  }

  String _charUuid() =>
      control.getString("char_uuid", "12345678-1234-5678-1234-56789abcdef1")!;

  /// BLE plugins sometimes surface Java/Kotlin bytes as signed [-128,127]. Normalize
  /// to unsigned before UTF-8 decode (matches Pyjnius `bytes(raw).decode` / Bleak).
  String _notifyBytesToString(List<int> value) {
    final bytes = Uint8List.fromList([for (final b in value) b & 0xFF]);
    return utf8.decode(bytes, allowMalformed: true);
  }

  void _emitStatus(String message) {
    // Always use WithoutSubscribers: Flet's triggerControlEvent drops events unless
    // `on_status` is true on the Dart control mirror, and Service controls often do
    // not sync that flag — so Python would never receive BLE data or status lines.
    control.triggerEventWithoutSubscribers("status", {"message": message});
  }

  void _emitNotification(String text) {
    control.triggerEventWithoutSubscribers("notification", {"text": text});
    _log(
        "notify bytes=${text.length} sample=${text.length > 80 ? text.substring(0, 80) : text}");
  }

  Future<bool> _connect(String mac) async {
    _log("connect start mac=$mac char=${_charUuid()}");
    await _disconnect();
    if (!await FlutterBluePlus.isSupported) {
      _log("connect abort: isSupported=false");
      _emitStatus("BLE no soportado en este dispositivo");
      return false;
    }
    if (!await FlutterBluePlus.isOn) {
      _log("connect abort: Bluetooth is off");
      _emitStatus("Bluetooth apagado o no disponible");
      return false;
    }

    _emitStatus("Conectando…");
    BluetoothDevice dev;
    try {
      dev = BluetoothDevice.fromId(mac);
    } catch (e) {
      _log("connect abort: fromId failed $e");
      _emitStatus("MAC inválida: $e");
      return false;
    }

    _device = dev;
    try {
      // flutter_blue_plus 1.36+ — connect() no longer takes a license parameter.
      _log("BluetoothDevice.connect(timeout=20s)…");
      await dev.connect(timeout: const Duration(seconds: 20));
      _log("connected isConnected=${dev.isConnected} mtu=${dev.mtuNow}");
    } catch (e) {
      _log("connect failed: $e");
      _emitStatus("Error al conectar: $e");
      _device = null;
      return false;
    }

    _emitStatus("Descubriendo servicios…");
    final want = Guid(_charUuid());
    final want128 = want.str128;
    BluetoothCharacteristic? target;
    try {
      final services = await dev.discoverServices();
      _log("discoverServices: ${services.length} service(s)");
      var chrLogged = 0;
      for (final s in services) {
        _log("  service ${s.uuid.str128} chars=${s.characteristics.length}");
        for (final c in s.characteristics) {
          if (chrLogged < 24) {
            _log("    chr ${c.uuid.str128} props=${c.properties} notify=${c.properties.notify} indicate=${c.properties.indicate}");
            chrLogged++;
          }
        }
      }
      outer:
      for (final s in services) {
        for (final c in s.characteristics) {
          if (c.uuid == want || c.uuid.str128 == want128) {
            target = c;
            _log("matched target char ${c.uuid.str128}");
            break outer;
          }
        }
      }
    } catch (e) {
      _log("discoverServices exception: $e");
      _emitStatus("discoverServices: $e");
      await _disconnect();
      return false;
    }

    if (target == null) {
      _log("no characteristic for want=$want128");
      _emitStatus("Característica GATT no encontrada (${_charUuid()})");
      await _disconnect();
      return false;
    }

    try {
      _log("setNotifyValue(true)…");
      await target.setNotifyValue(true);
      _log("setNotifyValue done isNotifying=${target.isNotifying}");
    } catch (e) {
      _log("setNotifyValue failed: $e");
      _emitStatus("setNotifyValue: $e");
      await _disconnect();
      return false;
    }

    _log("subscribing onValueReceived…");
    _notifyHexLogsLeft = 5;
    _notifySub = target.onValueReceived.listen(
      (value) {
        try {
          final text = _notifyBytesToString(value);
          if ((control.getBool("bridge_debug", false) ?? false) &&
              value.isNotEmpty &&
              _notifyHexLogsLeft > 0) {
            _notifyHexLogsLeft--;
            final n = value.length > 16 ? 16 : value.length;
            final hex = value
                .take(n)
                .map((b) => (b & 0xFF).toRadixString(16).padLeft(2, "0"))
                .join(" ");
            _log("onValueReceived len=${value.length} hex[:$n]=$hex");
          }
          _emitNotification(text);
        } catch (e) {
          _log("onValueReceived decode error: $e");
          _emitStatus("decode notify: $e");
        }
      },
      onError: (e) {
        _log("onValueReceived stream error: $e");
        _emitStatus("notify stream: $e");
      },
    );

    _emitStatus("Notificaciones activas");
    _log("connect ok, notifications armed");
    return true;
  }

  Future<void> _disconnect() async {
    _log("disconnect()");
    await _notifySub?.cancel();
    _notifySub = null;
    final d = _device;
    _device = null;
    if (d != null && d.isConnected) {
      try {
        await d.disconnect();
        _log("device.disconnect() done");
      } catch (_) {}
    }
    _emitStatus("Desconectado");
  }

  void _ingestScanResults(
    List<ScanResult> results,
    String targetName,
    List<Map<String, dynamic>> list,
    Set<String> seen, {
    String source = "scan",
  }) {
    _log("scanResults batch size=${results.length} ($source)");
    for (final sr in results) {
      final dev = sr.device;
      final name = dev.platformName;
      // Skip only when we know the name and it cannot match (empty name = still show; MAC may be enough).
      if (targetName.isNotEmpty &&
          name.isNotEmpty &&
          !name.contains(targetName)) {
        continue;
      }
      final id = dev.remoteId.str;
      if (seen.contains(id)) {
        continue;
      }
      seen.add(id);
      list.add({"name": name, "mac": id});
      _log(
          "  candidate name=${name.isEmpty ? "(empty)" : name} mac=$id rssi=${sr.rssi}");
    }
  }

  Future<void> _prepareScan() async {
    try {
      if (FlutterBluePlus.isScanningNow) {
        _log("prepareScan: stopping stuck scan");
        await FlutterBluePlus.stopScan();
      }
    } catch (e) {
      _log("prepareScan stopScan: $e");
    }
    // Let Android scanner fully release before the next start (avoids SCAN_FAILED_* / empty results).
    await Future<void>.delayed(const Duration(milliseconds: 400));
  }

  Future<void> _addBondedDevices(
    String targetName,
    List<Map<String, dynamic>> list,
    Set<String> seen,
  ) async {
    try {
      final bonded = await FlutterBluePlus.bondedDevices;
      _log("bondedDevices count=${bonded.length}");
      for (final d in bonded) {
        final id = d.remoteId.str;
        if (seen.contains(id)) {
          continue;
        }
        final name = d.platformName;
        if (targetName.isNotEmpty &&
            name.isNotEmpty &&
            !name.contains(targetName)) {
          continue;
        }
        seen.add(id);
        list.add({"name": name, "mac": id});
        _log(
            "  bonded name=${name.isEmpty ? "(empty)" : name} mac=$id");
      }
    } catch (e) {
      _log("bondedDevices (skip): $e");
    }
  }

  Future<List<Map<String, dynamic>>> _scan(String targetName, int timeoutMs) async {
    _log("scan start targetName=${targetName.isEmpty ? "(any)" : targetName} timeoutMs=$timeoutMs");
    if (!await FlutterBluePlus.isSupported) {
      _log("scan abort: not supported");
      return [];
    }
    if (!await FlutterBluePlus.isOn) {
      _log("scan abort: Bluetooth off");
      _emitStatus("Bluetooth apagado");
      return [];
    }
    if (FlutterBluePlus.adapterStateNow != BluetoothAdapterState.on) {
      _log("scan abort: adapterState=${FlutterBluePlus.adapterStateNow}");
    }

    final list = <Map<String, dynamic>>[];
    final seen = <String>{};

    await _prepareScan();
    await _addBondedDevices(targetName, list, seen);

    late StreamSubscription<List<ScanResult>> sub;
    sub = FlutterBluePlus.scanResults.listen((results) {
      _ingestScanResults(results, targetName, list, seen, source: "stream");
    });

    try {
      await FlutterBluePlus.startScan(
        timeout: Duration(milliseconds: timeoutMs),
        androidUsesFineLocation: true,
        // If system GPS is off, FBP may refuse to scan even when BT permissions are OK.
        androidCheckLocationServices: false,
      );
      await Future<void>.delayed(Duration(milliseconds: timeoutMs + 500));
      await FlutterBluePlus.stopScan();
      // Flush any deduped cache the plugin still holds.
      _ingestScanResults(
        List<ScanResult>.from(FlutterBluePlus.lastScanResults),
        targetName,
        list,
        seen,
        source: "lastScanResults",
      );
    } catch (e) {
      _log("scan exception: $e");
      _emitStatus("scan: $e");
    } finally {
      await sub.cancel();
    }

    _log("scan done unique=${list.length}");
    return list;
  }

  @override
  void dispose() {
    unawaited(_disconnect());
    control.removeInvokeMethodListener(_invokeMethod);
    super.dispose();
  }
}
