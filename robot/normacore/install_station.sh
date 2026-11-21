#!/usr/bin/env bash
# Download the NormaCore Station binary for this machine into robot/normacore/bin/.
# The Python side (station_py + generated protobufs) is already vendored in ./vendor.
#
#   bash robot/normacore/install_station.sh            # install v0.1.0-beta.10
#   STATION_VERSION=v0.1.0-beta.10 bash robot/normacore/install_station.sh --force
set -euo pipefail

STATION_VERSION="${STATION_VERSION:-v0.1.0-beta.10}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HERE/bin"
FORCE=false
[[ "${1:-}" == "--force" ]] && FORCE=true

case "$(uname -s)/$(uname -m)" in
  Darwin/arm64) ASSET="station-macos-arm64.zip" ;;
  Linux/x86_64 | Linux/amd64) ASSET="station-linux-amd64.tar.gz" ;;
  Linux/aarch64 | Linux/arm64) ASSET="station-linux-arm64.tar.gz" ;;
  *) echo "Station ${STATION_VERSION} has no build for $(uname -s)/$(uname -m). Use an Apple Silicon Mac or Linux." >&2; exit 1 ;;
esac

if [[ -x "$BIN_DIR/station" && -f "$BIN_DIR/.version" && "$(cat "$BIN_DIR/.version")" == "$STATION_VERSION" && "$FORCE" == false ]]; then
  echo "Station ${STATION_VERSION} is already installed at $BIN_DIR/station"
  exit 0
fi

URL="https://github.com/norma-core/norma-core/releases/download/${STATION_VERSION}/${ASSET}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
echo "Downloading $URL"
curl -fL --progress-bar -o "$TMP/$ASSET" "$URL"
mkdir -p "$BIN_DIR"
case "$ASSET" in
  *.zip) unzip -qo "$TMP/$ASSET" -d "$BIN_DIR" ;;
  *.tar.gz) tar -xzf "$TMP/$ASSET" -C "$BIN_DIR" ;;
esac
chmod +x "$BIN_DIR"/station "$BIN_DIR"/dataset-generator "$BIN_DIR"/dataset-mp4 2>/dev/null || chmod +x "$BIN_DIR/station"
if [[ "$(uname -s)" == Darwin ]]; then
  xattr -dr com.apple.quarantine "$BIN_DIR" 2>/dev/null || true
fi
echo "$STATION_VERSION" > "$BIN_DIR/.version"
echo "Installed Station ${STATION_VERSION} at $BIN_DIR/station"

if [[ "$(uname -s)" == Linux ]] && ! id -nG "$USER" | tr ' ' '\n' | grep -qx dialout; then
  echo
  echo "Linux: add yourself to the dialout group so Station can open the servo boards, then log out and back in:"
  echo "  sudo usermod -a -G dialout \$USER"
fi
