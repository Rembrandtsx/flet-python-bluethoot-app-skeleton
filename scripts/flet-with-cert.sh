#!/usr/bin/env bash
# Run the Flet CLI with SSL_CERT_FILE set from certifi (macOS / python.org Python).
# Usage (from project root, venv active):
#   ./scripts/flet-with-cert.sh build aab
#   ./scripts/flet-with-cert.sh build apk
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -f .venv/bin/activate ]]; then
  # shellcheck source=/dev/null
  source .venv/bin/activate
fi
export SSL_CERT_FILE="$(python -c 'import certifi; print(certifi.where())')"
export REQUESTS_CA_BUNDLE="$SSL_CERT_FILE"
# BleGatt Java bridge is synced inside flet_with_ble_gatt.py immediately before Gradle (required for APK).
exec python "$ROOT/scripts/flet_with_ble_gatt.py" "$@"
