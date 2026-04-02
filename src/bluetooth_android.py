"""
Android Bluetooth helpers using Pyjnius.

This module is meant to be used **only on Android** builds of your
Flet app. On desktop, importing it will fail unless Pyjnius and the
Android runtime are present, so the UI code should guard imports.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from threading import Thread
from typing import Callable, List, Optional

from jnius import autoclass  # type: ignore[import]


BluetoothAdapter = autoclass("android.bluetooth.BluetoothAdapter")
UUID = autoclass("java.util.UUID")

# Classic Bluetooth Serial Port Profile UUID.
SPP_UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")


@dataclass
class BondedDevice:
    name: str
    address: str


def _get_activity():
    host = os.environ.get("MAIN_ACTIVITY_HOST_CLASS_NAME")
    if host:
        cls = autoclass(host)
        return cls.mActivity
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    return PythonActivity.mActivity


def get_bluetooth_adapter():
    adapter = BluetoothAdapter.getDefaultAdapter()
    if adapter is None:
        raise RuntimeError("Bluetooth not supported on this device")
    if not adapter.isEnabled():
        # In a production app you would prompt the user to enable Bluetooth.
        raise RuntimeError("Bluetooth is disabled. Please enable it in system settings.")
    return adapter


def list_bonded_devices() -> List[BondedDevice]:
    """
    Return a list of already-paired (bonded) devices.

    This keeps things simple for prototyping: pair the device once in
    Android Settings, then pick it in the UI.
    """
    adapter = get_bluetooth_adapter()
    bonded = adapter.getBondedDevices()
    result: List[BondedDevice] = []
    for dev in bonded.toArray():
        result.append(BondedDevice(name=str(dev.getName()), address=str(dev.getAddress())))
    return result


def list_gatt_connected_devices() -> List[BondedDevice]:
    """
    Devices currently connected over GATT (BLE), including some that may
    appear without going through the bonded list first.
    """
    result: List[BondedDevice] = []
    try:
        activity = _get_activity()
        Context = autoclass("android.content.Context")
        BluetoothProfile = autoclass("android.bluetooth.BluetoothProfile")
        bm = activity.getSystemService(Context.BLUETOOTH_SERVICE)
        if bm is None:
            return result
        devices = bm.getConnectedDevices(BluetoothProfile.GATT)
        if devices is None:
            return result
        dev_list: list = []
        try:
            dev_list = list(devices)
        except Exception:
            try:
                n = int(devices.size())
                for i in range(n):
                    dev_list.append(devices.get(i))
            except Exception:
                dev_list = []
        for dev in dev_list:
            nm = dev.getName()
            result.append(
                BondedDevice(
                    name=str(nm) if nm is not None else "",
                    address=str(dev.getAddress()),
                )
            )
    except Exception:
        pass
    return result


def list_bonded_and_connected_devices(
    on_debug: Optional[Callable[[str], None]] = None,
) -> List[BondedDevice]:
    """
    Union of paired (bonded) devices and GATT-connected devices, deduped by MAC.
    Bonded entries win on name conflicts.
    """
    log = on_debug or (lambda _m: None)
    log("bluetooth_android: list_bonded_and_connected_devices: start")
    bonded = list_bonded_devices()
    log(f"bluetooth_android: bonded -> {len(bonded)}")
    gatt_conn = list_gatt_connected_devices()
    log(f"bluetooth_android: gatt_connected -> {len(gatt_conn)}")
    by_addr: dict[str, BondedDevice] = {}
    for d in bonded:
        by_addr[d.address.upper()] = d
    for d in gatt_conn:
        key = d.address.upper()
        if key not in by_addr:
            log(f"bluetooth_android: merge add GATT-only {d.name!r} {d.address}")
            by_addr[key] = d
    out = list(by_addr.values())
    log(f"bluetooth_android: merged total -> {len(out)}")
    return out


def _reader_thread(sock, on_data: Callable[[str], None]) -> None:
    """
    Blocking loop which reads from the Bluetooth socket and
    calls `on_data` for each chunk.
    """
    try:
        inp = sock.getInputStream()
        buf = bytearray(1024)
        while True:
            read = inp.read(buf)
            if read == -1:
                break
            if read > 0:
                chunk = bytes(buf[:read]).decode(errors="replace")
                on_data(chunk)
    except Exception as exc:  # pragma: no cover - Android runtime specific
        on_data(f"[BT error] {exc}")
    finally:
        try:
            sock.close()
        except Exception:
            pass


def connect_and_read(
    address: str,
    on_data: Callable[[str], None],
) -> Optional[Thread]:
    """
    Connects to a bonded device by MAC address and starts a background
    thread that reads raw data and feeds it to `on_data`.

    Returns the Thread object or None if connection fails early.
    """
    adapter = get_bluetooth_adapter()
    device = adapter.getRemoteDevice(address)
    # You can tweak this for your specific device/profile as needed.
    socket = device.createRfcommSocketToServiceRecord(SPP_UUID)

    # It's a good idea to stop discovery before connecting for speed/stability.
    if adapter.isDiscovering():
        adapter.cancelDiscovery()

    try:
        socket.connect()
    except Exception as exc:  # pragma: no cover - Android runtime specific
        on_data(f"[BT connect error] {exc}")
        try:
            socket.close()
        except Exception:
            pass
        return None

    t = Thread(target=_reader_thread, args=(socket, on_data), daemon=True)
    t.start()
    return t
