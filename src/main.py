"""
FallSense prototype: flujo login → condición → monitor BLE (ESP32) + alerta simulada.
Escritorio: Bleak; Android: flet_ble_bridge (Flutter) o Pyjnius (FLET_USE_PYJNIUS_BLE=1).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import queue
import sys
import threading
import time
from collections.abc import Callable
from types import SimpleNamespace
from typing import Optional

import flet as ft

from ble_desktop import start_ble_desktop
from flet_ble_bridge import FletBleBridge
from esp32_sensor import (
    CHAR_UUID,
    IR_THRESHOLD,
    TARGET_NAME,
    SensorState,
    apply_sample,
    normalize_payload,
    step_ui_state,
)
import fallsense_ui as fsui

# Flet calls ServiceRegistry.unregister_services() after each event; it drops any Service
# whose sys.getrefcount is ≤4. Without extra strong refs, FletBleBridge can disappear right
# after connect, Dart disposes the GATT service → notifications stop → UI sticks at zeros.
# Keep one explicit ref here (do NOT use page.add for the bridge — that triggers
# "Unknown control: FletBleBridge" because Services are not view controls).
_ANDROID_BLE_BRIDGE_KEEPALIVE: list[FletBleBridge] = []


def is_android() -> bool:
    return "ANDROID_ARGUMENT" in os.environ or hasattr(sys, "getandroidapilevel")


def _sparkline(ir_values: list[float], max_bars: int = 72) -> ft.Control:
    if not ir_values:
        return ft.Container(
            height=120,
            bgcolor="#ECEFF1",
            border_radius=8,
            alignment=ft.Alignment.CENTER,
            content=ft.Text("Sin datos IR todavía", color=fsui.C_GREY_LIGHT, size=13),
        )
    n = len(ir_values)
    step = max(1, n // max_bars)
    sampled = ir_values[::step][-max_bars:]
    lo, hi = min(sampled), max(sampled)
    if hi == lo:
        hi = lo + 1.0
    bars: list[ft.Control] = []
    for v in sampled:
        h = 10.0 + (v - lo) / (hi - lo) * 100.0
        bars.append(
            ft.Container(
                width=3,
                height=min(115.0, h),
                bgcolor=fsui.C_TEAL,
            )
        )
    return ft.Container(
        height=120,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        border_radius=8,
        bgcolor=fsui.C_WHITE,
        border=ft.border.all(1, fsui.C_BORDER),
        padding=ft.padding.all(6),
        content=ft.Row(bars, spacing=0, scroll=ft.ScrollMode.AUTO),
    )


def _open_snackbar(page: ft.Page, message: str) -> None:
    sb = ft.SnackBar(ft.Text(message), duration=4000)
    try:
        page.open(sb)
    except Exception:
        page.snack_bar = sb
        page.snack_bar.open = True


async def main(page: ft.Page) -> None:
    use_pyjnius_ble = os.environ.get("FLET_USE_PYJNIUS_BLE") == "1"
    dart_ble_bridge_debug = os.environ.get("FLET_BLE_BRIDGE_DEBUG", "1") != "0"

    page.title = "FallSense"
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.padding = 0
    page.scroll = ft.ScrollMode.AUTO
    page.bgcolor = fsui.C_PAGE_BG
    page.theme_mode = ft.ThemeMode.LIGHT

    APP_LOG_MAX = 500
    _log_lines: list[str] = []

    route_holder: list[str] = ["login"]
    session_email: list[str] = [""]
    condition_selected: list[str] = [""]
    crisis_shown: list[bool] = [False]
    crisis_remaining: list[int] = [180]
    crisis_task_ref: list[Optional[asyncio.Task]] = [None]

    # —— Monitor controls (mutated by pump) ——
    status_text = ft.Text("Estado: listo", size=13, color=fsui.C_GREY)
    status_msg = ft.Text(
        "Conecta el sensor y coloca el dedo en el PPG",
        size=17,
        weight=ft.FontWeight.W_600,
        color=fsui.C_BLUE_DARK,
    )
    move_text = ft.Text("Movimiento: no detectado", size=14, color=fsui.C_GREY)
    alert_text = ft.Text("Alertas: OK", size=14, color=fsui.C_GREY)
    chart_caption = ft.Text(
        "Señal IR (PPG). Si IR≈0, la gráfica se verá plana.",
        size=11,
        color=fsui.C_GREY_LIGHT,
    )
    chart_host = ft.Column(controls=[_sparkline([])], tight=True)
    connected_text = ft.Text("Sensor: no conectado", size=13, color=fsui.C_GREY)
    rx_counter_text = ft.Text("RX: 0", size=12, color=fsui.C_GREY_LIGHT)
    last_parsed_text = ft.Text("Último dato: —", size=12, color=fsui.C_GREY_700)
    live_sensor_text = ft.Text("", size=12, color=fsui.C_GREY)
    hw_mpu_text = ft.Text(
        "Acelerómetro (MPU): —",
        size=13,
        weight=ft.FontWeight.W_500,
        color=fsui.C_GREY,
    )
    hw_max_text = ft.Text(
        "MAX30102 (PPG): —",
        size=13,
        weight=ft.FontWeight.W_500,
        color=fsui.C_GREY,
    )

    debug_log = ft.ListView(
        height=180,
        spacing=2,
        auto_scroll=True,
        controls=[ft.Text("—", size=12, color=ft.Colors.GREY_600)],
    )
    app_log_text = ft.TextField(
        value="(vacío)",
        read_only=True,
        multiline=True,
        min_lines=6,
        max_lines=14,
        text_size=11,
        border_color=fsui.C_GREY_400,
    )
    app_log_title = ft.Text(
        "Diagnóstico (copiar y pegar):",
        size=14,
        weight=ft.FontWeight.W_600,
    )
    debug_title = ft.Text(
        "Raw sensor data (debug):",
        size=14,
        weight=ft.FontWeight.W_600,
    )

    def app_log_sync(msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        _log_lines.append(line)
        if len(_log_lines) > APP_LOG_MAX:
            del _log_lines[: len(_log_lines) - APP_LOG_MAX]
        app_log_text.value = "\n".join(_log_lines)

    _diag_thread_queue: queue.Queue[str] = queue.Queue()
    _ui_status_queue: queue.Queue[str] = queue.Queue()

    def app_log(msg: str) -> None:
        try:
            _diag_thread_queue.put_nowait(msg)
        except Exception:
            pass

    def app_log_ui(msg: str) -> None:
        app_log_sync(msg)
        page.update()

    async def clear_app_log(_) -> None:
        _log_lines.clear()
        app_log_text.value = "(vacío)"
        page.update()

    async def copy_app_log(_) -> None:
        try:
            await ft.Clipboard().set(app_log_text.value or "")
            app_log_ui("Diagnóstico copiado.")
        except Exception as exc:
            app_log_ui(f"No se pudo copiar ({exc})")

    device_list = ft.Dropdown(
        hint_text="Elige un dispositivo",
        options=[],
        expand=True,
        border_color=fsui.C_BORDER,
    )

    data_queue: queue.Queue[object] = queue.Queue()
    state = SensorState()
    stop_event = threading.Event()
    ble_thread: Optional[threading.Thread] = None
    android_disconnect: Optional[Callable[[], None]] = None
    pump_running = True
    rx_count = 0

    # Created after page.add(shell): avoids tight refcount window + ensures page tree exists.
    ble_bridge: Optional[FletBleBridge] = None

    body_holder = ft.Container(expand=True)

    async def override_click(_) -> None:
        state.manual_override = True
        page.update()

    override_btn = ft.TextButton(
        "Marcar: no es episodio (override)",
        on_click=override_click,
        style=ft.ButtonStyle(color=fsui.C_TEAL),
    )

    async def reset_detection(_) -> None:
        state.manual_override = False
        crisis_shown[0] = False
        app_log_ui("Detección de episodios restablecida.")
        page.update()

    reset_detect_btn = ft.TextButton(
        "Restablecer detección de episodios (pruebas)",
        on_click=reset_detection,
        style=ft.ButtonStyle(color=fsui.C_GREY_LIGHT, padding=ft.Padding.all(4)),
    )

    def on_status(msg: str) -> None:
        try:
            _ui_status_queue.put_nowait(msg)
        except Exception:
            pass

    async def ensure_bt_permissions() -> bool:
        if not is_android():
            return True
        try:
            import flet_permission_handler as fph
        except Exception as exc:
            app_log_ui(f"permisos: flet-permission-handler ({exc})")
            return False
        try:
            app_log_ui("permisos: BLUETOOTH_CONNECT / BLUETOOTH_SCAN…")
            ph = fph.PermissionHandler()
            await ph.request(fph.Permission.BLUETOOTH_CONNECT)
            await ph.request(fph.Permission.BLUETOOTH_SCAN)
            app_log_ui("permisos: OK")
            return True
        except Exception as exc:
            app_log_ui(f"permisos: error ({exc})")
            return False

    async def scan_devices(_) -> None:
        app_log_ui("scan: inicio")
        status_text.value = "Estado: buscando dispositivos…"
        page.update()
        if not is_android():
            app_log_ui("scan: escritorio — Conectar inicia Bleak directamente")
            status_text.value = "Estado: en escritorio usa Conectar"
            page.update()
            return
        if not await ensure_bt_permissions():
            return
        if not use_pyjnius_ble and ble_bridge is not None:
            try:
                rows = await ble_bridge.scan_ble(TARGET_NAME, timeout_ms=12000)
            except Exception as exc:
                app_log_ui(f"scan: error ({exc})")
                status_text.value = f"Estado: error de escaneo"
                page.update()
                return
            use: list[SimpleNamespace] = []
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                mac = row.get("mac")
                if not mac:
                    continue
                use.append(
                    SimpleNamespace(
                        name=str(row.get("name") or ""),
                        address=str(mac),
                    )
                )
            filtered = [d for d in use if TARGET_NAME in (d.name or "")]
            pick = filtered if filtered else use
            device_list.options = [
                ft.dropdown.Option(f"{d.name or '—'} ({d.address})") for d in pick
            ]
            status_text.value = (
                f"Estado: {len(pick)} dispositivo(s)" if pick else "Estado: sin resultados"
            )
            page.update()
            return
        try:
            from bluetooth_android import list_bonded_and_connected_devices
        except Exception as exc:
            app_log_ui(f"scan: Pyjnius ({exc})")
            page.update()
            return
        try:
            devices = list_bonded_and_connected_devices(on_debug=app_log_ui)
        except Exception as exc:
            app_log_ui(f"scan: lista ({exc})")
            page.update()
            return
        filtered = [d for d in devices if TARGET_NAME in (d.name or "")]
        use = filtered if filtered else devices
        device_list.options = [ft.dropdown.Option(f"{d.name} ({d.address})") for d in use]
        status_text.value = f"Estado: {len(use)} emparejado(s)"
        page.update()

    def _parse_selection_from_dropdown() -> tuple[Optional[str], Optional[str]]:
        if not device_list.value:
            return None, None
        selected = device_list.value
        if "(" in selected and selected.endswith(")"):
            name = selected.split("(", 1)[0].strip()
            mac = selected.split("(", 1)[1].rstrip(")")
            return name or None, mac or None
        return selected, selected

    async def connect_click(_) -> None:
        nonlocal ble_thread, android_disconnect, rx_count
        app_log_ui("conectar: nueva sesión")
        if is_android() and not use_pyjnius_ble and ble_bridge is not None:
            try:
                await ble_bridge.disconnect_ble()
            except Exception:
                pass
        if android_disconnect is not None:
            try:
                stop_event.set()
                android_disconnect()
            except Exception:
                pass
            android_disconnect = None
        stop_event.clear()
        state.manual_override = False
        rx_count = 0
        connected_text.value = "Sensor: no conectado"
        rx_counter_text.value = "RX: 0"
        last_parsed_text.value = "Último dato: —"
        live_sensor_text.value = ""
        state.mpu_hw_ok = None
        state.max_hw_ok = None
        hw_mpu_text.value = "Acelerómetro (MPU): —"
        hw_max_text.value = "MAX30102 (PPG): —"
        hw_mpu_text.color = fsui.C_GREY
        hw_max_text.color = fsui.C_GREY
        debug_log.controls = [ft.Text("—", size=12, color=ft.Colors.GREY_600)]
        page.update()
        while not data_queue.empty():
            try:
                data_queue.get_nowait()
            except queue.Empty:
                break

        if is_android():
            if not await ensure_bt_permissions():
                return
            _, mac = _parse_selection_from_dropdown()
            if not mac:
                _open_snackbar(page, "Selecciona un dispositivo en la lista.")
                return
            connected_text.value = f"Sensor: {mac}"
            if not use_pyjnius_ble and ble_bridge is not None:
                try:
                    ok = await ble_bridge.connect_ble(mac)
                except Exception as exc:
                    app_log_ui(f"Flutter BLE error ({exc})")
                    page.update()
                    return
                if not ok:
                    _open_snackbar(page, "No se pudo conectar al sensor.")
                page.update()
                return
            try:
                from ble_android_gatt import connect_ble_notify
            except Exception as exc:
                app_log_ui(f"GATT Android ({exc})")
                page.update()
                return

            def raw_cb(payload: object) -> None:
                data_queue.put(payload)

            try:
                android_disconnect = connect_ble_notify(
                    mac, raw_cb, on_status, on_debug=app_log
                )
            except Exception as exc:
                app_log_ui(f"Pyjnius ({exc})")
                page.update()
                return
            page.update()
            return

        def status_sync(msg: str) -> None:
            on_status(msg)

        ble_thread = start_ble_desktop(stop_event, data_queue, status_sync, on_debug=app_log)
        connected_text.value = "Sensor: escritorio (Bleak)"
        page.update()

    async def disconnect_click(_) -> None:
        nonlocal android_disconnect, ble_thread
        stop_event.set()
        if is_android() and not use_pyjnius_ble and ble_bridge is not None:
            try:
                await ble_bridge.disconnect_ble()
            except Exception:
                pass
        if android_disconnect is not None:
            try:
                android_disconnect()
            except Exception:
                pass
            android_disconnect = None
        ble_thread = None
        status_text.value = "Estado: desconectado"
        connected_text.value = "Sensor: no conectado"
        page.update()

    def cancel_crisis_timer() -> None:
        t = crisis_task_ref[0]
        if t is not None and not t.done():
            t.cancel()
        crisis_task_ref[0] = None

    async def crisis_countdown() -> None:
        try:
            while crisis_remaining[0] > 0:
                await asyncio.sleep(1)
                crisis_remaining[0] -= 1
                if route_holder[0] != "crisis":
                    return
                m, s = divmod(crisis_remaining[0], 60)
                crisis_timer_text.value = f"{m}:{s:02d}"
                page.update()
            if route_holder[0] == "crisis":
                _open_snackbar(page, "Alerta enviada a contactos (simulado).")
                crisis_shown[0] = False
                crisis_remaining[0] = 180
                cancel_crisis_timer()
                route_holder[0] = "home"
                body_holder.content = build_home()
                page.update()
        except asyncio.CancelledError:
            pass

    crisis_timer_text = ft.Text(
        "3:00",
        size=44,
        weight=ft.FontWeight.W_700,
        color=fsui.C_BLUE,
    )

    async def crisis_cancel_click(_) -> None:
        cancel_crisis_timer()
        state.manual_override = True
        crisis_shown[0] = False
        crisis_remaining[0] = 180
        route_holder[0] = "resolved"
        body_holder.content = build_resolved()
        page.update()

    async def resolved_to_home(_) -> None:
        route_holder[0] = "home"
        body_holder.content = build_home()
        page.update()

    # —— Login / condition / home builders ——
    login_email = fsui.styled_email_field()
    login_password = fsui.styled_password_field()
    login_err = ft.Text("", color=fsui.C_RED_ALERT, size=12)

    async def do_login(_) -> None:
        if not fsui.is_valid_email(login_email.value or ""):
            login_err.value = "Introduce un correo electrónico válido."
            page.update()
            return
        login_err.value = ""
        session_email[0] = (login_email.value or "").strip()
        route_holder[0] = "condition"
        body_holder.content = build_condition()
        page.update()

    async def do_register(_) -> None:
        _open_snackbar(
            page,
            "Registro: no implementado en este prototipo. Usa Iniciar sesión con cualquier contraseña.",
        )

    def _condition_options() -> list[ft.Control]:
        opts = []
        sel = condition_selected[0] if condition_selected else ""

        def pick_factory(label: str):
            async def pick(_):
                condition_selected.clear()
                condition_selected.append(label)
                body_holder.content = build_condition()
                page.update()

            return pick

        for cond in fsui.CONDITIONS:
            is_sel = cond == sel
            opts.append(
                ft.Container(
                    on_click=pick_factory(cond),
                    border_radius=12,
                    bgcolor=fsui.C_TEAL_LIGHT if is_sel else "#F5F5F5",
                    padding=ft.padding.symmetric(horizontal=16, vertical=14),
                    border=ft.border.all(2, fsui.C_TEAL) if is_sel else None,
                    content=ft.Text(
                        cond,
                        size=15,
                        color=fsui.C_WHITE if is_sel else fsui.C_BLUE_DARK,
                        weight=ft.FontWeight.W_500,
                    ),
                )
            )
        return opts

    cond_err = ft.Text("", color=fsui.C_RED_ALERT, size=12)

    async def do_condition_continue(_) -> None:
        if not condition_selected or not condition_selected[0]:
            cond_err.value = "Selecciona una condición."
            page.update()
            return
        cond_err.value = ""
        route_holder[0] = "home"
        body_holder.content = build_home()
        page.update()

    def build_condition() -> ft.Control:
        return fsui.screen_condition(
            _condition_options(),
            cond_err,
            do_condition_continue,
        )

    async def close_debug_page(_) -> None:
        route_holder[0] = "login"
        body_holder.content = build_login()
        page.update()

    def build_debug() -> ft.Control:
        """Legacy-style full BLE / parser / log screen (same control instances as home)."""
        return ft.Container(
            expand=True,
            bgcolor=fsui.C_PAGE_BG,
            padding=ft.padding.symmetric(horizontal=14, vertical=12),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.IconButton(
                                icon=ft.Icons.ARROW_BACK,
                                tooltip="Volver al inicio de sesión",
                                on_click=close_debug_page,
                            ),
                            ft.Text(
                                "Depuración BLE",
                                size=18,
                                weight=ft.FontWeight.W_700,
                                color=fsui.C_BLUE_DARK,
                                expand=True,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        "PPG / crisis (ESP32 BLE) — vista técnica",
                        size=12,
                        color=fsui.C_GREY,
                    ),
                    ft.Text(
                        "Formato ESP32: MPU:OK|FAIL,MAX:OK|FAIL,AX..GZ,IR,BPM",
                        size=11,
                        color=fsui.C_GREY_LIGHT,
                    ),
                    ft.Divider(height=1, color=ft.Colors.GREY_400),
                    status_text,
                    scan_btn if is_android() else ft.Text("(Escritorio: Conectar inicia Bleak)", size=12),
                    device_list,
                    ft.Row(
                        [connect_btn, disconnect_btn],
                        wrap=True,
                        spacing=8,
                    ),
                    chart_caption,
                    chart_host,
                    status_msg,
                    move_text,
                    alert_text,
                    override_btn,
                    connected_text,
                    rx_counter_text,
                    last_parsed_text,
                    hw_mpu_text,
                    hw_max_text,
                    live_sensor_text,
                    reset_detect_btn,
                    ft.Divider(height=1, color=ft.Colors.GREY_400),
                    app_log_title,
                    ft.Row(
                        [
                            ft.Button(content="Copiar diagnóstico", on_click=copy_app_log),
                            ft.OutlinedButton(content="Vaciar diagnóstico", on_click=clear_app_log),
                        ],
                        spacing=8,
                        wrap=True,
                    ),
                    app_log_text,
                    ft.Divider(height=1, color=ft.Colors.GREY_400),
                    debug_title,
                    debug_log,
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

    _logo_secret_taps: list[int] = [0]
    _logo_secret_last: list[float] = [0.0]
    _LOGO_SECRET_GAP_S = 4.0

    async def on_logo_secret_easter(_) -> None:
        """Hidden: tap the login logo 5 times within a few seconds to open BLE debug."""
        now = time.time()
        if now - _logo_secret_last[0] > _LOGO_SECRET_GAP_S:
            _logo_secret_taps[0] = 0
        _logo_secret_last[0] = now
        _logo_secret_taps[0] += 1
        if _logo_secret_taps[0] < 5:
            return
        _logo_secret_taps[0] = 0
        route_holder[0] = "debug"
        body_holder.content = build_debug()
        page.update()
        app_log_ui("Depuración: acceso oculto (logo ×5)")

    def build_login() -> ft.Control:
        return fsui.screen_login(
            login_email,
            login_password,
            login_err,
            do_login,
            do_register,
            on_logo_secret_tap=on_logo_secret_easter,
        )

    def build_home() -> ft.Control:
        sub = (
            f"{session_email[0]} · Condición: {condition_selected[0] or '—'}"
            if session_email[0]
            else ""
        )
        header = ft.Column(
            [
                fsui.logo_block(compact=True),
                ft.Text("Monitor", size=20, weight=ft.FontWeight.W_700, color=fsui.C_BLUE_DARK),
                ft.Text(sub, size=12, color=fsui.C_GREY),
                ft.Row(
                    [
                        ft.Container(expand=True, content=connected_text),
                        rx_counter_text,
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        )
        connection_card = fsui.card(
            "Conexión del sensor",
            ft.Column(
                [
                    status_text,
                    ft.Container(height=8),
                    scan_btn if is_android() else ft.Text("Escritorio: pulsa Conectar.", size=12),
                    device_list,
                    ft.Row(
                        [connect_btn, disconnect_btn],
                        wrap=True,
                        spacing=8,
                    ),
                ],
                spacing=6,
                tight=True,
            ),
        )
        vitals_card = fsui.card(
            "Signos vitales y movimiento",
            ft.Column(
                [
                    status_msg,
                    ft.Row(
                        [
                            ft.Column(
                                [hw_mpu_text, hw_max_text],
                                spacing=4,
                                tight=True,
                            ),
                        ],
                    ),
                    move_text,
                    alert_text,
                    live_sensor_text,
                    ft.Row([override_btn, reset_detect_btn], wrap=True),
                ],
                spacing=6,
                tight=True,
            ),
        )
        chart_block = fsui.card(
            "PPG (plethysmograph)",
            ft.Column([chart_caption, chart_host], tight=True),
        )
        return fsui.screen_home_shell(
            header,
            connection_card,
            vitals_card,
            chart_block,
        )

    def build_resolved() -> ft.Control:
        return fsui.screen_resolved(resolved_to_home)

    def build_crisis() -> ft.Control:
        return fsui.screen_crisis(crisis_timer_text, crisis_cancel_click)

    def enter_crisis_flow() -> None:
        crisis_remaining[0] = 180
        crisis_timer_text.value = "3:00"
        route_holder[0] = "crisis"
        crisis_shown[0] = True
        body_holder.content = build_crisis()
        cancel_crisis_timer()
        crisis_task_ref[0] = asyncio.create_task(crisis_countdown())
        _open_snackbar(page, "FallSense: posible episodio — revisa la pantalla.")
        page.update()

    scan_btn = ft.Button(
        "Buscar dispositivos BLE",
        on_click=scan_devices,
        style=ft.ButtonStyle(bgcolor=fsui.C_TEAL, color=fsui.C_WHITE),
    )
    connect_btn = ft.Button(
        "Conectar",
        on_click=connect_click,
        style=ft.ButtonStyle(bgcolor=fsui.C_BLUE, color=fsui.C_WHITE),
    )
    disconnect_btn = ft.OutlinedButton("Desconectar", on_click=disconnect_click)

    async def pump() -> None:
        nonlocal rx_count
        while pump_running:
            await asyncio.sleep(0.2)
            now = time.time()

            while True:
                try:
                    line = _diag_thread_queue.get_nowait()
                except queue.Empty:
                    break
                app_log_sync(line)

            while True:
                try:
                    st = _ui_status_queue.get_nowait()
                except queue.Empty:
                    break
                status_text.value = f"Estado: {st}"
                app_log_sync(f"[estado] {st}")

            while not data_queue.empty():
                try:
                    raw = data_queue.get_nowait()
                except queue.Empty:
                    break
                raw_str = str(raw).strip()
                if raw_str:
                    rx_count += 1
                    rx_counter_text.value = f"RX: {rx_count}"
                    last_parsed_text.value = f"Último dato (raw): {raw_str[:90]}"
                    if rx_count <= 5 or rx_count % 50 == 0:
                        app_log_sync(f"pump: RX#{rx_count} raw={raw_str[:120]}")
                    debug_log.controls.append(
                        ft.Text(raw_str[:160], size=11, color=ft.Colors.GREY_800)
                    )
                    if len(debug_log.controls) > 30:
                        debug_log.controls.pop(0)

                parsed = normalize_payload(raw)

                if parsed:
                    apply_sample(state, parsed, now)
                    keys = ", ".join(sorted(parsed.keys()))
                    last_parsed_text.value = f"Último dato (parsed): [{keys}]"
                    ax = float(parsed.get("AX", 0.0))
                    ay = float(parsed.get("AY", 0.0))
                    az = float(parsed.get("AZ", 0.0))
                    gx = float(parsed.get("GX", 0.0))
                    gy = float(parsed.get("GY", 0.0))
                    gz = float(parsed.get("GZ", 0.0))
                    ir_v = float(parsed.get("IR", 0.0))
                    bpm_v = float(parsed.get("BPM", 0.0))
                    mag = (ax * ax + ay * ay + az * az) ** 0.5
                    gyro_part = (
                        f" · GX {gx:.2f} · GY {gy:.2f} · GZ {gz:.2f}"
                        if any(k in parsed for k in ("GX", "GY", "GZ"))
                        else ""
                    )
                    live_sensor_text.value = (
                        f"AX {ax:.2f} · AY {ay:.2f} · AZ {az:.2f} · |A| {mag:.2f}{gyro_part} · "
                        f"IR {ir_v:.0f} · BPM {bpm_v:.1f} (dedo si IR>{IR_THRESHOLD})"
                    )
                    if state.mpu_hw_ok is not None:
                        hw_mpu_text.value = (
                            f"Acelerómetro (MPU): {'OK' if state.mpu_hw_ok else 'Fallo'}"
                        )
                        hw_mpu_text.color = (
                            fsui.C_TEAL if state.mpu_hw_ok else fsui.C_RED_ALERT
                        )
                    if state.max_hw_ok is not None:
                        hw_max_text.value = (
                            f"MAX30102 (PPG): {'OK' if state.max_hw_ok else 'Fallo'}"
                        )
                        hw_max_text.color = (
                            fsui.C_TEAL if state.max_hw_ok else fsui.C_RED_ALERT
                        )

            if route_holder[0] in ("home", "debug"):
                status_msg_val, alert_val, moving, _bpm_shown, _ = step_ui_state(
                    state, now
                )
                status_msg.value = status_msg_val
                move_text.value = (
                    f"Movimiento: {'detectado' if moving else 'no detectado'}"
                )
                alert_text.value = f"Alertas: {alert_val}"
                alert_text.color = (
                    fsui.C_RED_ALERT
                    if "crisis" in alert_val.lower() or "Taquicardia" in alert_val
                    else fsui.C_GREY
                )
                chart_host.controls[0] = _sparkline(state.ir_buffer)

                if (
                    route_holder[0] == "home"
                    and not crisis_shown[0]
                    and not state.manual_override
                    and "posible crisis" in alert_val.lower()
                ):
                    enter_crisis_flow()
                    continue

            page.update()

    # —— Initial route ——
    body_holder.content = build_login()
    shell = ft.SafeArea(content=body_holder, expand=True) if is_android() else body_holder
    page.add(shell)

    if is_android() and not use_pyjnius_ble:
        ble_bridge = FletBleBridge(
            char_uuid=CHAR_UUID,
            bridge_debug=dart_ble_bridge_debug,
            on_notification=lambda e: data_queue.put(e.text),
            on_status=lambda e: _ui_status_queue.put(e.message),
            on_bridge_log=lambda e: app_log(f"[dart] {e.message}"),
        )
        _ANDROID_BLE_BRIDGE_KEEPALIVE.clear()
        _ANDROID_BLE_BRIDGE_KEEPALIVE.append(ble_bridge)

    if is_android():
        app_log_ui(
            "FallSense — "
            + (
                "BLE Pyjnius"
                if use_pyjnius_ble
                else "BLE Flutter (flet_ble_bridge)"
            )
        )
    else:
        app_log_ui("FallSense — escritorio (Bleak)")

    asyncio.create_task(pump())


if __name__ == "__main__":
    try:
        import certifi

        _ca = certifi.where()
        os.environ.setdefault("SSL_CERT_FILE", _ca)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", _ca)
    except Exception:
        pass

    # Resolve `src/assets/` regardless of CWD (Logo.png and other static files).
    _assets = Path(__file__).resolve().parent / "assets"
    ft.run(main, assets_dir=str(_assets))
