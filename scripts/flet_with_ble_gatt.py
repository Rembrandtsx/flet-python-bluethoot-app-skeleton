#!/usr/bin/env python3
"""
Flet CLI wrapper: generate BleGattBridge.java into the Android **app package**
(e.g. com.flet.flet_bluetooth_prototype) under flutter_dir immediately before
``flutter build``.

Classes under ``dev.flet.ble`` were copied into the Gradle tree but still failed to
load via JNI on device; placing the bridge next to MainActivity fixes ClassLoader
visibility.

Also appends ProGuard/R8 keep rules for the concrete class names.

Use via ./scripts/flet-with-cert.sh (recommended) or:
  python scripts/flet_with_ble_gatt.py build apk
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_SRC_TEMPLATE = (
    ROOT
    / "android"
    / "app"
    / "src"
    / "main"
    / "java"
    / "dev"
    / "flet"
    / "ble"
    / "BleGattBridge.java"
)

_PROGUARD_MARKER = "# ble_gatt_bridge (Pyjnius)"


def _write_ble_package_hint(package_app_path: Path) -> None:
    """Ship Android package string inside the Python app (APK has no pyproject.toml)."""
    sys.path.insert(0, str(ROOT / "src"))
    try:
        from android_ble_bridge_meta import ble_bundle_package_from_pyproject
    except ImportError as exc:
        print(f"ble_gatt_sync: cannot import android_ble_bridge_meta: {exc}", file=sys.stderr)
        return
    pkg = ble_bundle_package_from_pyproject()
    dest = package_app_path / "ble_android_package.txt"
    dest.write_text(pkg + "\n", encoding="utf-8")
    print(f"ble_gatt_sync: wrote {dest} -> {pkg!r}")


def sync_ble_gatt_java(flutter_dir: Path) -> None:
    """Write BleGattBridge.java into the Flet Android app package; extend proguard."""
    sys.path.insert(0, str(ROOT / "src"))
    try:
        from android_ble_bridge_meta import ble_bundle_package_from_pyproject
    except ImportError as exc:
        print(f"ble_gatt_sync: cannot import android_ble_bridge_meta: {exc}", file=sys.stderr)
        return

    pkg = ble_bundle_package_from_pyproject()
    fqcn_bridge = f"{pkg}.BleGattBridge"
    fqcn_events = f"{pkg}.BleGattBridge$Events"

    if not _SRC_TEMPLATE.is_file():
        print(f"ble_gatt_sync: missing template {_SRC_TEMPLATE}", file=sys.stderr)
        return

    text = _SRC_TEMPLATE.read_text(encoding="utf-8")
    text = re.sub(r"^package\s+[\w.]+;", f"package {pkg};", text, count=1, flags=re.MULTILINE)

    rel = pkg.replace(".", "/")
    dest = (
        flutter_dir
        / "android"
        / "app"
        / "src"
        / "main"
        / "java"
        / rel
        / "BleGattBridge.java"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    print(f"ble_gatt_sync: wrote {fqcn_bridge} -> {dest}")

    proguard = flutter_dir / "android" / "app" / "proguard-rules.pro"
    if not proguard.is_file():
        return
    ptext = proguard.read_text(encoding="utf-8", errors="replace")
    if _PROGUARD_MARKER in ptext:
        return
    rules = (
        f"\n{_PROGUARD_MARKER}\n"
        f"-keep class {fqcn_bridge} {{ *; }}\n"
        f"-keep class {fqcn_events} {{ *; }}\n"
    )
    proguard.write_text(ptext.rstrip() + rules, encoding="utf-8")
    print(f"ble_gatt_sync: appended R8 keep rules -> {proguard}")

    # Remove stale copy under dev.flet.ble if present (avoid duplicate-class confusion)
    stale = (
        flutter_dir
        / "android"
        / "app"
        / "src"
        / "main"
        / "java"
        / "dev"
        / "flet"
        / "ble"
        / "BleGattBridge.java"
    )
    if stale.is_file():
        try:
            stale.unlink()
            print(f"ble_gatt_sync: removed stale {stale}")
        except OSError as exc:
            print(f"ble_gatt_sync: could not remove stale file: {exc}", file=sys.stderr)


def _patch_run_flutter() -> None:
    from flet_cli.commands.build_base import BaseBuildCommand

    _orig = BaseBuildCommand._run_flutter_command

    def _run_flutter_command(self) -> None:
        fd = getattr(self, "flutter_dir", None)
        if fd is not None:
            sync_ble_gatt_java(Path(fd))
        _orig(self)

    BaseBuildCommand._run_flutter_command = _run_flutter_command  # type: ignore[method-assign]


def _patch_package_python() -> None:
    from flet_cli.commands.build_base import BaseBuildCommand

    _orig = BaseBuildCommand.package_python_app

    def package_python_app(self) -> None:
        pa = getattr(self, "package_app_path", None)
        if pa is not None:
            _write_ble_package_hint(Path(pa))
        _orig(self)

    BaseBuildCommand.package_python_app = package_python_app  # type: ignore[method-assign]


def main() -> None:
    _patch_package_python()
    _patch_run_flutter()
    from flet_cli.cli import main as flet_main

    flet_main()


if __name__ == "__main__":
    main()
