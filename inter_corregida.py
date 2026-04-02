import asyncio
import threading
import queue
import time

import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.widgets import Button

from bleak import BleakScanner, BleakClient

# ================= BLE =================
CHAR_UUID = "12345678-1234-5678-1234-56789abcdef1"
TARGET_NAME = "ESP32_BIOSENSORS"

# ================= VARIABLES =================
data_queue = queue.Queue()
stop_event = threading.Event()

ir_buffer = []
time_buffer = []
acc_buffer = []

bpm_display = 0

alert_text = "OK"
manual_override = False

# ===== CONTROL DE DEDO =====
finger_detected = False
IR_THRESHOLD = 50000

# ===== BUFFER =====
MAX_SAMPLES = 1000

# ================= BLE RECEIVER =================
def ble_receiver():
    async def run():
        device = None
        print("🔎 Buscando ESP32...")

        while device is None:
            devices = await BleakScanner.discover()
            for d in devices:
                if d.name and TARGET_NAME in d.name:
                    device = d
                    break

        print(f"✅ Conectando a {device.name}")

        async with BleakClient(device.address, timeout=20.0) as client:

            def handler(_, data):
                try:
                    text = data.decode()
                    values = {}
                    for item in text.split(","):
                        k, v = item.split(":")
                        values[k] = float(v)

                    data_queue.put(values)
                except:
                    pass

            await client.start_notify(CHAR_UUID, handler)

            while not stop_event.is_set():
                await asyncio.sleep(0.1)

    # IMPORTANTE: loop nuevo para threading
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run())

# ================= UI =================
class MonitorUI:
    def __init__(self):
        self.fig, (self.ax_ecg, self.ax_info) = plt.subplots(2, 1, figsize=(10, 6))

        self.ax_ecg.set_title("Señal PPG")
        self.line, = self.ax_ecg.plot([], [])

        self.ax_info.axis("off")

        # Botón override (inicialmente oculto)
        self.ax_btn = plt.axes([0.7, 0.02, 0.25, 0.08])
        self.btn = Button(self.ax_btn, "No es crisis")
        self.btn.on_clicked(self.override)
        self.ax_btn.set_visible(False)

    def override(self, event):
        global manual_override
        manual_override = True

    def update(self, frame):
        global bpm_display
        global alert_text, manual_override
        global finger_detected

        # ===== RECIBIR DATOS =====
        while not data_queue.empty():
            d = data_queue.get()

            ax = d.get("AX", 0)
            ay = d.get("AY", 0)
            az = d.get("AZ", 0)
            ir = d.get("IR", 0)

            if "BPM" in d:
                bpm_display = d["BPM"]

            t = time.time()

            ir_buffer.append(ir)
            time_buffer.append(t)
            acc_buffer.append((ax, ay, az))

            if len(ir_buffer) > MAX_SAMPLES:
                ir_buffer.pop(0)
                time_buffer.pop(0)
                acc_buffer.pop(0)

        # ===== DETECCIÓN DE DEDO =====
        if len(ir_buffer) > 0:
            current_ir = ir_buffer[-1]
        else:
            current_ir = 0

        finger_detected = current_ir > IR_THRESHOLD

        if not finger_detected:
            bpm_display = 0

        # ===== MOVIMIENTO =====
        moving = False
        if len(acc_buffer) > 10:
            diffs = [
                abs(acc_buffer[i][0] - acc_buffer[i-1][0])
                for i in range(1, len(acc_buffer))
            ]
            if sum(diffs)/len(diffs) > 0.5:
                moving = True

        # Mostrar botón solo si hay movimiento
        self.ax_btn.set_visible(moving)

        # ===== ALERTAS =====
        alert_text = "OK"

        if bpm_display < 60 and finger_detected:
            alert_text = "⚠️ Bradicardia"
        elif bpm_display > 190:
            alert_text = "🚨 Taquicardia"

        if bpm_display > 150 and not moving:
            alert_text = "🚨 Posible crisis"

        if manual_override:
            alert_text = "✔️ No es crisis"

        # ===== MENSAJE PRINCIPAL =====
        if not finger_detected:
            status_msg = "Coloca el dedo en el sensor"
        else:
            status_msg = f"BPM: {bpm_display:.1f}"

        # ===== PLOT =====
        if len(ir_buffer) > 0:
            self.line.set_data(range(len(ir_buffer)), ir_buffer)
            self.ax_ecg.set_xlim(0, len(ir_buffer))

            ymin = min(ir_buffer)
            ymax = max(ir_buffer)
            if ymin == ymax:
                ymax += 1
            self.ax_ecg.set_ylim(ymin, ymax)

        self.ax_info.clear()
        self.ax_info.axis("off")

        self.ax_info.text(0.1, 0.7, status_msg, fontsize=16)
        self.ax_info.text(0.1, 0.5, f"Movimiento: {'Sí' if moving else 'No'}", fontsize=14)
        self.ax_info.text(0.1, 0.3, f"Estado: {alert_text}", fontsize=16)

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