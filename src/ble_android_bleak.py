"""
Android BLE backend using Bleak (notifications).

This mirrors the notification parsing approach used in `interfaz_PrCo.py`:
decode bytes -> split by "," -> split by ":" -> float values -> push dict.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from typing import Optional

from bleak import BleakClient

from esp32_sensor import CHAR_UUID, TARGET_NAME


def connect_ble_notify_bleak(
    address: str,
    on_payload: Callable[[dict[str, float]], None],
    on_status: Callable[[str], None],
    *,
    stop_event: Optional[threading.Event] = None,
    timeout_s: float = 20.0,
    on_debug: Optional[Callable[[str], None]] = None,
) -> Optional[Callable[[], None]]:
    """
    Connect to `address` and subscribe to `CHAR_UUID` notifications.

    Returns a disconnect callable (best-effort), or None if early failure.
    """

    def _d(msg: str) -> None:
        if on_debug:
            try:
                on_debug(f"[ble_android_bleak] {msg}")
            except Exception:
                pass

    stop_event = stop_event or threading.Event()
    holder: dict[str, object] = {"client": None, "notify_started": False}

    def _run() -> None:
        async def run() -> None:
            _d(f"thread run start address={address!r}")
            on_status("Conectando BLE (Bleak)...")

            async with BleakClient(address, timeout=timeout_s) as client:
                holder["client"] = client
                _d("BleakClient entered")

                _n = [0]

                def handler(_: int, data: bytearray) -> None:
                    try:
                        text = bytes(data).decode(errors="replace").strip()
                        values: dict[str, float] = {}
                        for item in text.split(","):
                            item = item.strip()
                            if not item or ":" not in item:
                                continue
                            k, v = item.split(":", 1)
                            values[k.strip().upper()] = float(v.strip())
                        if values:
                            _n[0] += 1
                            if _n[0] <= 5 or _n[0] % 100 == 0:
                                _d(f"notify #{_n[0]} keys={list(values.keys())}")
                            on_payload(values)
                    except Exception as exc:
                        on_status(f"[Bleak parse err] {exc}")
                        _d(f"parse err: {exc}")

                await client.start_notify(CHAR_UUID, handler)
                holder["notify_started"] = True
                _d("start_notify OK")
                on_status(f"Conectado. Notificando desde {TARGET_NAME}...")

                while not stop_event.is_set():
                    await asyncio.sleep(0.1)

                try:
                    await client.stop_notify(CHAR_UUID)
                except Exception:
                    pass
                _d("run() exit (stop_notify)")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run())
        finally:
            loop.close()
            _d("event loop closed")

    try:
        _d("spawn thread")
        t = threading.Thread(target=_run, daemon=True)
        t.start()
    except Exception as exc:
        _d(f"thread start failed: {exc}")
        on_status(f"BLEAK Android error: {exc}")
        return None

    def disconnect() -> None:
        _d("disconnect(): stop_event.set()")
        try:
            stop_event.set()
        except Exception:
            pass

    return disconnect

