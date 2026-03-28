#!/usr/bin/env bash
set -euo pipefail

WITH_SUDO_APT=1
SKIP_TESTS=0
SKIP_SIM_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-apt)
      WITH_SUDO_APT=0
      shift
      ;;
    --skip-tests)
      SKIP_TESTS=1
      shift
      ;;
    --skip-sim-run)
      SKIP_SIM_RUN=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ "$WITH_SUDO_APT" -eq 1 ]]; then
  echo '==> Installing system packages'
  sudo apt update
  sudo apt install -y git python3 python3-venv python3-pip
fi

echo '==> Ensuring submodules are initialized'
git submodule update --init --recursive

echo '==> Creating virtual environment (.venv)'
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo '==> Upgrading pip'
python -m pip install --upgrade pip

echo '==> Installing project dependencies (dev + hardware)'
pip install -e '.[dev,hardware]'

echo '==> Installing fuzzy-enigma recognizer and OCR runtime'
pip install -e ./third_party/fuzzy-enigma-card-recognition
pip install rapidocr-onnxruntime

if [[ -f ./third_party/fuzzy-enigma-card-recognition/requirements.txt ]]; then
  echo '==> Installing submodule requirements.txt'
  pip install -r ./third_party/fuzzy-enigma-card-recognition/requirements.txt
fi

echo '==> Verifying submodule path and RapidOCR import'
test -d ./third_party/fuzzy-enigma-card-recognition/src
python -c "import rapidocr_onnxruntime; print('rapidocr ok')"

if [[ "$SKIP_TESTS" -eq 0 ]]; then
  echo '==> Running test suite'
  pytest -q
fi

if [[ "$SKIP_SIM_RUN" -eq 0 ]]; then
  echo '==> Running sim CLI smoke check'
  python -m sorter.interfaces.cli --mode sim
fi

echo 'Installation complete.'
