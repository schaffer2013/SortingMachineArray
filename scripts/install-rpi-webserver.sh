#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${SORTINGMACHINE_REPO_URL:-https://github.com/schaffer2013/SortingMachineArray.git}"
REPO_DIR="${SORTINGMACHINE_REPO_DIR:-${HOME}/SortingMachineArray}"
SERVICE_NAME="sortingmachine-web"

sudo apt-get update
sudo apt-get install -y git python3 python3-venv python3-pip python3-picamera2 python3-gpiozero

if [ ! -d "${REPO_DIR}/.git" ]; then
  git clone "${REPO_URL}" "${REPO_DIR}"
fi

cd "${REPO_DIR}"
git fetch origin main
git checkout main
git pull --ff-only origin main
git submodule update --init --recursive
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e '.[hardware]'
python -m pip install -e './third_party/fuzzy-enigma-card-recognition[ocr,moss]'
chmod +x scripts/start-rpi-webserver.sh

cat > /tmp/${SERVICE_NAME}.service <<SERVICE
[Unit]
Description=Sorting Machine real hardware web console
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=${USER}
WorkingDirectory=${REPO_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=SORTER_MODE=hardware
Environment=SORTER_RECOGNIZER_BACKEND=moss_machine
Environment=SORTER_FUZZY_ENIGMA_SIM_TRUTH_FALLBACK=0
Environment=SORTER_MARLIN_SERIAL_PORT=/dev/ttyACM0
Environment=SORTER_MARLIN_BAUD_RATE=115200
Environment=SORTER_VACUUM_RELAY_PIN=17
ExecStart=${REPO_DIR}/scripts/start-rpi-webserver.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE

sudo install -m 0644 /tmp/${SERVICE_NAME}.service /etc/systemd/system/${SERVICE_NAME}.service
sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}.service
sudo systemctl restart ${SERVICE_NAME}.service
sudo systemctl --no-pager --full status ${SERVICE_NAME}.service