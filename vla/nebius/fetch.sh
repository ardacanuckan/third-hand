#!/usr/bin/env bash
# Download a checkpoint from a Nebius training run into vla/checkpoints/<RUN_TAG>/<step>.
#
#   bash vla/nebius/fetch.sh <RUN_TAG>             # list what the run has saved so far
#   bash vla/nebius/fetch.sh <RUN_TAG> final       # or step-004000, step-006000, ...
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
[ -f "$HERE/nebius.env" ] && set -a && . "$HERE/nebius.env" && set +a
: "${NEBIUS_BUCKET:?set NEBIUS_BUCKET in vla/nebius/nebius.env}"
ENDPOINT="https://storage.${NEBIUS_REGION:-eu-north1}.nebius.cloud"
TAG="${1:?usage: $0 <RUN_TAG> [final|step-NNNNNN]}"
if [ $# -lt 2 ]; then
  s5cmd --profile nebius --endpoint-url "$ENDPOINT" ls "s3://$NEBIUS_BUCKET/runs/$TAG/"
  exit 0
fi
DEST="$ROOT/vla/checkpoints/$TAG/$2"; mkdir -p "$DEST"
s5cmd --profile nebius --endpoint-url "$ENDPOINT" cp "s3://$NEBIUS_BUCKET/runs/$TAG/$2/*" "$DEST/"
echo "checkpoint: $DEST"
echo "try it without the arm:  bash vla/py.sh vla/policy_grasp.py --checkpoint $DEST --dry-run"
