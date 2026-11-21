#!/usr/bin/env bash
# Turn recorded grasp episodes into a training parquet, check it, and render a preview video.
#
#   bash vla/export.sh <from_frame> <to_frame> [name]
#
# <from_frame> and <to_frame> are the frame numbers of your start and end tags
# (Station web UI → History). Output: vla/data/<name>.parquet and vla/data/<name>.mp4.
#
# Environment (optional):
#   EPISODE_SECONDS  length of one episode in seconds (default 10)
#   MIN_COMMANDS     minimum servo commands for an episode to count (default 30)
#   STATION_HOST     where Station runs (default from robot/normacore/.env, else 127.0.0.1)
#   TASK             the instruction (default "pick up the resistor below the gripper")
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$ROOT/robot/normacore/bin"
[ $# -ge 2 ] || { sed -n '2,13p' "$0"; exit 2; }
FROM="$1"; TO="$2"; NAME="${3:-resistor-$(date +%H%M)}"
[ -x "$BIN/dataset-generator" ] || { echo "missing $BIN/dataset-generator: run  bash robot/normacore/install_station.sh" >&2; exit 1; }

if [ -z "${STATION_HOST:-}" ] && [ -f "$ROOT/robot/normacore/.env" ]; then
  STATION_HOST="$(sed -n 's/^STATION_HOST=//p' "$ROOT/robot/normacore/.env" | tail -1)"
fi
HOST="${STATION_HOST:-127.0.0.1}"; [ "$HOST" = "localhost" ] && HOST=127.0.0.1
TASK="${TASK:-pick up the resistor below the gripper}"
mkdir -p "$ROOT/vla/data"
OUT="$ROOT/vla/data/$NAME"

echo "exporting frames $FROM..$TO from $HOST as \"$TASK\""
"$BIN/dataset-generator" -no-tui \
  -episode.duration "${EPISODE_SECONDS:-10}" \
  -episode.min-commands "${MIN_COMMANDS:-30}" \
  -from "$FROM" -to "$TO" -robot "$HOST" \
  -output "$OUT" -task "$TASK"

PARQUET="$OUT.parquet"; [ -f "$PARQUET" ] || PARQUET="$OUT"
echo
bash "$ROOT/vla/py.sh" "$ROOT/vla/check_dataset.py" "$PARQUET" --frames-dir "$ROOT/vla/data/peek-$NAME" || true
echo
"$BIN/dataset-mp4" --input "$PARQUET" --output "$OUT.mp4" && echo "preview: $OUT.mp4" \
  || echo "(no preview video: dataset-mp4 needs Station's render service)"
