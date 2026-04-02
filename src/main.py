"""
Flet UI for ESP32 biosensor: desktop uses Bleak (BLE); Android uses Pyjnius GATT only.
"""

from __future__ import annotations

import asyncio
import os
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
    TARGET_NAME,
    SensorState,
    apply_sample,
    parse_sensor_payload,
    step_ui_state,
)


def is_android() -> bool:
    return "ANDROID_ARGUMENT" in os.environ or hasattr(sys, "getandroidapilevel")


def _sparkline(ir_values: list[float], max_bars: int = 72) -> ft.Control:
    if not ir_values:
        return ft.Container(
            height=140,
            bgcolor=ft.Colors.BLACK12,
            alignment=ft.Alignment.CENTER,
            content=ft.Text("PPG (sin datos)", color=ft.Colors.GREY),
        )
    n = len(ir_values)
    step = max(1, n // max_bars)
    sampled = ir_values[::step][-max_bars:]
    lo, hi = min(sampled), max(sampled)
    if hi == lo:
        hi = lo + 1.0
    bars: list[ft.Control] = []
    for v in sampled:
        h = 12.0 + (v - lo) / (hi - lo) * 118.0
        bars.append(
            ft.Container(
                width=3,
                height=min(130.0, h),
                bgcolor=ft.Colors.TEAL_400,
            )
        )
    return ft.Container(
        height=140,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        border=ft.border.all(1, ft.Colors.GREY_400),
        border_radius=4,
        padding=ft.padding.all(4),
        content=ft.Row(bars, spacing=0, scroll=ft.ScrollMode.AUTO),
    )


async def main(page: ft.Page) -> None:
    # Android: default = Flutter BLE (flet_ble_bridge). Set FLET_USE_PYJNIUS_BLE=1 for Pyjnius GATT.
    use_pyjnius_ble = os.environ.get("FLET_USE_PYJNIUS_BLE") == "1"
    # Verbose Dart traces → in-app log (also adb logcat: lines prefixed [flet_ble_bridge]). Set FLET_BLE_BRIDGE_DEBUG=0 to hide from app.
    dart_ble_bridge_debug = os.environ.get("FLET_BLE_BRIDGE_DEBUG", "1") != "0"

    page.title = "ESP32 Biosensores"
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.padding = 12
    # Whole-screen scroll; inner Column/ListView scroll often fails without a bounded height on Android.
    page.scroll = ft.ScrollMode.AUTO

    # Copyable in-app log (for debugging on device; send this text if something fails).
    APP_LOG_MAX = 500
    _log_lines: list[str] = []

    status_text = ft.Text("Estado: listo")
    status_msg = ft.Text(
        "Coloca el dedo en el sensor",
        size=22,
        weight=ft.FontWeight.W_500,
    )
    move_text = ft.Text("Movimiento: No", size=16)
    alert_text = ft.Text("Estado: OK", size=18, color=ft.Colors.BLUE_GREY)
    chart_host = ft.Column(controls=[_sparkline([])], tight=True)

    connected_text = ft.Text("Conectado a: —", size=14, color=ft.Colors.GREY_700)
    rx_counter_text = ft.Text("RX: 0", size=14, color=ft.Colors.GREY_700)
    last_parsed_text = ft.Text("Último dato: —", size=12, color=ft.Colors.GREY_700)

    debug_title = ft.Text("Raw sensor data (debug):", size=14, weight=ft.FontWeight.W_600)
    debug_log = ft.ListView(
        height=180,
        spacing=2,
        auto_scroll=True,
        controls=[ft.Text("—", size=12, color=ft.Colors.GREY_600)],
    )

    app_log_title = ft.Text("Diagnóstico (copiar y pegar):", size=14, weight=ft.FontWeight.W_600)
    app_log_text = ft.TextField(
        value="(vacío)",
        read_only=True,
        multiline=True,
        min_lines=6,
        max_lines=14,
        text_size=11,
        border_color=ft.Colors.GREY_400,
    )

    def app_log_sync(msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        _log_lines.append(line)
        if len(_log_lines) > APP_LOG_MAX:
            del _log_lines[: len(_log_lines) - APP_LOG_MAX]
        app_log_text.value = "\n".join(_log_lines)

    # Pyjnius GATT callbacks run on Android's Bluetooth binder thread. Never call
    # page.update() or touch Flet controls from there — only enqueue; pump() applies.
    _diag_thread_queue: queue.Queue[str] = queue.Queue()
    _ui_status_queue: queue.Queue[str] = queue.Queue()

    def app_log(msg: str) -> None:
        """Safe from any thread (e.g. BluetoothGatt JNI callbacks)."""
        try:
            _diag_thread_queue.put_nowait(msg)
        except Exception:
            pass

    def app_log_ui(msg: str) -> None:
        """Call from async UI handlers (same thread as Page)."""
        app_log_sync(msg)
        page.update()

    async def clear_app_log(_) -> None:
        _log_lines.clear()
        app_log_text.value = "(vacío)"
        page.update()

    async def copy_app_log(_) -> None:
        try:
            await ft.Clipboard().set(app_log_text.value or "")
            app_log_ui("Diagnóstico: texto copiado al portapapeles.")
        except Exception as exc:
            app_log_ui(f"Diagnóstico: no se pudo copiar ({exc})")

    device_list = ft.Dropdown(
        label="Dispositivo (BLE)",
        options=[],
        expand=True,
    )

    # Can receive either:
    # - raw notification strings (current Pyjnius backend)
    # - parsed dict payloads (Bleak-style backend like interfaz_PrCo.py)
    data_queue: queue.Queue[object] = queue.Queue()
    state = SensorState()
    stop_event = threading.Event()
    ble_thread: Optional[threading.Thread] = None
    android_disconnect: Optional[Callable[[], None]] = None
    pump_running = True
    rx_count = 0

    ble_bridge: Optional[FletBleBridge] = None
    if is_android() and not use_pyjnius_ble:
        ble_bridge = FletBleBridge(
            char_uuid=CHAR_UUID,
            bridge_debug=dart_ble_bridge_debug,
            on_notification=lambda e: data_queue.put(e.text),
            on_status=lambda e: _ui_status_queue.put(e.message),
            on_bridge_log=lambda e: app_log(f"[dart] {e.message}"),
        )

    async def override_click(_) -> None:
        state.manual_override = True
        page.update()

    override_btn = ft.Button(
        content="No es crisis",
        visible=True,
        on_click=override_click,
    )

    def on_status(msg: str) -> None:
        """Safe from GATT threads too: drained in pump()."""
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
            app_log_ui(f"permisos: falta flet-permission-handler ({exc})")
            status_text.value = f"Estado: falta flet-permission-handler ({exc})"
            page.update()
            return False

        try:
            app_log_ui("permisos: solicitando BLUETOOTH_CONNECT / BLUETOOTH_SCAN...")
            ph = fph.PermissionHandler()
            await ph.request(fph.Permission.BLUETOOTH_CONNECT)
            await ph.request(fph.Permission.BLUETOOTH_SCAN)
            app_log_ui("permisos: OK")
            return True
        except Exception as exc:
            app_log_ui(f"permisos: error ({exc})")
            status_text.value = f"Estado: permiso Bluetooth denegado/err ({exc})"
            page.update()
            return False

    async def scan_devices(_) -> None:
        app_log_ui("scan_devices: inicio")
        status_text.value = "Estado: buscando..."
        page.update()
        if not is_android():
            app_log_ui("scan_devices: escritorio — no aplica emparejar")
            status_text.value = "Estado: en escritorio no hace falta emparejar (usa Conectar)"
            page.update()
            return

        if not await ensure_bt_permissions():
            app_log_ui("scan_devices: permisos no concedidos, abort")
            return

        if not use_pyjnius_ble and ble_bridge is not None:
            try:
                app_log_ui("scan_devices: Flutter BLE (flet_ble_bridge)…")
                rows = await ble_bridge.scan_ble(TARGET_NAME, timeout_ms=12000)
            except Exception as exc:
                app_log_ui(f"scan_devices: scan_ble error ({exc})")
                status_text.value = f"Estado: error scan ({exc})"
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
            if not pick:
                app_log_ui("scan_devices: sin dispositivos en escaneo BLE")
                status_text.value = "Estado: sin dispositivos"
            else:
                for d in pick:
                    app_log_ui(f"scan_devices: opción {d.name!r} {d.address}")
                status_text.value = f"Estado: {len(pick)} dispositivo(s)"
            page.update()
            return

        try:
            from bluetooth_android import list_bonded_and_connected_devices
        except Exception as exc:
            app_log_ui(f"scan_devices: import bluetooth_android falló ({exc})")
            status_text.value = f"Estado: error Pyjnius ({exc})"
            page.update()
            return
        try:
            devices = list_bonded_and_connected_devices(on_debug=app_log_ui)
            app_log_ui(f"scan_devices: lista final count={len(devices)}")
        except Exception as exc:
            app_log_ui(f"scan_devices: list_bonded_and_connected_devices error ({exc})")
            status_text.value = f"Estado: error ({exc})"
            page.update()
            return
        filtered = [d for d in devices if TARGET_NAME in (d.name or "")]
        use = filtered if filtered else devices
        device_list.options = [ft.dropdown.Option(f"{d.name} ({d.address})") for d in use]
        if not use:
            app_log_ui("scan_devices: sin dispositivos (emparejados ni GATT)")
            status_text.value = "Estado: sin dispositivos"
        else:
            for d in use:
                app_log_ui(f"scan_devices: opción {d.name!r} {d.address}")
            status_text.value = f"Estado: {len(use)} dispositivo(s)"
        page.update()

    def _parse_selection_from_dropdown() -> tuple[Optional[str], Optional[str]]:
        """
        Returns (name, mac_or_address).

        Dropdown value format: "Name (AA:BB:...)".
        """
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
        app_log_ui("connect_click: inicio (reset sesión)")
        if is_android() and not use_pyjnius_ble and ble_bridge is not None:
            try:
                await ble_bridge.disconnect_ble()
            except Exception as exc:
                app_log_ui(f"connect_click: cerrar Flutter BLE previo ({exc})")
        if android_disconnect is not None:
            app_log_ui("connect_click: cerrando sesión BLE anterior")
            try:
                stop_event.set()
                android_disconnect()
            except Exception as exc:
                app_log_ui(f"connect_click: error al cerrar anterior ({exc})")
            android_disconnect = None
        stop_event.clear()
        state.manual_override = False

        # Reset UI/debug counters for a new session.
        rx_count = 0
        connected_text.value = "Conectado a: —"
        rx_counter_text.value = "RX: 0"
        last_parsed_text.value = "Último dato: —"
        debug_log.controls = [ft.Text("—", size=12, color=ft.Colors.GREY_600)]
        page.update()

        while not data_queue.empty():
            try:
                data_queue.get_nowait()
            except queue.Empty:
                break

        if is_android():
            if not await ensure_bt_permissions():
                app_log_ui("connect_click: permisos no OK, abort")
                return
            name, mac = _parse_selection_from_dropdown()
            if not mac:
                app_log_ui("connect_click: no hay MAC seleccionada")
                status_text.value = "Estado: elige un dispositivo"
                page.update()
                return
            connected_text.value = f"Conectado a: {name or mac}"
            app_log_ui(f"connect_click: MAC={mac} name={name!r}")
            page.update()

            def raw_cb(payload: object) -> None:
                data_queue.put(payload)

            android_disconnect = None

            if not use_pyjnius_ble and ble_bridge is not None:
                try:
                    app_log_ui("connect_click: Flutter BLE (flet_ble_bridge)...")
                    ok = await ble_bridge.connect_ble(mac)
                except Exception as exc:
                    app_log_ui(f"connect_click: connect_ble excepción ({exc})")
                    status_text.value = f"Estado: Flutter BLE error ({exc})"
                    page.update()
                    return
                if not ok:
                    app_log_ui("connect_click: connect_ble devolvió false")
                    status_text.value = "Estado: no se pudo conectar (Flutter BLE)"
                else:
                    app_log_ui("connect_click: Flutter BLE conectado (notificaciones → Python)")
                page.update()
                return

            # Android: Pyjnius BluetoothGatt (opt-in via FLET_USE_PYJNIUS_BLE=1).
            try:
                from ble_android_gatt import connect_ble_notify
            except Exception as exc:
                app_log_ui(f"connect_click: import ble_android_gatt falló ({exc})")
                status_text.value = f"Estado: BLE Android no disponible ({exc})"
                page.update()
                return

            try:
                app_log_ui("connect_click: Pyjnius GATT (ble_android_gatt)...")
                android_disconnect = connect_ble_notify(
                    mac,
                    raw_cb,
                    on_status,
                    on_debug=app_log,
                )
            except Exception as exc:
                app_log_ui(f"connect_click: Pyjnius connect_ble_notify excepción ({exc})")
                status_text.value = f"Estado: Pyjnius connect error ({exc})"
                page.update()
                return

            if android_disconnect is None:
                app_log_ui("connect_click: disconnect handle es None (fallo al conectar)")
                status_text.value = "Estado: no se pudo conectar"
            else:
                app_log_ui("connect_click: sesión GATT iniciada (callback disconnect disponible)")
            page.update()
            return

        def status_sync(msg: str) -> None:
            on_status(msg)

        app_log_ui("connect_click: escritorio — iniciando Bleak (ble_desktop)")
        ble_thread = start_ble_desktop(stop_event, data_queue, status_sync, on_debug=app_log)
        page.update()

    async def disconnect_click(_) -> None:
        nonlocal android_disconnect, ble_thread
        app_log_ui("disconnect_click: desconectando...")
        stop_event.set()
        if is_android() and not use_pyjnius_ble and ble_bridge is not None:
            try:
                await ble_bridge.disconnect_ble()
            except Exception as exc:
                app_log_ui(f"disconnect_click: Flutter BLE ({exc})")
        if android_disconnect is not None:
            try:
                android_disconnect()
            except Exception:
                pass
            android_disconnect = None
        ble_thread = None
        status_text.value = "Estado: desconectado"
        app_log_ui("disconnect_click: hecho")
        page.update()

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

                # Debug: show the raw BLE notification so we can verify we're receiving data.
                # Keep only the last N messages to avoid unbounded growth.
                raw_str = str(raw).strip()
                if raw_str:
                    rx_count += 1
                    rx_counter_text.value = f"RX: {rx_count}"
                    last_parsed_text.value = f"Último dato (raw): {raw_str[:90]}"
                    if rx_count <= 5 or rx_count % 50 == 0:
                        app_log_ui(f"pump: RX#{rx_count} raw={raw_str[:120]}")
                    debug_log.controls.append(
                        ft.Text(raw_str[:160], size=11, color=ft.Colors.GREY_800)
                    )
                    if len(debug_log.controls) > 30:
                        debug_log.controls.pop(0)

                parsed = None
                if isinstance(raw, dict):
                    # Bleak-style backend already parsed the values.
                    parsed = raw
                elif isinstance(raw, str):
                    parsed = parse_sensor_payload(raw)
                else:
                    parsed = parse_sensor_payload(str(raw))

                if parsed:
                    apply_sample(state, parsed, now)
                    keys = ", ".join(sorted(parsed.keys()))
                    last_parsed_text.value = f"Último dato (parsed): [{keys}]"

            status_msg_val, alert_val, moving, _bpm_shown, show_ov = step_ui_state(state, now)
            status_msg.value = status_msg_val
            move_text.value = f"Movimiento: {'Sí' if moving else 'No'}"
            alert_text.value = f"Estado: {alert_val}"
            alert_text.color = (
                ft.Colors.RED_700
                if "crisis" in alert_val.lower() or "Taquicardia" in alert_val
                else ft.Colors.BLUE_GREY
            )
            # interfaz_PrCo.py keeps the override button always available.
            override_btn.visible = True
            chart_host.controls[0] = _sparkline(state.ir_buffer)
            page.update()

    connect_btn = ft.Button(content="Conectar / escuchar", on_click=connect_click)
    disconnect_btn = ft.OutlinedButton(content="Desconectar", on_click=disconnect_click)
    scan_btn = ft.Button(content="Buscar emparejados", on_click=scan_devices)

    controls_column = ft.Column(
        controls=[
            scan_btn if is_android() else ft.Text("(Escritorio: Conectar busca por BLE)"),
            device_list,
            ft.Row(
                controls=[connect_btn, disconnect_btn],
                wrap=True,
                spacing=8,
            ),
        ],
        spacing=10,
    )

    body = ft.Column(
        controls=[
            ft.Text(
                "PPG / crisis (ESP32 BLE)",
                theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
            ),
            status_text,
            controls_column,
            chart_host,
            status_msg,
            move_text,
            alert_text,
            override_btn,
            connected_text,
            rx_counter_text,
            last_parsed_text,
            ft.Divider(height=1, color=ft.Colors.GREY_400),
            app_log_title,
            ft.Row(
                controls=[
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
    )
    page.add(ft.SafeArea(content=body, expand=True) if is_android() else body)

    if is_android():
        app_log_ui(
            "app: arranque Android — BLE "
            + (
                "Pyjnius (FLET_USE_PYJNIUS_BLE=1)"
                if use_pyjnius_ble
                else "Flutter / flutter_blue_plus (flet_ble_bridge)"
            )
        )
    else:
        app_log_ui(f"app: arranque (android={is_android()})")

    asyncio.create_task(pump())


if __name__ == "__main__":
    try:
        import os

        import certifi

        _ca = certifi.where()
        os.environ.setdefault("SSL_CERT_FILE", _ca)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", _ca)
    except Exception:
        pass

    ft.run(main)
