#!/usr/bin/env python3
"""
Flet CLI wrapper: generate BleGattBridge.java into the Android **app package**
(e.g. com.flet.flet_bluetooth_prototype) under flutter_dir immediately before
``flutter build``.

Classes under ``dev.flet.ble`` were copied into the Gradle tree but still failed to
load via JNI on device; placing the bridge next to MainActivity fixes ClassLoader
visibility.

Also appends ProGuard/R8 keep rules for the concrete class names.

Use via ./scripts/flet-with-cert.sh (macOS/Linux), scripts\\flet-with-cert.ps1 (Windows), or:
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

_GRADLE_NET_MARKER = "# ble_gatt: gradle network patch"
_GRADLE_STABILITY_MARKER = "# ble_gatt: gradle windows stability"
_EXTRACT_ANN_WORKAROUND_MARKER = "// ble_gatt: extractReleaseAnnotations workaround"
_MAVEN_CENTRAL_MIRROR = "https://maven-central.storage-download.googleapis.com/maven2/"


def _read_flutter_sdk_path(flutter_dir: Path) -> Path | None:
    lp = flutter_dir / "android" / "local.properties"
    if not lp.is_file():
        return None
    for raw in lp.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("flutter.sdk="):
            return Path(line.split("=", 1)[1].strip())
    return None


def _patch_flutter_tools_gradle_settings(flutter_sdk: Path) -> None:
    """Patch Flutter's included :gradle composite build (its own settings.gradle.kts)."""
    path = flutter_sdk / "packages" / "flutter_tools" / "gradle" / "settings.gradle.kts"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    if _MAVEN_CENTRAL_MIRROR in text:
        return
    needle = (
        "        google()\n"
        "        mavenCentral()\n"
        "    }\n"
        "}\n"
    )
    insert = (
        "        google()\n"
        "        maven {\n"
        f'            url = uri("{_MAVEN_CENTRAL_MIRROR}")\n'
        "        }\n"
        "        mavenCentral()\n"
        "    }\n"
        "}\n"
    )
    if needle not in text:
        return
    path.write_text(text.replace(needle, insert, 1), encoding="utf-8")
    print(f"ble_gatt_sync: Maven Central mirror (Flutter :gradle) -> {path}")


def _patch_gradle_network(flutter_dir: Path) -> None:
    """Help Gradle reach Kotlin/Maven artifacts (IPv4 + Google-hosted Maven Central mirror).

    Some Windows networks fail HTTPS to repo.maven.apache.org; the Google mirror and
    preferIPv4Stack often fix resolution for the Flutter :gradle included build.
    """
    android = flutter_dir / "android"
    if not android.is_dir():
        return

    _patch_gradle_properties_network(android / "gradle.properties")
    _patch_gradle_properties_stability(android / "gradle.properties")
    _patch_settings_repositories(android / "settings.gradle.kts")
    _patch_root_build_repositories(android / "build.gradle.kts")
    _patch_build_gradle_extract_annotations_workaround(android / "build.gradle.kts")
    sdk = _read_flutter_sdk_path(flutter_dir)
    if sdk is not None:
        _patch_flutter_tools_gradle_settings(sdk)


def _patch_gradle_properties_network(path: Path) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    if _GRADLE_NET_MARKER in text:
        return
    flag = "-Djava.net.preferIPv4Stack=true"
    lines: list[str] = []
    for line in text.splitlines(keepends=True):
        if line.startswith("org.gradle.jvmargs=") and flag not in line:
            line = line.rstrip("\r\n") + " " + flag + "\n"
        lines.append(line)
    out = "".join(lines).rstrip() + "\n"
    out += f"\n{_GRADLE_NET_MARKER}\n"
    out += "systemProp.java.net.preferIPv4Stack=true\n"
    path.write_text(out, encoding="utf-8")
    print(f"ble_gatt_sync: Gradle IPv4 / systemProp -> {path}")


def _patch_gradle_properties_stability(path: Path) -> None:
    """Reduce parallel/VFS races on Windows (connectivity_plus extractReleaseAnnotations)."""
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    if _GRADLE_STABILITY_MARKER in text:
        return
    extra = (
        f"\n{_GRADLE_STABILITY_MARKER}\n"
        "org.gradle.parallel=false\n"
        "org.gradle.configuration-cache=false\n"
        "org.gradle.vfs.watch=false\n"
    )
    path.write_text(text.rstrip() + extra + "\n", encoding="utf-8")
    print(f"ble_gatt_sync: Gradle stability (parallel/VFS) -> {path}")


def _patch_build_gradle_extract_annotations_workaround(path: Path) -> None:
    """Gradle 8.14 + AGP: typedefFile output missing -> doNotTrackState on extractReleaseAnnotations."""
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    new_block = """
// ble_gatt: extractReleaseAnnotations workaround (Gradle 8.14 + Windows / connectivity_plus)
gradle.beforeProject {
    tasks.configureEach {
        if (name.contains("extractReleaseAnnotations", ignoreCase = true)) {
            doNotTrackState("ble_gatt: typedef output snapshot (Windows/AGP)")
        }
    }
}
"""
    new_block = new_block.lstrip("\n")
    old_block = """
// ble_gatt: extractReleaseAnnotations workaround (Gradle 8.14 + Windows / connectivity_plus)
subprojects {
    afterEvaluate {
        tasks.configureEach {
            if (name.contains("extractReleaseAnnotations", ignoreCase = true)) {
                doNotTrackState("ble_gatt: typedef output snapshot (Windows/AGP)")
            }
        }
    }
}
"""
    old_block = old_block.lstrip("\n")
    norm = text.replace("\r\n", "\n")
    if old_block in norm:
        path.write_text(norm.replace(old_block, new_block, 1), encoding="utf-8")
        print(f"ble_gatt_sync: extractReleaseAnnotations workaround (beforeProject) -> {path}")
        return
    if _EXTRACT_ANN_WORKAROUND_MARKER in text and "gradle.beforeProject" in text:
        return
    if _EXTRACT_ANN_WORKAROUND_MARKER in text:
        return
    path.write_text(text.rstrip() + "\n" + new_block, encoding="utf-8")
    print(f"ble_gatt_sync: extractReleaseAnnotations workaround -> {path}")


def _patch_settings_repositories(path: Path) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    if _MAVEN_CENTRAL_MIRROR in text:
        return
    needle = (
        "        google()\n"
        "        mavenCentral()\n"
        "        gradlePluginPortal()\n"
    )
    insert = (
        "        google()\n"
        "        maven {\n"
        f'            url = uri("{_MAVEN_CENTRAL_MIRROR}")\n'
        "        }\n"
        "        mavenCentral()\n"
        "        gradlePluginPortal()\n"
    )
    if needle not in text:
        return
    path.write_text(text.replace(needle, insert, 1), encoding="utf-8")
    print(f"ble_gatt_sync: Maven Central mirror (pluginManagement) -> {path}")


def _patch_root_build_repositories(path: Path) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    if _MAVEN_CENTRAL_MIRROR in text:
        return
    needle = "        google()\n        mavenCentral()\n"
    insert = (
        "        google()\n"
        "        maven {\n"
        f'            url = uri("{_MAVEN_CENTRAL_MIRROR}")\n'
        "        }\n"
        "        mavenCentral()\n"
    )
    if needle not in text:
        return
    path.write_text(text.replace(needle, insert, 1), encoding="utf-8")
    print(f"ble_gatt_sync: Maven Central mirror (allprojects) -> {path}")


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
    _patch_gradle_network(flutter_dir)
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
