"""
ESP32 biosensor protocol and UI state (ported from inter_corregida.py).

BLE characteristic sends UTF-8 text like: AX:0.1,AY:0.2,AZ:0.3,IR:12345,BPM:72
"""

from __future__ import annotations

from dataclasses import dataclass, field

CHAR_UUID = "12345678-1234-5678-1234-56789abcdef1"
TARGET_NAME = "ESP32_BIOSENSORS"

MAX_SAMPLES = 200
IR_THRESHOLD = 50000


@dataclass
class SensorState:
    ir_buffer: list[float] = field(default_factory=list)
    time_buffer: list[float] = field(default_factory=list)
    acc_buffer: list[tuple[float, float, float]] = field(default_factory=list)
    bpm_display: float = 0.0
    alert_text: str = "OK"
    manual_override: bool = False
    finger_detected: bool = False


def parse_sensor_payload(text: str) -> dict[str, float] | None:
    """Parse one notification string into a dict of floats."""
    text = text.strip()
    if not text:
        return None
    values: dict[str, float] = {}
    try:
        for item in text.split(","):
            item = item.strip()
            if not item:
                continue
            if ":" in item:
                k, v = item.split(":", 1)
            elif "=" in item:
                k, v = item.split("=", 1)
            else:
                continue
            k_norm = k.strip().upper()
            values[k_norm] = float(v.strip())
    except (ValueError, TypeError):
        return None
    return values if values else None


def apply_sample(
    state: SensorState,
    d: dict[str, float],
    now: float,
) -> None:
    ax = float(d.get("AX", 0.0))
    ay = float(d.get("AY", 0.0))
    az = float(d.get("AZ", 0.0))
    ir = float(d.get("IR", 0.0))

    if "BPM" in d:
        state.bpm_display = float(d["BPM"])

    state.ir_buffer.append(ir)
    state.time_buffer.append(now)
    state.acc_buffer.append((ax, ay, az))

    if len(state.ir_buffer) > MAX_SAMPLES:
        state.ir_buffer.pop(0)
        state.time_buffer.pop(0)
        state.acc_buffer.pop(0)


def compute_motion(acc_buffer: list[tuple[float, float, float]]) -> bool:
    if len(acc_buffer) <= 10:
        return False
    diffs = [
        abs(acc_buffer[i][0] - acc_buffer[i - 1][0])
        for i in range(1, len(acc_buffer))
    ]
    return (sum(diffs) / len(diffs)) > 0.5


def step_ui_state(state: SensorState, _now: float) -> tuple[str, str, bool, float, bool]:
    """
    Recompute finger detection, alerts, and status strings after buffers updated.

    Returns (status_msg, alert_text, moving, bpm_shown, show_override_button).
    """
    current_ir = state.ir_buffer[-1] if state.ir_buffer else 0.0
    state.finger_detected = current_ir > IR_THRESHOLD

    bpm_shown = state.bpm_display
    if not state.finger_detected:
        bpm_shown = 0.0

    moving = compute_motion(state.acc_buffer)

    alert_text = "OK"
    if bpm_shown < 60 and state.finger_detected:
        alert_text = "⚠️ Bradicardia"
    elif bpm_shown > 190:
        alert_text = "🚨 Taquicardia"

    if bpm_shown > 150 and not moving:
        alert_text = "🚨 Posible crisis"

    if state.manual_override:
        alert_text = "✔️ No es crisis"

    if not state.finger_detected:
        status_msg = "Coloca el dedo en el sensor"
    else:
        status_msg = f"BPM: {bpm_shown:.1f}"

    state.alert_text = alert_text
    show_override = moving
    return status_msg, alert_text, moving, bpm_shown, show_override
