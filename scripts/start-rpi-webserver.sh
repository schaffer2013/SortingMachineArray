#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

if [ ! -x ".venv/bin/python" ]; then
  echo "Missing .venv. Run scripts/deploy-rpi-webserver.sh before starting the service." >&2
  exit 1
fi

. .venv/bin/activate

export SORTER_MODE=hardware
export SORTER_RECOGNIZER_BACKEND="${SORTER_RECOGNIZER_BACKEND:-moss_machine}"
export SORTER_FUZZY_ENIGMA_SIM_TRUTH_FALLBACK=0
export SORTER_MARLIN_SERIAL_PORT="${SORTER_MARLIN_SERIAL_PORT:-/dev/ttyACM0}"
export SORTER_MARLIN_BAUD_RATE="${SORTER_MARLIN_BAUD_RATE:-115200}"
export SORTER_VACUUM_RELAY_PIN="${SORTER_VACUUM_RELAY_PIN:-17}"

exec python -m sorter.interfaces.web_runner
