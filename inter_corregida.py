"""
Monitor PPG/BLE de escritorio — misma lógica que la app Android (FallSense).

La app usa `esp32_sensor`: formato MPU:OK|FAIL, MAX:OK|FAIL, AX..GZ, IR, BPM y
`step_ui_state` para dedo, alertas y movimiento. Ver `src/main.py` + `src/esp32_sensor.py`.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import queue
import time
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.widgets import Button

from bleak import BleakScanner, BleakClient

# Misma fuente de verdad que la app Flet
_ROOT = Path(__file__).resolve().parent
_src = _ROOT / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from esp32_sensor import (  # noqa: E402
    CHAR_UUID,
    TARGET_NAME,
    SensorState,
    apply_sample,
    normalize_payload,
    step_ui_state,
)

# ================= COLA / ESTADO (como `pump()` en main.py) =================
data_queue: queue.Queue[str] = queue.Queue()
stop_event = threading.Event()
state = SensorState()


# ================= BLE RECEIVER (como `ble_desktop.py`: raw UTF-8 en cola) =================
def ble_receiver():
    async def run():
        device = None
        print("🔎 Buscando ESP32...")

        while device is None and not stop_event.is_set():
            devices = await BleakScanner.discover(timeout=5.0)
            for d in devices:
                if d.name and TARGET_NAME in d.name:
                    device = d
                    break
            if device is None:
                await asyncio.sleep(1.0)

        if stop_event.is_set() or device is None:
            return

        print(f"✅ Conectando a {device.name}")

        async with BleakClient(device.address, timeout=20.0) as client:

            def handler(_, data: bytearray):
                try:
                    raw = data.decode(errors="replace")
                    data_queue.put(raw)
                except Exception:
                    pass

            await client.start_notify(CHAR_UUID, handler)

            while not stop_event.is_set():
                await asyncio.sleep(0.1)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run())


# ================= UI =================
class MonitorUI:
    def __init__(self):
        self.fig, (self.ax_ecg, self.ax_info) = plt.subplots(2, 1, figsize=(10, 6))

        self.ax_ecg.set_title("Señal PPG (IR)")
        self.line, = self.ax_ecg.plot([], [])

        self.ax_info.axis("off")

        self.ax_btn = plt.axes([0.7, 0.02, 0.25, 0.08])
        self.btn = Button(self.ax_btn, "No es crisis")
        self.btn.on_clicked(self.override)
        self.ax_btn.set_visible(False)

    def override(self, event):
        state.manual_override = True

    def update(self, frame):
        now = time.time()

        while not data_queue.empty():
            try:
                raw = data_queue.get_nowait()
            except queue.Empty:
                break
            parsed = normalize_payload(raw)
            if parsed:
                apply_sample(state, parsed, now)

        status_msg, alert_val, moving, bpm_shown, show_override = step_ui_state(
            state, now
        )

        self.ax_btn.set_visible(show_override)

        hw_line = ""
        if state.mpu_hw_ok is not None:
            hw_line += f"MPU: {'OK' if state.mpu_hw_ok else 'Fallo'}  "
        if state.max_hw_ok is not None:
            hw_line += f"MAX30102: {'OK' if state.max_hw_ok else 'Fallo'}"

        move_label = "detectado" if moving else "no detectado"

        if len(state.ir_buffer) > 0:
            self.line.set_data(range(len(state.ir_buffer)), state.ir_buffer)
            self.ax_ecg.set_xlim(0, len(state.ir_buffer))

            ymin = min(state.ir_buffer)
            ymax = max(state.ir_buffer)
            if ymin == ymax:
                ymax += 1
            self.ax_ecg.set_ylim(ymin, ymax)

        self.ax_info.clear()
        self.ax_info.axis("off")

        self.ax_info.text(0.1, 0.78, status_msg, fontsize=16)
        if hw_line.strip():
            self.ax_info.text(0.1, 0.62, hw_line.strip(), fontsize=11, color="0.35")
        self.ax_info.text(0.1, 0.46, f"Movimiento: {move_label}", fontsize=14)
        self.ax_info.text(0.1, 0.28, f"Alertas: {alert_val}", fontsize=16)

    def run(self):
        ani = animation.FuncAnimation(self.fig, self.update, interval=200)
        plt.show()


# ================= MAIN =================
def main():
    t = threading.Thread(target=ble_receiver)
    t.daemon = True
    t.start()

    ui = MonitorUI()
    try:
        ui.run()
    finally:
        stop_event.set()


if __name__ == "__main__":
    main()
