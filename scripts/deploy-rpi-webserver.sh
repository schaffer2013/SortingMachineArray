#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PULL_REMOTE=1

if [ "${1:-}" = "--no-pull" ]; then
  PULL_REMOTE=0
fi

cd "${REPO_ROOT}"

if [ "${PULL_REMOTE}" -eq 1 ]; then
  git fetch origin main
  git checkout main
  git pull --ff-only origin main
fi

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
