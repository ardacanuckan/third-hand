#!/usr/bin/env bash
# Start NormaCore Station with the web UI (:8889) and the Python API (:8888).
# Uses station.local.yaml if you made one (bus serials filled in), else the default station.yaml.
#
#   bash robot/normacore/run_station.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$HERE/bin/station"
CONFIG="$HERE/station.local.yaml"
[[ -f "$CONFIG" ]] || CONFIG="$HERE/station.yaml"

if [[ ! -x "$BIN" ]]; then
  echo "Station is not installed yet. Run: bash robot/normacore/install_station.sh" >&2
  exit 1
fi

cd "$HERE"   # station_data/ (recorded history) lands here and is git-ignored
echo "Config: $CONFIG"
echo "Web UI: http://localhost:8889   Python API: localhost:8888"
if [[ "$(uname -s)" == Darwin ]]; then
  echo "macOS: the camera permission belongs to this terminal app (System Settings → Privacy & Security → Camera)."
fi
exec "$BIN" --config "$CONFIG" --tcp --web
