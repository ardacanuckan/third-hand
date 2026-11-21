#!/usr/bin/env bash
# Train on a Nebius GPU: bundle the code and datasets, upload, start the job.
#
#   bash vla/nebius/submit.sh vla/data/resistor.parquet [more.parquet ...]
#
# Needs a one-time setup (vla/nebius/README.md): the nebius CLI logged in, s5cmd with a
# "nebius" profile, a bucket, and vla/nebius/nebius.env with its name and id.
# Prints the RUN_TAG; fetch the result later with  bash vla/nebius/fetch.sh <RUN_TAG>.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
[ -f "$HERE/nebius.env" ] && set -a && . "$HERE/nebius.env" && set +a
if [ -z "${BUNDLE_ONLY:-}" ]; then   # BUNDLE_ONLY=1 builds vla/runs/smolvla-bundle.zip and stops
  : "${NEBIUS_BUCKET:?set NEBIUS_BUCKET in vla/nebius/nebius.env}"
  : "${NEBIUS_BUCKET_ID:?set NEBIUS_BUCKET_ID (storagebucket-...) in vla/nebius/nebius.env}"
fi
REGION="${NEBIUS_REGION:-eu-north1}"
ENDPOINT="https://storage.$REGION.nebius.cloud"
STEPS="${STEPS:-10000}"; BATCH="${BATCH_SIZE:-64}"; SAVE_EVERY="${SAVE_EVERY:-2000}"
PLATFORM="${NEBIUS_PLATFORM:-gpu-l40s-d}"; PRESET="${NEBIUS_PRESET:-1gpu-16vcpu-96gb}"; TIMEOUT="${NEBIUS_TIMEOUT:-6h}"
[ $# -ge 1 ] || { echo "usage: $0 <dataset.parquet> [...]" >&2; exit 2; }
SRC="$ROOT/vla/.norma-core/software/ai/smolvla_py"
[ -d "$SRC" ] || { echo "run  bash vla/setup.sh  first" >&2; exit 1; }

# 1. bundle: NormaCore's package and lockfile, their scripts plus our ElRobot trainer, the datasets
STAGE="$(mktemp -d)"; trap 'rm -rf "$STAGE"' EXIT
B="$STAGE/smolvla-bundle"; mkdir -p "$B/datasets" "$B/scripts"
rsync -a --exclude '__pycache__' --exclude '.venv' "$SRC/pyproject.toml" "$SRC/uv.lock" "$SRC/smolvla" "$B/"
cp "$SRC/scripts/train.py" "$SRC/scripts/merge_datasets.py" "$ROOT/vla/train_elrobot.py" "$B/scripts/"
for f in "$@"; do cp "$f" "$B/datasets/"; echo "  + datasets/$(basename "$f")"; done
ZIP="$ROOT/vla/runs/smolvla-bundle.zip"; mkdir -p "$ROOT/vla/runs"; rm -f "$ZIP"
( cd "$STAGE" && zip -qr -0 "$ZIP" smolvla-bundle )
echo "bundle: $(du -h "$ZIP" | cut -f1)  $ZIP"
[ -n "${BUNDLE_ONLY:-}" ] && exit 0

# 2. upload
s5cmd --profile nebius --endpoint-url "$ENDPOINT" cp "$ZIP" "s3://$NEBIUS_BUCKET/code/smolvla-bundle.zip"

# 3. job (the same recipe as norma-core's nebius.md, with train_elrobot.py)
RUN_TAG="elrobot-$(date +%F-%H%M)"
nebius ai job create \
  --name "smolvla-elrobot-$(date +%s)" \
  --image ghcr.io/astral-sh/uv:python3.12-bookworm-slim \
  --platform "$PLATFORM" --preset "$PRESET" --timeout "$TIMEOUT" \
  --volume "$NEBIUS_BUCKET_ID:/mnt/bucket:rw" \
  --env "STEPS=$STEPS" --env "BATCH_SIZE=$BATCH" --env "SAVE_EVERY=$SAVE_EVERY" --env "RUN_TAG=$RUN_TAG" \
  --working-dir /workspace \
  --container-command /bin/bash \
  --args '-lc "python -m zipfile -e /mnt/bucket/code/smolvla-bundle.zip . && cd smolvla-bundle && uv sync && uv run python scripts/train_elrobot.py --device cuda --steps $STEPS --batch-size $BATCH_SIZE --save-every $SAVE_EVERY --parquets datasets/*.parquet --output /mnt/bucket/runs/$RUN_TAG"'

echo
echo "RUN_TAG=$RUN_TAG"
echo "watch:  nebius ai job list   then   nebius ai job logs <job-id> --follow"
echo "fetch:  bash vla/nebius/fetch.sh $RUN_TAG"
