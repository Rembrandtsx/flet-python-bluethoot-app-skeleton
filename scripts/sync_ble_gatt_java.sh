#!/usr/bin/env bash
# Copy BleGattBridge.java into Flet's generated Android project(s).
# Prefer ./scripts/flet-with-cert.sh — it uses flet_with_ble_gatt.py with the exact flutter_dir.
# Manual examples:
#   ./scripts/sync_ble_gatt_java.sh build/flutter
#   ./scripts/sync_ble_gatt_java.sh src/build/flutter
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"
run_sync() {
  local abs
  abs="$(cd "$1" && pwd)"
  python3 -c "from pathlib import Path; from flet_with_ble_gatt import sync_ble_gatt_java; sync_ble_gatt_java(Path(r'${abs}'))"
}
if [[ "${1:-}" != "" ]]; then
  run_sync "$1"
  exit 0
fi
synced=0
try_dir() {
  local d="$ROOT/$1"
  [[ -d "$d" ]] || return 0
  run_sync "$d"
  synced=1
}
try_dir "build/flutter"
try_dir "src/build/flutter"
while IFS= read -r d; do
  [[ -d "$d" ]] || continue
  run_sync "$d"
  synced=1
done < <(find "$ROOT" -type d -path '*/build/flutter' 2>/dev/null || true)
if [[ "$synced" -eq 0 ]]; then
  echo "sync_ble_gatt_java: no build/flutter tree found; pass: $0 path/to/build/flutter" >&2
fi
