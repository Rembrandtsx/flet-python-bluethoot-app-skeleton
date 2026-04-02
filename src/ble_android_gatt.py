"""
Android BLE GATT notifications via Pyjnius (ESP32 same UUID as desktop Bleak).

Pyjnius PythonJavaClass only implements Java *interfaces* (java.lang.reflect.Proxy).
BluetoothGattCallback is an abstract *class*, so we use a tiny Java subclass
(BleGattBridge in the same Android package as MainActivity) and implement its Events
interface from Python.

The bridge must live in the **application Java package** (see ``android_ble_bridge_meta``),
not a separate ``dev.*`` package, or JNI may fail to load the class on device.

Build the APK with ./scripts/flet-with-cert.sh so BleGattBridge is generated into
``build/flutter`` before Gradle (scripts/flet_with_ble_gatt.py).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Optional

from android_ble_bridge_meta import ble_bridge_class_fqcn, ble_bridge_events_iface_internal
from esp32_sensor import CHAR_UUID

LogFn = Optional[Callable[[str], None]]

try:
    from jnius import PythonJavaClass, autoclass, find_javaclass, java_method
except ImportError:  # pragma: no cover - desktop
    PythonJavaClass = object  # type: ignore[misc, assignment]
    autoclass = None  # type: ignore[misc, assignment]
    find_javaclass = None  # type: ignore[misc, assignment]
    java_method = lambda *a, **k: (lambda f: f)  # type: ignore[misc, assignment]

JAVA_BRIDGE_FQCN = ble_bridge_class_fqcn()
# JNI internal name for inner interface Events (must match app package)
_EVENTS_IFACE = ble_bridge_events_iface_internal()

# Resolve once on the thread that runs connect_ble_notify (async/UI). GATT callbacks
# run on a binder thread; calling autoclass() there is a common JNI crash source.
_JAVA: dict[str, object] = {}


def _warm_java_types() -> None:
    assert autoclass is not None
    if _JAVA:
        return
    _JAVA["BluetoothProfile"] = autoclass("android.bluetooth.BluetoothProfile")
    _JAVA["BluetoothGatt"] = autoclass("android.bluetooth.BluetoothGatt")
    _JAVA["BluetoothGattDescriptor"] = autoclass("android.bluetooth.BluetoothGattDescriptor")
    _JAVA["UUID"] = autoclass("java.util.UUID")


def _get_activity():
    assert autoclass is not None
    host = os.environ.get("MAIN_ACTIVITY_HOST_CLASS_NAME")
    if host:
        cls = autoclass(host)
        return cls.mActivity
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    return PythonActivity.mActivity


if PythonJavaClass is not object:

    class _BleEvents(PythonJavaClass):  # type: ignore[misc, valid-type]
        __javainterfaces__ = [_EVENTS_IFACE]
        __javacontext__ = "app"

        @java_method("(Landroid/bluetooth/BluetoothGatt;II)V")  # type: ignore[misc]
        def onConnectionStateChange(self, gatt, status, new_state) -> None:  # noqa: N802
            BT = _JAVA["BluetoothProfile"]
            self._d(f"onConnectionStateChange status={status} new_state={new_state}")
            if new_state == BT.STATE_CONNECTED:
                self._holder.connected = True
                try:
                    self._on_raw("[GATT] connected")
                except Exception:
                    pass
                self._d("discoverServices()")
                gatt.discoverServices()
            elif new_state == BT.STATE_DISCONNECTED:
                self._holder.connected = False
                self._d("STATE_DISCONNECTED")

        @java_method("(Landroid/bluetooth/BluetoothGatt;I)V")  # type: ignore[misc]
        def onServicesDiscovered(self, gatt, status) -> None:  # noqa: N802
            Gatt = _JAVA["BluetoothGatt"]
            self._d(f"onServicesDiscovered status={status}")
            if status != Gatt.GATT_SUCCESS:
                self._on_raw(f"[GATT] onServicesDiscovered status={status}")
                return
            UUID = _JAVA["UUID"]
            want = UUID.fromString(self._target_uuid)
            services = gatt.getServices()
            found = None
            for i in range(services.size()):
                svc = services.get(i)
                chars = svc.getCharacteristics()
                for j in range(chars.size()):
                    ch = chars.get(j)
                    if ch.getUuid().equals(want):
                        found = ch
                        break
                if found is not None:
                    break
            if found is None:
                self._d("target characteristic UUID not found on any service")
                self._on_raw("[GATT] Característica no encontrada")
                return
            self._holder.characteristic = found
            self._on_raw("[GATT] Característica encontrada, habilitando NOTIFY...")
            self._d("setCharacteristicNotification(True)")
            gatt.setCharacteristicNotification(found, True)
            BTDesc = _JAVA["BluetoothGattDescriptor"]
            cccd = UUID.fromString("00002902-0000-1000-8000-00805F9B34FB")
            desc = found.getDescriptor(cccd)
            if desc is None:
                self._d("CCCD descriptor missing")
                self._on_raw("[GATT] Descriptor CCCD no encontrado")
                return
            desc.setValue(BTDesc.ENABLE_NOTIFICATION_VALUE)
            self._d("writeDescriptor(CCCD enable notify)")
            gatt.writeDescriptor(desc)
            self._holder.connected = True

        @java_method(  # type: ignore[misc]
            "(Landroid/bluetooth/BluetoothGatt;Landroid/bluetooth/BluetoothGattDescriptor;I)V"
        )
        def onDescriptorWrite(self, gatt, descriptor, status) -> None:  # noqa: N802
            self._d(f"onDescriptorWrite status={status}")

        @java_method(  # type: ignore[misc]
            "(Landroid/bluetooth/BluetoothGatt;Landroid/bluetooth/BluetoothGattCharacteristic;)V"
        )
        def onCharacteristicChanged(self, gatt, characteristic) -> None:  # noqa: N802
            raw = characteristic.getValue()
            if raw is None:
                self._d("onCharacteristicChanged: value is None")
                return
            try:
                text = bytes(raw).decode(errors="replace")
                self._notify_count += 1
                n = self._notify_count
                if n <= 5 or n % 100 == 0:
                    self._d(f"onCharacteristicChanged #{n} len={len(raw)} preview={text[:80]!r}")
                self._on_raw(text)
            except Exception as exc:
                self._d(f"onCharacteristicChanged decode err: {exc}")

        def _d(self, msg: str) -> None:
            if self._on_debug:
                try:
                    self._on_debug(f"[ble_android_gatt] {msg}")
                except Exception:
                    pass

else:  # pragma: no cover - desktop stub
    _BleEvents = None  # type: ignore[misc, assignment]


class _GattHolder:
    def __init__(self) -> None:
        self.gatt = None
        self.characteristic = None
        self.connected = False


def _make_events(
    on_raw: Callable[[str], None],
    target_uuid: str,
    holder: _GattHolder,
    on_debug: LogFn,
) -> object:
    e = _BleEvents()
    e._on_raw = on_raw
    e._target_uuid = target_uuid
    e._holder = holder
    e._on_debug = on_debug
    e._notify_count = 0
    return e


def connect_ble_notify(
    mac_address: str,
    on_raw: Callable[[str], None],
    on_status: Callable[[str], None],
    *,
    on_debug: LogFn = None,
) -> Optional[Callable[[], None]]:
    """
    Connect to bonded device by MAC and subscribe to CHAR_UUID notifications.
    Returns a disconnect callable, or None on early failure.
    """

    def _d(msg: str) -> None:
        if on_debug:
            try:
                on_debug(f"[ble_android_gatt] {msg}")
            except Exception:
                pass

    if autoclass is None or find_javaclass is None or _BleEvents is None:
        _d("autoclass is None (Pyjnius missing)")
        on_status("Pyjnius no disponible")
        return None

    # autoclass() can JNI-abort if the class was never compiled into the APK; find_javaclass is safer.
    try:
        if find_javaclass(JAVA_BRIDGE_FQCN) is None:
            _d(f"find_javaclass({JAVA_BRIDGE_FQCN!r}) -> None")
            on_status(
                "Falta la clase Java BleGattBridge en el APK. Recompila con "
                "./scripts/flet-with-cert.sh build apk."
            )
            return None
    except Exception as exc:
        _d(f"find_javaclass {JAVA_BRIDGE_FQCN!r}: {exc!r}")
        on_status(f"BleGattBridge no encontrado (JNI): {exc}")
        return None

    try:
        BleGattBridge = autoclass(JAVA_BRIDGE_FQCN)
    except Exception as exc:
        _d(f"autoclass {JAVA_BRIDGE_FQCN} failed: {exc!r}")
        on_status(
            "Falta clase Java BleGattBridge. Recompila con ./scripts/flet-with-cert.sh build apk."
        )
        return None

    try:
        _d(f"connect_ble_notify mac={mac_address!r} char={CHAR_UUID}")
        activity = _get_activity()
        _d("_get_activity() OK")
        BluetoothAdapter = autoclass("android.bluetooth.BluetoothAdapter")
        adapter = BluetoothAdapter.getDefaultAdapter()
        if adapter is None:
            _d("getDefaultAdapter() is None")
            on_status("Bluetooth no disponible")
            return None
        if not adapter.isEnabled():
            _d("adapter disabled")
            on_status("Activa Bluetooth en Ajustes")
            return None

        device = adapter.getRemoteDevice(mac_address)
        _warm_java_types()
        holder = _GattHolder()
        events = _make_events(on_raw, CHAR_UUID, holder, on_debug)
        bridge = BleGattBridge()
        bridge.setEvents(events)

        if adapter.isDiscovering():
            _d("cancelDiscovery()")
            adapter.cancelDiscovery()

        on_status("Conectando BLE...")
        try:
            BluetoothDevice = autoclass("android.bluetooth.BluetoothDevice")
            on_status("connectGatt(TRANSPORT_LE) ...")
            _d("connectGatt(activity, false, bridge, TRANSPORT_LE)")
            gatt = device.connectGatt(activity, False, bridge, BluetoothDevice.TRANSPORT_LE)
        except Exception as exc:
            _d(f"connectGatt LE failed ({exc}), fallback without transport")
            gatt = device.connectGatt(activity, False, bridge)
        on_status("connectGatt() returned, waiting callbacks...")
        _d(f"connectGatt returned gatt={gatt!r}")
        holder.gatt = gatt

        def disconnect() -> None:
            _d("disconnect() called")
            try:
                if holder.gatt is not None:
                    holder.gatt.disconnect()
                    holder.gatt.close()
            except Exception as exc:
                _d(f"disconnect err: {exc}")

        return disconnect
    except Exception as exc:  # pragma: no cover - Android only
        _d(f"connect_ble_notify exception: {exc!r}")
        on_status(f"Error BLE: {exc}")
        return None
