#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

git fetch origin main
git checkout main
git pull --ff-only origin main
git submodule update --init --recursive

if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv --system-site-packages .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e '.[hardware]'
python -m pip install -e './third_party/fuzzy-enigma-card-recognition[moss]'
# rapidocr-onnxruntime >=1.4 does not currently publish for the Pi's Python 3.13 runtime.
python -m pip install 'rapidocr-onnxruntime==1.2.3'
python -m pip install 'paddleocr>=3.7'

export SORTER_MODE=hardware
export SORTER_RECOGNIZER_BACKEND="${SORTER_RECOGNIZER_BACKEND:-moss_machine}"
export SORTER_FUZZY_ENIGMA_SIM_TRUTH_FALLBACK=0
export SORTER_MARLIN_SERIAL_PORT="${SORTER_MARLIN_SERIAL_PORT:-/dev/ttyACM0}"
export SORTER_MARLIN_BAUD_RATE="${SORTER_MARLIN_BAUD_RATE:-115200}"
export SORTER_VACUUM_RELAY_PIN="${SORTER_VACUUM_RELAY_PIN:-17}"

exec python -m sorter.interfaces.web_runner