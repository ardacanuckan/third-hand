#!/usr/bin/env bash
# Set up NormaCore's SmolVLA package (software/ai/smolvla_py) in vla/.norma-core and download
# the base model, so training, the dataset checker and the policy grasp all run from this repo.
#
#   bash vla/setup.sh
#
# Needs git, uv and about 3 GB of disk. Safe to re-run.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIN="${NORMA_CORE_PIN:-6b494f77fac366a878ae71222458b196f8400dee}"   # norma-core main, 21 Nov 2026
DEST="$HERE/.norma-core"
PY="${VLA_PYTHON:-3.12}"

if [ ! -d "$DEST/.git" ]; then
  echo "cloning norma-core (smolvla_py only) into $DEST"
  git clone -q --filter=blob:none --sparse --no-checkout https://github.com/norma-core/norma-core.git "$DEST"
fi
git -C "$DEST" sparse-checkout set software/ai/smolvla_py
git -C "$DEST" checkout -q "$PIN"
echo "norma-core at $(git -C "$DEST" rev-parse --short HEAD)"

cd "$DEST/software/ai/smolvla_py"
echo "installing smolvla_py with Python $PY (torch, transformers, ...)"
uv sync --python "$PY"

echo "downloading the base model and the SmolVLM2 processor"
uv run --python "$PY" python - <<'EOF'
from huggingface_hub import snapshot_download
snapshot_download("lerobot/smolvla_base")
# Only the processor and config files: SmolVLA ships the VLM weights inside its own checkpoint.
snapshot_download("HuggingFaceTB/SmolVLM2-500M-Video-Instruct",
                  allow_patterns=["*.json", "*.txt", "*.jinja", "tokenizer*", "*.model"])
print("models ready")
EOF

echo
echo "ready. Run our scripts with:  bash vla/py.sh <script.py> [args]"
