import flet as ft


def main(page: ft.Page) -> None:
    page.title = "Bluetooth Prototype Skeleton"
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.vertical_alignment = ft.MainAxisAlignment.START

    status_text = ft.Text("Bluetooth status: idle")
    log_output = ft.ListView(expand=True, spacing=4, auto_scroll=True)

    device_list = ft.Dropdown(
        label="Discovered devices",
        options=[],
        width=400,
    )

    async def log(message: str) -> None:
        log_output.controls.append(ft.Text(message, size=12))
        await page.update_async()

    async def scan_devices(_):
        await log("Starting Bluetooth scan on Android (bonded devices)...")
        status_text.value = "Bluetooth status: scanning..."
        await page.update_async()

        try:
            # Import inside handler so desktop runs without Pyjnius.
            from bluetooth_android import list_bonded_devices
        except Exception as exc:
            await log(f"Android Bluetooth not available in this environment: {exc}")
            status_text.value = "Bluetooth status: error (see log)"
            await page.update_async()
            return

        try:
            devices = list_bonded_devices()
        except Exception as exc:
            await log(f"Error listing bonded devices: {exc}")
            status_text.value = "Bluetooth status: error (see log)"
            await page.update_async()
            return

        if not devices:
            await log("No bonded devices found. Pair your sensor in Android Settings first.")
            status_text.value = "Bluetooth status: no bonded devices"
            await page.update_async()
            return

        device_list.options = [
            ft.dropdown.Option(f"{d.name} ({d.address})") for d in devices
        ]
        await log(f"Found {len(devices)} bonded devices.")

        status_text.value = "Bluetooth status: scan complete"
        await page.update_async()

    async def connect_device(_):
        if not device_list.value:
            await log("No device selected.")
            return

        # Value format: "Name (AA:BB:CC:DD:EE:FF)"
        selected = device_list.value
        if "(" in selected and selected.endswith(")"):
            mac = selected.split("(", 1)[1].rstrip(")")
        else:
            mac = selected

        await log(f"Attempting to connect to {selected}...")
        status_text.value = "Bluetooth status: connecting..."
        await page.update_async()

        try:
            from bluetooth_android import connect_and_read
        except Exception as exc:
            await log(f"Android Bluetooth not available in this environment: {exc}")
            status_text.value = "Bluetooth status: error (see log)"
            await page.update_async()
            return

        def on_data(chunk: str) -> None:
            # Called from a background thread; use `page.add` via `call_from_thread`.
            def _append():
                log_output.controls.append(ft.Text(chunk.rstrip(), size=12))
                page.update()

            page.call_from_thread(_append)

        try:
            t = connect_and_read(mac, on_data=on_data)
        except Exception as exc:
            await log(f"Error starting connection: {exc}")
            status_text.value = "Bluetooth status: error (see log)"
            await page.update_async()
            return

        if t is None:
            await log("Failed to start Bluetooth reader thread. See previous errors.")
            status_text.value = "Bluetooth status: connection failed"
            await page.update_async()
            return

        await log(f"Connected to {selected}. Waiting for data...")
        status_text.value = "Bluetooth status: connected (reading...)"
        await page.update_async()

    scan_button = ft.ElevatedButton("Scan for devices", on_click=scan_devices)
    connect_button = ft.ElevatedButton("Connect", on_click=connect_device)

    layout = ft.Column(
        controls=[
            ft.Text("Flet Bluetooth Prototype Skeleton", style=ft.TextThemeStyle.TITLE_MEDIUM),
            status_text,
            ft.Row(controls=[scan_button, device_list, connect_button], wrap=True),
            ft.Text("Log:", weight=ft.FontWeight.BOLD),
            log_output,
        ],
        expand=True,
        spacing=10,
    )

    page.add(layout)


if __name__ == "__main__":
    # Help HTTPS (e.g. Flet downloading the desktop client) on macOS/Python.org installs
    # where the default SSL store is incomplete. See README "SSL certificate errors".
    try:
        import os

        import certifi

        _ca = certifi.where()
        os.environ.setdefault("SSL_CERT_FILE", _ca)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", _ca)
    except Exception:
        pass

    # For Android build/run, the entry point is still `main()`.
    ft.run(main)

