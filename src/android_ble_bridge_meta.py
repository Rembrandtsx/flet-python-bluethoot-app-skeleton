"""
Resolve the Android BleGattBridge class name so it matches the Flet app package.

On device, ``pyproject.toml`` is not bundled; we read one line from
``ble_android_package.txt`` next to this module (written at build time).

Flet puts MainActivity in ``{org}.{project_slug}`` (see flet_cli build_base.setup_template_data).
"""

from __future__ import annotations

import re
import unicodedata

try:
    import tomllib
except ImportError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]
from pathlib import Path


def _slugify(value: str) -> str:
    """Same rules as flet.utils.slugify (used for Android package segment)."""
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-_\s]+", "-", value).strip("-")


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def ble_bundle_package_from_pyproject() -> str:
    """
    Compute Android package from ``pyproject.toml`` (used on the build machine and
    when writing ``ble_android_package.txt``).
    """
    root = _project_root()
    py = root / "pyproject.toml"
    if not py.is_file():
        return "com.flet.app"

    data = tomllib.loads(py.read_text(encoding="utf-8"))
    tool = data.get("tool") or {}
    flet = tool.get("flet") or {}
    android = flet.get("android") or {}

    bundle = android.get("bundle_id") or flet.get("bundle_id")
    if bundle:
        return str(bundle).strip()

    org = android.get("org") or flet.get("org") or "com.flet"
    name = (data.get("project") or {}).get("name") or "app"
    project_name_slug = _slugify(str(name))
    project_name = project_name_slug.replace("-", "_")
    return f"{org}.{project_name}"


def ble_bundle_package() -> str:
    """
    Android application id / Java package for the Flutter host activity,
    e.g. ``com.flet.flet_bluetooth_prototype``.

    Prefer ``ble_android_package.txt`` (bundled in the APK); fall back to pyproject
    when developing from source.
    """
    hint = Path(__file__).resolve().parent / "ble_android_package.txt"
    if hint.is_file():
        line = hint.read_text(encoding="utf-8").strip().splitlines()[0].strip()
        if line:
            return line
    return ble_bundle_package_from_pyproject()


def ble_bridge_class_fqcn() -> str:
    return f"{ble_bundle_package()}.BleGattBridge"


def ble_bridge_events_iface_internal() -> str:
    """JNI internal form for the inner Events interface."""
    pkg = ble_bundle_package()
    return pkg.replace(".", "/") + "/BleGattBridge$Events"
