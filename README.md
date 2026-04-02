# Flet Bluetooth Prototype Skeleton

This repository is a **minimal Flet app skeleton** you can use to prototype and test Bluetooth connections to a device/sensor from Python, with a UI that can be packaged for Android.

It includes an Android-only helper that uses **Pyjnius** to call native Bluetooth APIs (see [Tap into native Android and iOS APIs with Pyjnius and Pyobjus](https://flet.dev/blog/tap-into-native-android-and-iOS-apis-with-Pyjnius-and-pyobjus/)).

---

## 1. Project Structure

- `src/main.py` – Flet UI with:
  - "Scan for devices" (lists **bonded Android devices** via Pyjnius when running on Android).
  - dropdown listing devices as `"Name (MAC)"`.
  - "Connect" button which opens a classic Bluetooth RFCOMM connection and streams raw data into the log.
  - log area to confirm that bytes are being received from the sensor.
- `requirements.txt` – Python dependencies:
  - `flet` – UI framework
  - `bleak` – optional cross-platform BLE library for desktop experiments
  - `pyjnius` – Android-only dependency, used to call native Bluetooth APIs
- `src/bluetooth_android.py` – helper module using Pyjnius to:
  - list already-paired (bonded) devices via `BluetoothAdapter.getBondedDevices()`
  - open an RFCOMM socket to a selected device and stream incoming bytes
- `pyproject.toml` – Flet metadata: `[tool.flet.app]` points at `path = "src"` and `module = "main"` (required by current `flet build`), plus Android-only `pyjnius`.

---

## 2. Prerequisites

- **Python**: 3.10 or newer (recommended 3.10–3.12)
- **pip**: the Python package manager
- **Git** (optional, for version control)

Check versions:

```bash
python --version
pip --version
```

On some systems you may need to use `python3` / `pip3` instead of `python` / `pip`.

---

## 3. Setup on macOS

### 3.1. Install Python (if needed)

You can install Python using Homebrew:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python
```

### 3.2. Create and activate a virtual environment

From the project root (`flet-python-bluethoot-app-skeleton`):

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Your shell prompt should show `(.venv)` when the environment is active.

To deactivate later:

```bash
deactivate
```

### 3.3. Install dependencies

With the virtual environment activated:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3.4. Run the app on macOS (desktop)

From the project root, with the venv active:

```bash
python src/main.py
```

By default, Flet will open a desktop window with the Bluetooth prototype UI.

---

## 4. Setup on Windows

### 4.1. Install Python

1. Download the latest Python 3 installer from the official website.
2. During installation, **check "Add Python to PATH"**.

After installation, verify:

```powershell
python --version
pip --version
```

### 4.2. Create and activate a virtual environment

In **PowerShell** or **Command Prompt** from the project root:

```powershell
python -m venv .venv
```

Activate:

```powershell
.venv\Scripts\activate
```

The prompt should now show `(.venv)`.

To deactivate later:

```powershell
deactivate
```

### 4.3. Install dependencies

With the virtual environment active:

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

### 4.4. Run the app on Windows (desktop)

From the project root, with venv active:

```powershell
python src/main.py
```

A Flet window should open with the Bluetooth prototype UI.

---

## 5. Android – Overview and Options

There are two main ways to test your Flet UI on Android:

- **Option A – Quick testing via web / Flet app**
- **Option B – Build a native Android APK / AAB with `flet build`**

For **Bluetooth testing on real hardware**, you generally want **Option B**, but **Option A** is very convenient for quickly iterating on UI.

---

## 6. Option A – Quick Android testing (no build)

### 6.1. Run the app as a web app

You can make Flet serve the app over HTTP and access it from Android (emulator or device).

Update the bottom of `src/main.py` like this:

```python
if __name__ == "__main__":
    # Runs as a web app; you can open it from Android browser.
    ft.app(target=main, view=ft.AppView.WEB_BROWSER)
```

Then run:

```bash
python src/main.py
```

Flet will log a local URL, typically `http://127.0.0.1:8550` or similar.

#### On Android emulator

- If you run the emulator on the **same machine**, you can often access the same localhost via:
  - `http://10.0.2.2:8550` in the emulator browser (for standard Android emulators).
- Type that URL in the emulator’s browser to load the app.

#### On physical Android device (same network)

1. Ensure your computer and Android device are on the **same Wi‑Fi network**.
2. Find your computer’s local IP:

   - **macOS**:
     ```bash
     ipconfig getifaddr en0
     ```
     (or `en1` depending on your adapter)
   - **Windows**:
     ```powershell
     ipconfig
     ```
3. Replace `127.0.0.1` in the Flet URL with this IP, for example:
   - `http://192.168.1.23:8550`
4. Open that URL in Chrome on your Android device.

This is enough to test **UI flows**. For **Bluetooth**, access to hardware from the browser is limited and depends on Web Bluetooth support on your device and browser.

---

## 7. Option B – Build a native Android app

For full Bluetooth access (using something like `bleak` inside your Python code), you want a **native Android package**.

Flet uses a build pipeline based on Flutter and the Android SDK. The core steps are:

### 7.1. Requirements (both macOS and Windows)

- **Java JDK 17**
- **Android SDK + platform tools** (installed via Android Studio)
- **Flet CLI** (already installed when you installed `flet`, but verify)

Verify Flet CLI:

```bash
flet --version
```

If that fails, install the CLI:

```bash
pip install flet
```

Make sure `flet` is on your PATH (usually handled automatically by the Python venv).

### 7.2. Install Android Studio & SDK

1. Download and install Android Studio from the official website.
2. Start Android Studio and run the **Android SDK** and **SDK Platform-Tools** setup via:
   - `More Actions` → `SDK Manager` (or `Settings` → `Appearance & Behavior` → `System Settings` → `Android SDK`).
3. Ensure at least one recent Android platform (e.g. Android 13/14) is installed.

When `flet build` runs `flutter doctor`, you may see **Android toolchain** warnings. Current Flutter often expects a specific **Android SDK platform** (for example **API 36**) and **Android Build-Tools** (for example **28.0.3**). Install those exact items in **SDK Manager** (SDK Platforms + SDK Tools), then run `flutter doctor` again until Android is clean enough to build.

You can ignore **Xcode / CocoaPods** warnings if you only build for **Android**.

---

## 8. Creating a Flet Android build

Layout used here:

- `pyproject.toml` – project metadata and `[tool.flet.app]` (`path = "src"`, `module = "main"`)
- `src/main.py` – app entry point (this is what `flet build` looks for under the app path)

You can build an Android APK (release build):

On **macOS** with Python from python.org, run builds through the helper script so HTTPS downloads (Flutter SDK, etc.) verify certificates:

```bash
./scripts/flet-with-cert.sh build apk
```

Or an Android App Bundle (AAB):

```bash
./scripts/flet-with-cert.sh build aab
```

If you prefer plain `flet build`, set the same environment variables first (see **12. Troubleshooting** below).

After the build completes, Flet will create an output directory (typically something like `build/android`). Inside you will find:
   - `*.apk` files
   - optionally, `*.aab` files

---

## 9. Run on Android emulator

### 9.1. Create an emulator (AVD) in Android Studio

1. Open Android Studio.
2. Go to **Device Manager**.
3. Click **Create device**.
4. Choose a phone device definition (e.g. Pixel 6).
5. Choose a system image (Android version) and download it if needed.
6. Finish the wizard to create the AVD.

### 9.2. Start the emulator

In Device Manager, click the **Run** (play) icon next to your AVD to start it.

### 9.3. Install your APK on the emulator

From your project root, once you have an APK (e.g. `build/android/app-release.apk`):

```bash
adb install -r path/to/your.apk
```

Notes:

- Make sure `adb` (Android Debug Bridge) is in your PATH. It is part of the Android SDK `platform-tools`.
- Use `-r` to replace an existing install.

The app should then appear in the emulator’s app drawer. Launch it like a normal app.

---

## 10. Run on a physical Android device

### 10.1. Enable developer options and USB debugging

On your Android device:

1. Go to **Settings → About phone**.
2. Tap **Build number** 7 times to enable Developer options.
3. Go to **Settings → System → Developer options** (location may vary).
4. Enable **USB debugging**.

### 10.2. Connect device to your computer

- Connect via USB cable.
- If prompted on the device, **allow USB debugging** for this computer.

Verify the device is visible:

```bash
adb devices
```

You should see a device ID listed as `device`.

### 10.3. Install the APK

From the project root:

```bash
adb install -r path/to/your.apk
```

The app will be installed on the device; find it in the app drawer and launch it.

---

## 11. Where the native Bluetooth logic lives

The current code is designed to:

- Use **Pyjnius** on Android to:
  - list already-paired devices (`bluetooth_android.list_bonded_devices()`)
  - connect and start reading raw bytes (`bluetooth_android.connect_and_read()`)
- Keep desktop runs working:
  - `src/main.py` imports `bluetooth_android` lazily inside event handlers, so running on macOS/Windows without Pyjnius just logs a friendly error instead of crashing.

If you want to extend this:

- Add filtering by device name or MAC in `scan_devices()`.
- Parse the raw chunks received in `on_data()` and update additional UI elements (charts, numerical readouts, etc.).
- If your sensor uses a different profile than classic SPP, adjust the UUID and connection code in `src/bluetooth_android.py` to match.

---

## 12. Troubleshooting

- **Flet window does not appear**:
  - Check terminal for errors.
  - Upgrade `flet`:
    ```bash
    pip install --upgrade flet
    ```
- **`flet` command not found**:
  - Make sure your virtual environment is activated.
  - Reinstall: `pip install flet`.
- **`adb` not found**:
  - Ensure Android SDK `platform-tools` are installed and in your PATH.
- **Build errors when running `flet build`**:
  - Check that JDK 17 is installed and set as default.
  - Confirm Android SDK location is properly configured (Android Studio usually handles this).
  - **`main.py not found in the root of Flet app directory`**: current Flet expects `[tool.flet.app]` in `pyproject.toml` with `path` (folder containing your module) and `module` (filename without `.py`). This repo uses `path = "src"` and `module = "main"` so the file must be `src/main.py`. Alternatively pass `--module-name main` only if `main.py` sits next to `pyproject.toml`.
  - **`Flutter requires Android SDK 36` / Build-Tools**: open Android Studio → **SDK Manager** → **SDK Platforms** and install the API level Flutter asks for; under **SDK Tools** enable **Show Package Details** and install the requested **Android SDK Build-Tools** version (e.g. 28.0.3).

- **`SSL: CERTIFICATE_VERIFY_FAILED` on macOS (Python from python.org)** — affects anything that uses Python’s HTTPS, including:
  - **`python src/main.py`** — first-time download of the Flet desktop client.
  - **`flet build`** — download of the Flutter SDK and other artifacts.

  **Fix (recommended):** ensure `certifi` is installed (`pip install -r requirements.txt`), then either:

  - Use the project script for CLI builds:
    ```bash
    chmod +x scripts/flet-with-cert.sh   # once
    ./scripts/flet-with-cert.sh build aab
    ```
  - Or set the same variables in your shell before `python src/main.py` or `flet …`:
    ```bash
    export SSL_CERT_FILE="$(python -c 'import certifi; print(certifi.where())')"
    export REQUESTS_CA_BUNDLE="$SSL_CERT_FILE"
    flet build aab
    ```

  The app entrypoint in `src/main.py` already sets these for **`python src/main.py`** / desktop runs; the CLI does not, so you must export or use `scripts/flet-with-cert.sh` for builds.

  **If it still fails:** run Apple’s certificate installer for your Python, e.g. `/Applications/Python 3.12/Install Certificates.command`.

---

## 13. Next steps

- Pair your real sensor in Android Settings, then run the built APK and verify:
  - Scan shows your device.
  - Connect establishes a session and data starts appearing in the log.
- Once you trust the Android ↔ sensor path, start porting your existing PC-side data processing logic into this app (or keep it on the Python side and just stream raw data).

