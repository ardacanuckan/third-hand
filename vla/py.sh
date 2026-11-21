#!/usr/bin/env bash
# Run a Python script inside the smolvla_py environment that vla/setup.sh created.
#
#   bash vla/py.sh vla/check_dataset.py data/resistor.parquet
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJ="$HERE/.norma-core/software/ai/smolvla_py"
if [ ! -d "$PROJ/.venv" ]; then
  echo "smolvla_py is not set up yet: run  bash vla/setup.sh" >&2
  exit 1
fi
exec uv run --project "$PROJ" --python "${VLA_PYTHON:-3.12}" python "$@"
