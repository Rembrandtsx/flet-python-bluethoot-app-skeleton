"""
Desktop BLE using Bleak (asyncio in a background thread).
"""

from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import Callable
from typing import Optional

from bleak import BleakClient, BleakScanner

from esp32_sensor import CHAR_UUID, TARGET_NAME


def _run_ble_loop(
    stop_event: threading.Event,
    out_queue: "queue.Queue[str]",
    on_status: Callable[[str], None],
    on_debug: Optional[Callable[[str], None]] = None,
) -> None:
    def _d(msg: str) -> None:
        if on_debug:
            try:
                on_debug(f"[ble_desktop] {msg}")
            except Exception:
                pass

    async def run() -> None:
        on_status("Buscando ESP32...")
        _d("BleakScanner.discover loop start")
        device = None
        while device is None and not stop_event.is_set():
            devices = await BleakScanner.discover(timeout=5.0)
            _d(f"discover saw {len(devices)} device(s)")
            for d in devices:
                if d.name and TARGET_NAME in d.name:
                    device = d
                    _d(f"match name={d.name!r} addr={d.address}")
                    break
            if device is None:
                on_status("ESP32 no encontrado, reintentando...")
                await asyncio.sleep(1.0)

        if stop_event.is_set() or device is None:
            _d("exit before connect (stop or no device)")
            return

        on_status(f"Conectando a {device.name}...")
        _d(f"BleakClient({device.address})")

        _n = [0]

        def handler(_: int, data: bytearray) -> None:
            try:
                raw = data.decode(errors="replace")
                _n[0] += 1
                if _n[0] <= 5 or _n[0] % 100 == 0:
                    _d(f"notify #{_n[0]} len={len(data)} preview={raw[:80]!r}")
                out_queue.put(raw)
            except Exception:
                pass

        async with BleakClient(device.address, timeout=20.0) as client:
            _d("start_notify")
            await client.start_notify(CHAR_UUID, handler)
            on_status("Conectado. Recibiendo datos...")
            while not stop_event.is_set():
                await asyncio.sleep(0.1)
            _d("stop_notify path (loop exit)")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run())
    finally:
        loop.close()


def start_ble_desktop(
    stop_event: threading.Event,
    out_queue: "queue.Queue[str]",
    on_status: Callable[[str], None],
    *,
    on_debug: Optional[Callable[[str], None]] = None,
) -> threading.Thread:
    t = threading.Thread(
        target=_run_ble_loop,
        args=(stop_event, out_queue, on_status, on_debug),
        daemon=True,
    )
    t.start()
    return t
