"""
Flet service: Flutter-side BLE (flutter_blue_plus) forwards GATT notifications to Python.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import flet as ft
from flet.controls.control_event import Event
from flet.controls.services.service import Service

__all__ = [
    "BleBridgeLogEvent",
    "BleNotificationEvent",
    "BleStatusEvent",
    "FletBleBridge",
]


@dataclass(kw_only=True)
class BleNotificationEvent(Event["FletBleBridge"]):
    text: str = field(metadata={"data_field": "text"})


@dataclass(kw_only=True)
class BleStatusEvent(Event["FletBleBridge"]):
    message: str = field(metadata={"data_field": "message"})


@dataclass(kw_only=True)
class BleBridgeLogEvent(Event["FletBleBridge"]):
    """Verbose line from Dart (scan/connect/GATT). Only sent when ``bridge_debug`` is True."""

    message: str = field(metadata={"data_field": "message"})


@ft.control("FletBleBridge")
class FletBleBridge(Service):
    """
    Mobile-only: registers with the page service registry and runs BLE in Flutter.

    Subscribe to :attr:`on_notification` for UTF-8 payload strings from the GATT
    characteristic, and optionally :attr:`on_status` for human-readable status.

    Set :attr:`bridge_debug` to forward verbose Dart traces to :attr:`on_bridge_log`; Dart
    also logs every line with ``debugPrint`` and prefix ``[flet_ble_bridge]`` (see ``adb logcat``).
    """

    char_uuid: str = "12345678-1234-5678-1234-56789abcdef1"

    bridge_debug: bool = False

    on_notification: Optional[Callable[[BleNotificationEvent], None]] = None
    on_status: Optional[Callable[[BleStatusEvent], None]] = None
    on_bridge_log: Optional[Callable[[BleBridgeLogEvent], None]] = None

    async def connect_ble(self, mac: str) -> Any:
        return await self._invoke_method("connect", {"mac": mac})

    async def disconnect_ble(self) -> Any:
        return await self._invoke_method("disconnect")

    async def scan_ble(self, target_name: str, timeout_ms: int = 10000) -> Any:
        return await self._invoke_method(
            "scan", {"target_name": target_name, "timeout_ms": timeout_ms}
        )
