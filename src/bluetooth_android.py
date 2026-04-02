"""
Android Bluetooth helpers using Pyjnius.

This module is meant to be used **only on Android** builds of your
Flet app. On desktop, importing it will fail unless Pyjnius and the
Android runtime are present, so the UI code should guard imports.
"""

from __future__ import annotations

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
